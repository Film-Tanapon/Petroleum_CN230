"""Import petroleum CSV, emission factors, and annual reserves from one entry point.

Usage:
    py import_data.py --type csv --database petroleum --dry-run
    py import_data.py --type emission --dry-run
    py import_data.py --type reserve --dry-run

Run CSV before the Excel imports: CSV mode resets all ten project tables.
Each mode requires --dry-run (rollback) or --apply (commit).
"""
import argparse
import csv
import getpass
import hashlib
import io
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent


DEFAULT_CSV_FOLDER = ROOT / "CN230 Petrolium Data"
PRODUCTION = {"oil": "น้ำมันดิบ", "condensate": "คอนเดนเสท", "gas": "ก๊าซธรรมชาติ"}
SUPPLY = {"crude": ("น้ำมันดิบ", "CRUDEPROD"), "condy": ("คอนเดนเสท", "CONDPROD"),
          "gas": ("ก๊าซธรรมชาติ", "GASPROD")}
SALE_TYPES = {"oli": "น้ำมันดิบ", "gas": "ก๊าซธรรมชาติ", "condensate": "คอนเดนเสท", "lpg": "LPG"}
FIELDS = {
    "Product": "product_id name", "Field": "field_id name", "Block": "block_id label",
    "Unit": "unit_id symbol description",
    "Production_Monthly": "production_id product_id field_id block_id unit_id quantity oil_equivalent production_days year month",
    "Supply_Monthly": "supply_id product_id unit_id area daily_rate month year",
    "Sale": "sale_id product_id field_id volume_bbl volume_mmscf energy_mmbtu sale_value royalty currency month year",
    "Price_Monthly": "price_id product_id field_id unit_id unit_price currency month year",
}
DIMENSIONS = ("Product", "Field", "Block", "Unit")
UNIT_DESC = {"BBLD":"barrels per day", "MMSCFD":"million standard cubic feet per day",
            "bbl":"barrel", "MMBtu":"million British thermal units"}
PRICE_CURR = {"both": ("THB","USD"), "THB": ("THB",), "USD": ("USD",)}
PRODUCT_NAMES = {"น้ำมันดิบ": "Crude Oil", "ก๊าซธรรมชาติ": "Natural Gas",
                 "คอนเดนเสท": "Condensate", "LPG": "LPG"}
PREFIX = {"Product":"P","Field":"F","Block":"B","Unit":"U","Production_Monthly":"PR",
          "Sale":"S","Price_Monthly":"PC","Supply_Monthly":"SP"}
DELETE_ORDER = ("Emission_Factor","Reserve_Annual","Sale","Supply_Monthly","Price_Monthly",
                "Production_Monthly","Field","Block","Unit","Product")
EXPECTED = {
    **{f"Manufacture Data/production_{k}.csv": "production" for k in PRODUCTION},
    **{f"Supply Data/supply_th_{k}.csv": "supply" for k in SUPPLY},
    **{f"Price Data/price_{k}.csv": "price" for k in SUPPLY},
    "Price Data/petroluem-report.csv": "sale",
}
SUMMARY = {f"Price Data/{s}.csv" for s in ("oli","condensate","gas")}


def parse_csv_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--folder", type=Path, default=DEFAULT_CSV_FOLDER)
    p.add_argument("--database", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=3308)
    p.add_argument("--user", default="root")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Rehearse the entire reset and roll back.")
    mode.add_argument("--apply", action="store_true", help="Replace all rows in the ten project tables.")
    p.add_argument("--price-currency", choices=PRICE_CURR, default="both")
    p.add_argument("--sale-currency", help="Set only if the currency of values/royalty is confirmed.")
    p.add_argument("--gas-price-unit", help="Confirmed gas price denominator (e.g. MMBtu); default NULL.")
    p.add_argument("--include-negative-sales", action="store_true", help="Keep negative sale values/royalties if your rules permit.")
    p.add_argument("--report", type=Path, default=Path("petroleum_import_review.csv"))
    p.add_argument("--supply-area-column", default="area", help="Actual column for supply area")
    p.add_argument("--supply-rate-column", default="daily_rate", help="Actual column for daily supply rate")
    return p.parse_args(argv)


def key(prefix, *parts):
    raw = "\x1f".join(map(str,parts)).encode("utf-8")
    return prefix + "_" + hashlib.sha256(raw).hexdigest()[:32]


def number(value):
    if value is None or value.strip() in ("","-"):
        return None
    return Decimal(value.replace(",","").strip())


