"""Rebuild the ten CN230 project tables from the petroleum CSV folder, in one transaction.
Install: py -m pip install mysql-connector-python
Usage:   py import_data.py --database petroleum --dry-run
"""
import argparse
import csv
import getpass
import hashlib
import io
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import mysql.connector

DEFAULT_FOLDER = Path(r"C:\Users\User\Downloads\CN230 Petrolium Data\CN230 Petrolium Data")
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


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
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
    return p.parse_args()


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


def main():
    args = parse_args()
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


if __name__=="__main__":
    try:
        main()
    except (mysql.connector.Error,ValueError,RuntimeError,OSError) as error:
        sys.exit(f"Import stopped: {error}")
