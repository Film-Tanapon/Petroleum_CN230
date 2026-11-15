"""Import annual proven reserves from Reserve-2 Excel workbooks, atomically."""
import argparse
from collections import Counter
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import getpass
import hashlib
import os
from pathlib import Path
import sys

import mysql.connector
from dotenv import load_dotenv
from openpyxl import load_workbook

from import_emission_factor import resolve_reference

ROOT = Path(__file__).resolve().parent
FILES = {
    '2025_p1-oil.xlsx': ('P1 Oil', 'Oil', 'PROD-CRUDE', ('Crude Oil', 'น้ำมันดิบ'), 'MMbbl'),
    '2025_p1-gas.xlsx': ('P1 Gas', 'Gas', 'PROD-NG', ('Natural Gas', 'ก๊าซธรรมชาติ'), 'Bcf'),
    '2025_p1-condy.xlsx': ('P1 Condy', 'Condy', 'PROD-COND', ('Condensate', 'คอนเดนเสท'), 'MMbbl'),
}


def identifier(prefix, *parts):
    return prefix + hashlib.sha256('\x1f'.join(map(str, parts)).encode('utf-8')).hexdigest()[:32]


def parse_value(value):
    if value is None or (isinstance(value, str) and value.strip() in ('', '-')):
        return None, None
    try:
        if isinstance(value, bool):
            raise InvalidOperation
        original = Decimal(str(value).replace(',', '').strip())
        if not original.is_finite() or original < 0:
            raise InvalidOperation
        rounded = original.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        if rounded >= Decimal('1000000000000'):
            raise InvalidOperation
        return original, rounded
    except InvalidOperation as exc:
        raise ValueError('reserve must be nonnegative and fit DECIMAL(18,6)') from exc


def read_records(folder):
    records, seen = [], set()
    for filename, (sheet_name, fuel, product, aliases, unit) in FILES.items():
        path = folder / filename
        formulas = load_workbook(path, read_only=True, data_only=False)
        cached = None
        try:
            cached = load_workbook(path, read_only=True, data_only=True)
            if sheet_name not in formulas.sheetnames:
                raise ValueError(f'{filename}: missing sheet {sheet_name}')
            sheet = formulas[sheet_name]
            expected = ('Year', 'Block', f'Prove Reserves of {fuel} ({unit})')
            if tuple(next(sheet.iter_rows(values_only=True))[:3]) != expected:
                raise ValueError(f'{filename}: expected header {expected}')
            formula_rows = sheet.iter_rows(min_row=2, values_only=True)
            cached_rows = cached[sheet_name].iter_rows(min_row=2, values_only=True)
            for line, (source, cache) in enumerate(zip(formula_rows, cached_rows, strict=True), 2):
                if all(v is None for v in source):
                    continue
                try:
                    if any(v is not None for v in source[3:]):
                        raise ValueError('unexpected data outside columns A:C')
                    raw_year, block, raw_value = source[:3]
                    if isinstance(raw_year, bool) or not isinstance(raw_year, (int, float)) or int(raw_year) != raw_year:
                        raise ValueError('year must be an integer')
                    year = int(raw_year)
                    if year >= 2400:
                        year -= 543
                    if not 1900 <= year <= 2200:
                        raise ValueError('year outside supported range')
                    if block is None or isinstance(block, bool):
                        raise ValueError('missing block label')
                    block = str(block).strip()
                    if not block or len(block) > 50 or block.startswith('='):
                        raise ValueError('invalid block label')
                    formula = raw_value if isinstance(raw_value, str) and raw_value.startswith('=') else ''
                    if formula:
                        raw_value = cache[2]
                        if raw_value is None:
                            raise ValueError('formula has no cached result; recalculate and save Excel first')
                    original, value = parse_value(raw_value)
                    grain = (product, block.casefold(), unit, year)
                    if grain in seen:
                        raise ValueError('duplicate product/block/unit/year in source')
                    seen.add(grain)
                    records.append(dict(source_file=filename, sheet=sheet_name, row=line,
                                        product=product, aliases=aliases, block=block, unit=unit, year=year,
                                        original=original, value=value, formula=formula))
                except ValueError as exc:
                    raise ValueError(f'{filename}:{sheet_name}:{line}: {exc}') from exc
        finally:
            formulas.close()
            if cached is not None:
                cached.close()
    return records


def resolve_block(cur, label, stats):
    cur.execute('SELECT block_id,label FROM Block FOR UPDATE')
    rows = cur.fetchall()
    matches = [r for r in rows if str(r[1]).strip().casefold() == label.casefold()]
    if len(matches) > 1:
        raise ValueError(f'ambiguous Block label {label!r}: {matches}')
    if matches:
        return matches[0][0]
    code = identifier('RB_', label.casefold())
    if any(str(r[0]).casefold() == code.casefold() for r in rows):
        raise ValueError(f'Block ID collision: {code}')
    cur.execute('INSERT INTO Block (block_id,label) VALUES (%s,%s)', (code, label))
    stats['Block added'] += 1
    return code