def read_rows(path):
    data = path.read_bytes()
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = data.decode("cp874")
    return csv.DictReader(io.StringIO(content,newline=""))


class Importer:
    def __init__(self, cur, args):
        self.cur = cur
        self.args = args
        self.pending = defaultdict(list)
        self.stats = Counter()
        self.issues = []
        self.names = {}
        self.column_specs = {}
        self.sql_columns = {}
        for table, columns in FIELDS.items():
            cur.execute("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s", (table,))
            engine = cur.fetchone()
            if not engine or engine[0] != "InnoDB":
                raise ValueError(f"{table}: expected an existing InnoDB table")
            cur.execute(f"SHOW COLUMNS FROM `{table}`")
            specs = {r[0]:r[1].lower() for r in cur.fetchall()}
            aliases = {}
            if table == "Supply_Monthly":
                aliases = {"area":args.supply_area_column,"daily_rate":args.supply_rate_column}
            lookup = {name.casefold():name for name in specs}
            names = {c:lookup.get(aliases.get(c,c).casefold()) for c in columns.split()}
            missing = [c for c,v in names.items() if v is None]
            if missing:
                raise ValueError(f"{args.database}.{table}: missing {missing}. Actual columns: {list(specs)}")
            if len(set(names.values())) != len(names):
                raise ValueError(f"{table}: two fields target the same column")
            self.column_specs[table] = {c:specs[v] for c,v in names.items()}
            cols = ", ".join("`" + v.replace("`","``") + "`" for v in names.values())
            self.sql_columns[table] = cols
            if table in DIMENSIONS:
                self.names[table] = {}
        for label in PRODUCT_NAMES:
            self.ref("Product",label)

    def ref(self, table, label):
        label = (label or "").strip()
        if not label:
            return None
        names = self.names[table]
        if label in names:
            return names[label]
        pk = f"{PREFIX[table]}{len(names)+1:02d}"
        display = PRODUCT_NAMES[label] if table == "Product" else label
        names[label] = pk
        row = (pk,display,UNIT_DESC.get(label,display)) if table=="Unit" else (pk,display)
        self.pending[table].append(row)
        return pk

    def add(self, table, values, variant=""):
        pk = f"{PREFIX[table]}{len(self.pending[table])+1:02d}"
        # Match the DECIMAL scale in the actual target before comparing on a repeat run.
        converted = []
        for column,value in zip(FIELDS[table].split()[1:], values, strict=True):
            spec = self.column_specs[table][column]
            if isinstance(value,Decimal) and spec.startswith("decimal("):
                scale = int(spec.partition(",")[2].split(")")[0])
                rounded = value.quantize(Decimal(1).scaleb(-scale),rounding=ROUND_HALF_UP)
                if rounded != value:
                    self.stats["rounded numeric values"] += 1
                value = rounded
            converted.append(value)
        values = tuple(converted)
        self.pending[table].append((pk,*values))

    def process(self, kind, tag, r):
        year = int(r["YEAR"])
        if year >= 2400:
            year -= 543
        month = int(r["MONTH"])
        if not 1 <= month <= 12:
            raise ValueError(f"Invalid month: {month}")
        product = lambda name: self.ref("Product", name)
        unit = lambda label: self.ref("Unit", label)
        if kind=="production":
            qty = tag.upper()
            self.add("Production_Monthly", (product(PRODUCTION[tag]),self.ref("Field",r["SOURCE_GROUP"]),
                     self.ref("Block",r["BLOCK"]),unit("MMSCFD" if tag=="gas" else "BBLD"),
                     number(r[qty]),number(r.get(qty+"_EQUI_OIL")),number(r["DAYSOFPRODUCE"]),year,month))
        elif kind=="supply":
            label,qty = SUPPLY[tag]
            self.add("Supply_Monthly",(product(label),unit(r[qty+"_UNIT"]),{"ในประเทศ":"Domestic","":None}[r["AREATYPE"].strip()],
                     number(r[qty]),month,year))
        elif kind=="price":
            label = SUPPLY[tag][0]
            denom = self.args.gas_price_unit if tag=="gas" else "bbl"
            if not r["FIELD"].strip():
                self.issues.append((self.file,self.line,"missing required Price_Monthly.field_id","",""))
                return
            if not denom:
                self.issues.append((self.file,self.line,"unconfirmed gas price unit; set --gas-price-unit after verification","",""))
                return
            for currency in PRICE_CURR[self.args.price_currency]:
                self.add("Price_Monthly",(product(label),self.ref("Field",r["FIELD"]),unit(denom),
                         number(r[currency+"/BARREL"]),currency,month,year),currency)
        else:
            sale,royalty = number(r["VALUES"]),number(r["ROYALTY"])
            if not r["FIELD"].strip():
                self.issues.append((self.file,self.line,"missing required Sale.field_id",sale,royalty))
                return
            if any(n is not None and n<0 for n in (sale,royalty)) and not self.args.include_negative_sales:
                self.issues.append((self.file,self.line,"negative sale_value or royalty",sale,royalty))
                return
            self.add("Sale",(product(SALE_TYPES[r["TYPE"].strip().lower()]),self.ref("Field",r["FIELD"]),
                     number(r["SALES(BARRELS)"]),number(r["SALES(MMSCF)"]),number(r["SALES(MILLION_BTU)"]),
                     sale,royalty,self.args.sale_currency,month,year))

    def read(self):
        for self.file,kind in EXPECTED.items():
            path = self.args.folder/self.file
            tag = path.stem.split("_")[-1]
            seen = set()
            for self.line,raw in enumerate(read_rows(path),2):
                if None in raw or None in raw.values():
                    raise ValueError(f"{self.file}:{self.line}: malformed CSV record")
                r = {k.strip().upper():v.strip() for k,v in raw.items()}
                signature = tuple(r.items())
                if signature in seen:
                    self.issues.append((self.file,self.line,"duplicate source record","",""))
                    continue
                seen.add(signature)
                try:
                    self.process(kind,tag,r)
                except (ValueError,KeyError,ArithmeticError) as exc:
                    raise ValueError(f"{self.file}:{self.line}: {exc}") from exc

    def write(self):
        for table,columns in FIELDS.items():
            rows = self.pending[table]
            cols = columns.split()
            sql = f"INSERT INTO `{table}` ({self.sql_columns[table]}) VALUES ("+",".join(["%s"]*len(cols))+")"
            for i in range(0,len(rows),500):
                try:
                    self.cur.executemany(sql,rows[i:i+500])
                except mysql.connector.Error as exc:
                    raise RuntimeError(f"{table}, batch beginning {rows[i][0]}: {exc}") from exc
            print(f"{table}: {len(rows):,} new")


