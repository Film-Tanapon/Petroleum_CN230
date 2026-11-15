"""Import the MySQL_Import_Ready Excel sheet without clearing existing tables."""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import getpass
import hashlib
import os
from pathlib import Path
import sys

import mysql.connector
from dotenv import load_dotenv
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent
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


def read_records(path):
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


def import_records(db, records, apply=False):
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


def main():
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
    args = parser.parse_args()
    records = read_records(args.file)
    print(f"Excel validated: {len(records)} factors (total kgCO2e per fuel unit)")
    password = os.getenv("MYSQL_PASSWORD") or getpass.getpass("MySQL password: ")
    db = mysql.connector.connect(host=args.host, port=args.port, database=args.database,
                                 user=args.user, password=password, charset="utf8mb4", autocommit=False)
    try:
        stats = import_records(db, records, apply=args.apply)
        for label, count in sorted(stats.items()):
            print(f"{label}: {count}")
        print("Import committed." if args.apply else "Dry run complete: rolled back.")
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except (mysql.connector.Error, ValueError, RuntimeError, OSError) as exc:
        sys.exit(f"Import stopped: {exc}")