def import_records(db, records, apply=False):
    stats, products, units, blocks = Counter(), {}, {}, {}
    lock = identifier('import_', db.database)
    acquired = False
    try:
        with db.cursor() as cur:
            cur.execute('SELECT GET_LOCK(%s,10)', (lock,))
            acquired = cur.fetchone()[0] == 1
            if not acquired:
                raise RuntimeError('Another petroleum import is running')
            for table in ('Product', 'Unit', 'Block', 'Reserve_Annual'):
                cur.execute('SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s', (table,))
                row = cur.fetchone()
                if not row or row[0] != 'InnoDB':
                    raise ValueError(f'{table}: expected an existing InnoDB table')
            cur.execute("SET SESSION sql_mode=CONCAT_WS(',',NULLIF(@@sql_mode,''),'STRICT_ALL_TABLES')")
            for record in records:
                p, u, b, year = (record[k] for k in ('product', 'unit', 'block', 'year'))
                if p not in products:
                    products[p] = resolve_reference(cur, 'Product', p, record['aliases'], stats)
                if u not in units:
                    desc = 'million barrels' if u == 'MMbbl' else 'billion cubic feet'
                    units[u] = resolve_reference(cur, 'Unit', 'UNIT-'+u.upper(), (u,), stats, desc)
                if b.casefold() not in blocks:
                    blocks[b.casefold()] = resolve_block(cur, b, stats)
                grain = (products[p], blocks[b.casefold()], units[u], year)
                value = record['value']
                cur.execute('SELECT reserve_id,proven_reserves FROM Reserve_Annual '
                            'WHERE product_id=%s AND block_id=%s AND unit_id=%s AND year=%s FOR UPDATE', grain)
                previous = cur.fetchall()
                if len(previous) > 1:
                    raise ValueError(f'duplicate existing reserve grain: {grain}')
                if not previous:
                    code = identifier('RA_', p, b.casefold(), u, year)
                    cur.execute('INSERT INTO Reserve_Annual '
                                '(reserve_id,product_id,block_id,unit_id,proven_reserves,year) '
                                'VALUES (%s,%s,%s,%s,%s,%s)', (code, *grain[:3], value, year))
                    stats['reserves added'] += 1
                elif previous[0][1] != value:
                    cur.execute('UPDATE Reserve_Annual SET proven_reserves=%s WHERE reserve_id=%s', (value, previous[0][0]))
                    stats['reserves updated'] += 1
                else:
                    stats['reserves unchanged'] += 1
                stats['NULL reserves'] += value is None
                stats['rounded values'] += record['original'] != value
                stats['cached formula values'] += bool(record['formula'])
        if apply:
            db.commit()
        else:
            db.rollback()
        return stats
    except BaseException:
        db.rollback()
        raise
    finally:
        if acquired:
            with db.cursor() as cur:
                cur.execute('SELECT RELEASE_LOCK(%s)', (lock,))
                cur.fetchone()


def write_review(path, records):
    with path.open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.writer(out)
        writer.writerow(['source_file','sheet','row','product','block','unit','year','source_value','stored_value','note'])
        for r in records:
            notes = []
            if r['value'] is None:
                notes.append('missing reserve retained as NULL')
            elif r['original'] != r['value']:
                notes.append('rounded HALF_UP to 6 decimals')
            if r['formula']:
                notes.append('cached Excel formula result; not recalculated: '+r['formula'])
            writer.writerow([r[k] for k in ('source_file','sheet','row','product','block','unit','year','original','value')] + ['; '.join(notes)])


def main():
    load_dotenv(ROOT / '.env', encoding='utf-8-sig', interpolate=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=ROOT / 'CN230 Petrolium Data' / 'Reserve-2')
    parser.add_argument('--host', default=os.getenv('MYSQL_HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.getenv('MYSQL_PORT', '3308')))
    parser.add_argument('--database', default=os.getenv('MYSQL_DATABASE', 'petroleum'))
    parser.add_argument('--user', default=os.getenv('MYSQL_USER', 'root'))
    parser.add_argument('--report', type=Path, default=ROOT / 'reserve_import_review.csv')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    records = read_records(args.folder)
    write_review(args.report, records)
    print(f'Excel validated: {len(records)} reserve records; review: {args.report}')
    password = os.getenv('MYSQL_PASSWORD') or getpass.getpass('MySQL password: ')
    db = mysql.connector.connect(host=args.host, port=args.port, database=args.database,
                                 user=args.user, password=password, charset='utf8mb4', autocommit=False)
    try:
        for label, count in sorted(import_records(db, records, apply=args.apply).items()):
            print(f'{label}: {count}')
        print('Import committed.' if args.apply else 'Dry run complete: rolled back.')
    finally:
        db.close()


if __name__ == '__main__':
    try:
        main()
    except (mysql.connector.Error, ValueError, RuntimeError, OSError) as exc:
        sys.exit(f'Import stopped: {exc}')