def import_csv_main(argv=None):
    args = parse_csv_args(argv)
    missing = [f for f in EXPECTED if not (args.folder/f).is_file()]
    if missing:
        raise ValueError(f"Check --folder ({args.folder}); missing: "+", ".join(missing))
    for path in sorted(args.folder.rglob("*.csv")):
        rel = path.relative_to(args.folder).as_posix()
        if rel not in EXPECTED:
            print("Skipped monthly sales summary:" if rel in SUMMARY else "Unmapped CSV:", rel)
    password = os.getenv("MYSQL_PASSWORD") or getpass.getpass("MySQL password: ")
    db = mysql.connector.connect(host=args.host,port=args.port,user=args.user,password=password,
                                 database=args.database,charset="utf8mb4",autocommit=False)
    try:
        with db.cursor() as cur:
            lock = key("import",args.database)
            cur.execute("SELECT GET_LOCK(%s,10)",(lock,))
            if cur.fetchone()[0]!=1:
                raise RuntimeError("Another import is running")
            cur.execute("SET SESSION sql_mode=CONCAT_WS(',',NULLIF(@@sql_mode,''),'STRICT_ALL_TABLES')")
            job = Importer(cur,args)
            job.read()
            with args.report.open("w",encoding="utf-8-sig",newline="") as out:
                writer = csv.writer(out)
                writer.writerow(["source_file","record_no","reason","sale_value","royalty"])
                writer.writerows(job.issues)
            # Check all tables, including CSV-less tables, BEFORE deleting any rows.
            for table in DELETE_ORDER:
                cur.execute("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",(table,))
                engine=cur.fetchone()
                if not engine or engine[0]!="InnoDB":
                    raise ValueError(f"Expected transactional table {table}")
            # Refuse cascades into tables outside this project.
            cur.execute("SELECT TABLE_SCHEMA,TABLE_NAME,REFERENCED_TABLE_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE REFERENCED_TABLE_SCHEMA=DATABASE()")
            for schema,child,parent in cur.fetchall():
                project={t.casefold() for t in DELETE_ORDER}
                if parent.casefold() in project and (schema!=args.database or child.casefold() not in project):
                    raise ValueError(f"External dependency: {schema}.{child} references {parent}")
            for table in DELETE_ORDER:
                cur.execute(f"DELETE FROM `{table}`")
                print(f"{table}: removed {cur.rowcount} old rows")
            job.write()
            print(dict(job.stats), f"Review rows: {len(job.issues)} -> {args.report}")
        if args.dry_run:
            db.rollback()
            print("Dry run complete: rolled back.")
        else:
            db.commit()
            print("Import committed.")
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


