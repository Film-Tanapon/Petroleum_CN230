"""Section 6 acceptance checks for the deployed petroleum database."""
import getpass
import os
import time
import uuid

import mysql.connector as mysql
import pytest

from reports import statements
from test_business import AUDITS
from test_database import TABLES


def connect(user, password):
    return mysql.connect(host=os.getenv("MYSQL_HOST", "127.0.0.1"),
                         port=int(os.getenv("MYSQL_PORT", "3308")),
                         database=os.getenv("MYSQL_DATABASE", "petroleum"),
                         user=user, password=password, charset="utf8mb4")


@pytest.fixture(scope="session")
def db():
    user = os.getenv("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD")
    if password is None:
        password = getpass.getpass(f"MySQL password for {user}: ")
    conn = connect(user, password)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def live(db):
    db.start_transaction(readonly=True)
    try:
        with db.cursor() as c:
            yield c
    finally:
        db.rollback()


ORDER = ["Product", "Field", "Unit", "Block", "Production_Monthly", "Supply_Monthly",
         "Reserve_Annual", "Sale", "Price_Monthly", "Emission_Factor"]


@pytest.mark.parametrize("table", ORDER, ids=[f"DR-{n:02}" for n in range(1, 11)])
def test_DR_columns_and_primary_key(live, table):
    live.execute("SELECT column_name,column_key FROM information_schema.columns "
                 "WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    columns = dict(live.fetchall())
    assert not (missing := set(TABLES[table]) - columns.keys()), (table, missing)
    assert [col for col, key in columns.items() if key == "PRI"] == [TABLES[table][0]]


@pytest.mark.parametrize("rule", AUDITS, ids=[
    f"Q{int(key[3:5])+5:02}-{key}" for key in AUDITS])
def test_BR_audit(live, rule, record_property):
    table = (rule.split("/")[1] if "/" in rule else
             {"BR-01": "Field", "BR-08": "Price_Monthly", "BR-09": "Production_Monthly"}[rule])
    live.execute(f"SELECT 1 FROM `{table}` LIMIT 1")
    if not live.fetchone():
        pytest.skip(f"No records in {table}")
    live.execute("SELECT COUNT(*) FROM (" + AUDITS[rule] + ") violations")
    count, = live.fetchone()
    record_property("offending_rows_or_groups", count)
    if count:
        live.execute(AUDITS[rule] + " LIMIT 5")
        pytest.fail(f"{count} violations, example keys: {live.fetchall()}")


@pytest.mark.parametrize("n", range(1, 6), ids=[f"Q{i:02}-FR-{i:02}" for i in range(1, 6)])
def test_FR_team_report_and_time(live, n, record_property):
    live.execute("SELECT MIN(year), MAX(year) FROM Production_Monthly")
    lo, hi = live.fetchone()
    live.execute("SELECT field_id, product_id FROM Production_Monthly WHERE field_id IS NOT NULL "
                 "AND product_id IS NOT NULL ORDER BY field_id,product_id LIMIT 1")
    pair = live.fetchone()
    if not pair or lo is None:
        pytest.skip("Missing production data for the report parameters")
    if n == 4:
        live.execute("SELECT 1 FROM Reserve_Annual LIMIT 1")
        if not live.fetchone():
            pytest.skip("Q04 needs annual reserve data")
    sql, args = statements(lo, hi, *pair)[f"FR-{n:02}"]
    if n == 3:
        live.execute("EXPLAIN " + sql, args)
        record_property("Q03_EXPLAIN", repr(live.fetchall()))
    start = time.perf_counter()
    live.execute(sql, args)
    rows = live.fetchall()
    elapsed = time.perf_counter() - start
    record_property("rows", len(rows))
    record_property("seconds", elapsed)
    record_property("sample", repr(rows[:3]))
    record_property("parameters", repr(args))
    if n != 2:
        assert rows, "Report returned no rows"
    if n == 2:
        live.execute("SELECT DISTINCT year,month FROM Production_Monthly WHERE field_id=%s "
                     "AND product_id=%s AND year BETWEEN %s AND %s", (*pair, lo, hi))
        expected = {(y,m) for y in range(lo, hi+1) for m in range(1,13)}
        assert set(rows) == expected - set(live.fetchall())
    assert elapsed <= 2, f"NFR-02: {elapsed:.3f}s > 2s"


@pytest.fixture
def probe(db):
    if os.getenv("SECTION6_WRITE_PROBES") != "1":
        pytest.skip("Set SECTION6_WRITE_PROBES=1 for rollback-only negative tests")
    with db.cursor() as c:
        c.execute("SELECT table_name,engine FROM information_schema.tables WHERE table_schema=DATABASE()")
        engines = {name.lower(): engine for name, engine in c.fetchall()}
        assert all(engines.get(t.lower()) == "InnoDB" for t in ORDER), "Transactional tables required"
        db.rollback()
        db.start_transaction()
        try:
            yield c
        finally:
            db.rollback()


@pytest.mark.parametrize("table,column", [("Price_Monthly","unit_price"),("Production_Monthly","quantity")])
def test_negative_update(probe, table, column):
    pk = TABLES[table][0]
    probe.execute(f"SELECT {pk} FROM {table} LIMIT 1")
    row = probe.fetchone()
    if not row:
        pytest.skip(f"No {table} record to update")
    with pytest.raises(mysql.Error) as exc:
        probe.execute(f"UPDATE {table} SET {column}=-1 WHERE {pk}=%s", row)
    assert exc.value.errno in (3819, 1644), str(exc.value)


@pytest.mark.parametrize("table,expected", [("Sale",1452),("Price_Monthly",1062)])
def test_negative_insert(probe, table, expected):
    cols = TABLES[table]
    probe.execute("SELECT " + ",".join(cols) + f" FROM {table} WHERE " +
                  " AND ".join(c+" IS NOT NULL" for c in
                  (["product_id"] if table=="Sale" else ["field_id","product_id","unit_id","month","year"])) +
                  " LIMIT 1")
    row = probe.fetchone()
    if not row:
        pytest.skip(f"No usable {table} record to copy")
    values = list(row)
    values[0] = "T" + uuid.uuid4().hex
    if table == "Sale":
        values[1] = "missing" + uuid.uuid4().hex
    with pytest.raises(mysql.Error) as exc:
        probe.execute(f"INSERT INTO {table} (" + ",".join(cols) + ") VALUES (" +
                      ",".join(["%s"]*len(cols)) + ")", values)
    assert exc.value.errno == expected, str(exc.value)


def test_T03_deployed_reader():
    user = os.getenv("MYSQL_READER_USER")
    if not user:
        pytest.skip("Set MYSQL_READER_USER to test the deployed reader")
    password = os.environ.get("MYSQL_READER_PASSWORD")
    conn = connect(user, password if password is not None else getpass.getpass("Reader password: "))
    try:
        with conn.cursor() as c:
            c.execute("SELECT product_id FROM Product LIMIT 1")
            c.fetchall()
            for sql in ("INSERT INTO Product(product_id,name) SELECT 'T','Test' WHERE FALSE",
                        "UPDATE Product SET name=name WHERE FALSE", "DELETE FROM Product WHERE FALSE"):
                with pytest.raises(mysql.Error) as exc:
                    c.execute(sql)
                assert exc.value.errno in (1142,1143), str(exc.value)
    finally:
        conn.rollback()
        conn.close()

