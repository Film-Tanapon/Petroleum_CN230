"""Export the CN230 MySQL database as UTF-8 Cypher for Neo4j 5.x / cypher-shell."""
import argparse
from datetime import date, datetime
from decimal import Decimal
import getpass
import json
import os
from pathlib import Path
import tempfile

import mysql.connector

# Parent tables must appear before their children.
MODEL = {
    "Product": ("product_id", {}),
    "Field": ("field_id", {}),
    "Block": ("block_id", {}),
    "Unit": ("unit_id", {}),
    "Production_Monthly": ("production_id", {
        "product_id": ("OF_PRODUCT", "Product"), "field_id": ("FROM_FIELD", "Field"),
        "block_id": ("IN_BLOCK", "Block"), "unit_id": ("MEASURED_IN", "Unit")}),
    "Supply_Monthly": ("supply_id", {
        "product_id": ("OF_PRODUCT", "Product"), "unit_id": ("MEASURED_IN", "Unit")}),
    "Reserve_Annual": ("reserve_id", {
        "product_id": ("OF_PRODUCT", "Product"), "block_id": ("IN_BLOCK", "Block"),
        "unit_id": ("MEASURED_IN", "Unit")}),
    "Sale": ("sale_id", {
        "product_id": ("OF_PRODUCT", "Product"), "field_id": ("FROM_FIELD", "Field")}),
    "Price_Monthly": ("price_id", {
        "product_id": ("OF_PRODUCT", "Product"), "field_id": ("FROM_FIELD", "Field"),
        "unit_id": ("PRICED_PER", "Unit")}),
    "Emission_Factor": ("factor_id", {
        "product_id": ("OF_PRODUCT", "Product"), "unit_id": ("PER_UNIT", "Unit")}),
}


def ident(name):
    return "`" + name.replace("`", "``") + "`"


def literal(value):
    if isinstance(value, Decimal):
        value = format(value, "f")  # Neo4j has no fixed-point DECIMAL type.
    if isinstance(value, (date, datetime)):
        value = value.isoformat()
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def export(db, target):
    directory = target.resolve().parent
    report = []
    tmp = None
    try:
        db.start_transaction(isolation_level="REPEATABLE READ", consistent_snapshot=True, readonly=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=directory, delete=False) as out:
            tmp = Path(out.name)
            out.write("// CN230 petroleum snapshot. Use an empty Neo4j database for a full refresh.\n")
            for table, (pk, _) in MODEL.items():
                out.write(f"CREATE CONSTRAINT {ident('cn230_'+table+'_pk')} IF NOT EXISTS "
                          f"FOR (n:{ident(table)}) REQUIRE n.{ident(pk)} IS UNIQUE;\n")

            for table, (pk, links) in MODEL.items():
                with db.cursor() as cur:
                    cur.execute(f"SELECT * FROM {ident(table)} ORDER BY {ident(pk)}")
                    columns = list(cur.column_names)
                    missing = {pk, *links} - set(columns)
                    if missing:
                        raise ValueError(f"{table} missing columns: {sorted(missing)}")
                    count = edges = 0
                    while rows := cur.fetchmany(300):
                        maps = ["{" + ", ".join(f"{ident(c)}: {literal(v)}" for c,v in zip(columns,row)) + "}"
                                for row in rows]
                        out.write("UNWIND [\n" + ",\n".join(maps) + "\n] AS row\n")
                        out.write(f"MERGE (n:{ident(table)} {{{ident(pk)}: row.{ident(pk)}}})\nSET n += row")
                        # Independent subqueries preserve records with optional / missing FK.
                        for fk, (rel, parent) in links.items():
                            parent_pk = MODEL[parent][0]
                            out.write(f"\nCALL {{\n  WITH n, row\n  MATCH (p:{ident(parent)} "
                                      f"{{{ident(parent_pk)}: row.{ident(fk)}}})\n"
                                      f"  MERGE (n)-[:{rel}]->(p)\n}}")
                            edges += sum(row[columns.index(fk)] is not None for row in rows)
                        out.write(";\n")
                        count += len(rows)
                    report.append((table,count,edges))
        db.commit()
        tmp.replace(target)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    for table, count, edges in report:
        print(f"{table}: {count:,} rows, {edges:,} non-NULL references")
    print(f"Written: {target.resolve()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3308)
    parser.add_argument("--database", default="petroleum")
    parser.add_argument("--user", default="root")
    parser.add_argument("--out", type=Path, default=Path("petroleum.cypher"))
    args = parser.parse_args()
    db = mysql.connector.connect(host=args.host, port=args.port, database=args.database,
                                 user=args.user, charset="utf8mb4",
                                 password=os.getenv("MYSQL_PASSWORD") or getpass.getpass("MySQL password: "))
    try:
        export(db, args.out)
    finally:
        db.close()


if __name__ == "__main__":
    main()