DEFAULT_FILE = ROOT / "CN230 Petrolium Data" / "TGO_2569_Emission_Factor_Petroleum_Fuels.xlsx"
COLUMNS = ("factor_id", "product_id", "unit_id", "factor_value", "activity_type", "basis")
PRODUCTS = {
    "PROD-NG": ("Natural Gas", "ก๊าซธรรมชาติ"),
    "PROD-LPG": ("LPG",),
    "PROD-HC-GAS": ("Hydrocarbon Gas",),
    "PROD-FO": ("Fuel Oil",),
    "PROD-KER": ("Kerosene",),
    "PROD-DSL": ("Diesel",),
    "PROD-GSL": ("Gasoline",),
}
UNITS = {
    "UNIT-SCF": ("SCF", "standard cubic foot"),
    "UNIT-MJ": ("MJ", "megajoule"),
    "UNIT-MMBTU": ("MMBtu", "million British thermal units"),
    "UNIT-LITER": ("liter", "litre"),
    "UNIT-KG": ("kg", "kilogram"),
}


def normalized(value):
    return str(value).strip().casefold()


def read_emission_records(path):
    """Validate the entire sheet before any database writes; do not guess values."""
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        if "MySQL_Import_Ready" not in workbook.sheetnames:
            raise ValueError("Missing worksheet MySQL_Import_Ready")
        sheet = workbook["MySQL_Import_Ready"]
        rows = sheet.iter_rows(values_only=True)
        if tuple(next(rows, ())) != COLUMNS:
            raise ValueError(f"Expected exactly these Excel columns: {', '.join(COLUMNS)}")
        records, seen = [], set()
        for line, row in enumerate(rows, 2):
            if all(v is None for v in row):
                continue
            values = [v.strip() if isinstance(v, str) else v for v in row]
            for index, limit in ((0, 50), (1, 50), (2, 50), (4, 100), (5, 100)):
                value = values[index]
                if not isinstance(value, str) or not value or len(value) > limit or value.startswith("="):
                    raise ValueError(f"Excel row {line}: invalid {COLUMNS[index]} (limit {limit})")
            if values[0] in seen:
                raise ValueError(f"Excel row {line}: duplicate factor_id {values[0]}")
            seen.add(values[0])
            if values[1] not in PRODUCTS or values[2] not in UNITS:
                raise ValueError(f"Excel row {line}: unrecognized product/unit code")
            try:
                if isinstance(values[3], bool):
                    raise InvalidOperation
                number = Decimal(str(values[3]))
                if not number.is_finite() or number < 0 or number >= 10000:
                    raise InvalidOperation
                if number != number.quantize(Decimal("0.000001")):
                    raise InvalidOperation
            except InvalidOperation as exc:
                raise ValueError(f"Excel row {line}: factor_value must fit DECIMAL(10,6) and be nonnegative") from exc
            values[3] = number
            records.append(tuple(values))
        if not records:
            raise ValueError("Excel sheet has no factor records")
        return records
    finally:
        workbook.close()


def resolve_reference(cur, table, code, aliases, stats, description=None):
    """Reuse an unambiguous semantic match, never assume a particular Pxx/Uxx ID."""
    key, label = ("product_id", "name") if table == "Product" else ("unit_id", "symbol")
    cur.execute(f"SELECT `{key}`, `{label}` FROM `{table}` FOR UPDATE")
    existing = cur.fetchall()
    allowed = {normalized(v) for v in aliases}
    matches = [row for row in existing if normalized(row[1]) in allowed]
    collision = [row for row in existing if normalized(row[0]) == normalized(code)]
    if collision and normalized(collision[0][1]) not in allowed:
        raise ValueError(f"{table}: ID {code} is already used for {collision[0][1]!r}")
    if len(matches) > 1:
        raise ValueError(f"{table}: ambiguous matching rows for {code}: {matches}")
    if matches:
        return matches[0][0]
    if table == "Product":
        cur.execute("INSERT INTO Product (product_id,name) VALUES (%s,%s)", (code, aliases[0]))
    else:
        cur.execute("INSERT INTO Unit (unit_id,symbol,description) VALUES (%s,%s,%s)",
                    (code, aliases[0], description))
    stats[f"{table} added"] += 1
    return code


def import_emission_records(db, records, apply=False):
    stats = Counter()
    # Share the CSV importer's advisory lock, so both imports cannot overlap.
    lock = "import_" + hashlib.sha256(db.database.encode("utf-8")).hexdigest()[:32]
    acquired = False
    try:
        with db.cursor() as cur:
            cur.execute("SELECT GET_LOCK(%s,10)", (lock,))
            acquired = cur.fetchone()[0] == 1
            if not acquired:
                raise RuntimeError("Another petroleum import is running")
            for table in ("Product", "Unit", "Emission_Factor"):
                cur.execute("SELECT ENGINE FROM information_schema.TABLES "
                            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s", (table,))
                row = cur.fetchone()
                if not row or row[0] != "InnoDB":
                    raise ValueError(f"{table}: expected an existing InnoDB table; run schema.sql first")
            cur.execute("SET SESSION sql_mode=CONCAT_WS(',',NULLIF(@@sql_mode,''),'STRICT_ALL_TABLES')")
            products, units = {}, {}
            for record in records:
                _, product, unit, *_ = record
                if product not in products:
                    products[product] = resolve_reference(cur, "Product", product, PRODUCTS[product], stats)
                if unit not in units:
                    symbol, description = UNITS[unit]
                    units[unit] = resolve_reference(cur, "Unit", unit, (symbol,), stats, description)
                mapped = (record[0], products[product], units[unit], *record[3:])
                cur.execute("SELECT product_id,unit_id,factor_value,activity_type,basis "
                            "FROM Emission_Factor WHERE factor_id=%s FOR UPDATE", (record[0],))
                previous = cur.fetchone()
                if previous is None:
                    cur.execute("INSERT INTO Emission_Factor "
                                "(factor_id,product_id,unit_id,factor_value,activity_type,basis) "
                                "VALUES (%s,%s,%s,%s,%s,%s)", mapped)
                    stats["factors added"] += 1
                elif previous == mapped[1:]:
                    stats["factors unchanged"] += 1
                else:
                    cur.execute("UPDATE Emission_Factor SET product_id=%s,unit_id=%s,factor_value=%s,"
                                "activity_type=%s,basis=%s WHERE factor_id=%s", (*mapped[1:], mapped[0]))
                    stats["factors updated"] += 1
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
                cur.execute("SELECT RELEASE_LOCK(%s)", (lock,))
                cur.fetchone()


def import_emission_main(argv=None):
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3308")))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "petroleum"))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Validate and rehearse all writes, then roll back")
    mode.add_argument("--apply", action="store_true", help="Insert/update factors by factor_id and commit")
    args = parser.parse_args(argv)
    records = read_emission_records(args.file)
    print(f"Excel validated: {len(records)} factors (total kgCO2e per fuel unit)")
    password = os.getenv("MYSQL_PASSWORD") or getpass.getpass("MySQL password: ")
    db = mysql.connector.connect(host=args.host, port=args.port, database=args.database,
                                 user=args.user, password=password, charset="utf8mb4", autocommit=False)
    try:
        stats = import_emission_records(db, records, apply=args.apply)
        for label, count in sorted(stats.items()):
            print(f"{label}: {count}")
        print("Import committed." if args.apply else "Dry run complete: rolled back.")
    finally:
        db.close()


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


def read_reserve_records(folder):
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


def import_reserve_records(db, records, apply=False):
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


def import_reserve_main(argv=None):
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
    args = parser.parse_args(argv)
    records = read_reserve_records(args.folder)
    write_review(args.report, records)
    print(f'Excel validated: {len(records)} reserve records; review: {args.report}')
    password = os.getenv('MYSQL_PASSWORD') or getpass.getpass('MySQL password: ')
    db = mysql.connector.connect(host=args.host, port=args.port, database=args.database,
                                 user=args.user, password=password, charset='utf8mb4', autocommit=False)
    try:
        for label, count in sorted(import_reserve_records(db, records, apply=args.apply).items()):
            print(f'{label}: {count}')
        print('Import committed.' if args.apply else 'Dry run complete: rolled back.')
    finally:
        db.close()

def main(argv=None):
    # Parse only the mode here; each importer validates its own remaining options.
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--type', choices=('csv', 'emission', 'reserve'), default='csv')
    args, remaining = parser.parse_known_args(argv)
    handlers = {
        'csv': import_csv_main,
        'emission': import_emission_main,
        'reserve': import_reserve_main,
    }
    return handlers[args.type](remaining)


if __name__ == '__main__':
    try:
        main()
    except (mysql.connector.Error, ValueError, RuntimeError, OSError) as exc:
        sys.exit(f'Import stopped: {exc}')
