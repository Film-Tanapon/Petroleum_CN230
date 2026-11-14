"""Regression tests for Petroleum.png. Run against an empty disposable cn230_test database."""
import os

import mysql.connector
import pytest
from mysql.connector import IntegrityError


# The first column is the expected single-column primary key.
TABLES = {
    "Product": "product_id name".split(),
    "Field": "field_id name".split(),
    "Block": "block_id label".split(),
    "Unit": "unit_id symbol description".split(),
    "Emission_Factor": "factor_id product_id unit_id factor_value activity_type basis".split(),
    "Supply_Monthly": "supply_id product_id unit_id area daily_rate month year".split(),
    "Reserve_Annual": "reserve_id product_id block_id unit_id proven_reserves year".split(),
    "Price_Monthly": "price_id product_id field_id unit_id unit_price currency month year".split(),
    "Sale": "sale_id product_id field_id volume_bbl volume_mmscf energy_mmbtu sale_value royalty currency month year".split(),
    "Production_Monthly": "production_id product_id field_id block_id unit_id quantity oil_equivalent production_days year month".split(),
}
PARENTS = {"product_id": "Product", "field_id": "Field", "block_id": "Block", "unit_id": "Unit"}
LINKS = [
    (table, column, PARENTS[column])
    for table, columns in TABLES.items()
    for column in columns[1:]
    if column in PARENTS
]
TEXT = {
    "name": "Test", "label": "B1", "symbol": "bbl", "description": "Barrel",
    "activity_type": "production", "basis": "test", "area": "Domestic", "currency": "THB",
}
SAMPLES = {"month": 6, "year": 2025, "production_days": 30, **TEXT}


@pytest.fixture(scope="session")
def connection():
    db = mysql.connector.connect(
        host=os.getenv("MYSQL_TEST_HOST", "mysql-test"),
        port=int(os.getenv("MYSQL_TEST_PORT", "3306")),
        database="cn230_test", user=os.getenv("MYSQL_TEST_USER", "tester"),
        password=os.getenv("MYSQL_TEST_PASSWORD", "test_password"),
        autocommit=False,
    )
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def cur(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        connection.rollback()
        cursor.close()


def insert(cur, table, **overrides):
    columns = TABLES[table]
    values = [overrides.get(c, SAMPLES.get(c, 1)) for c in columns]
    names = ", ".join(f"`{c}`" for c in columns)
    markers = ", ".join(["%s"] * len(columns))
    cur.execute(f"INSERT INTO `{table}` ({names}) VALUES ({markers})", values)


def seed_parents(cur, table):
    for child, _, parent in LINKS:
        if child == table:
            insert(cur, parent)


@pytest.mark.parametrize("table", TABLES)
def test_columns_and_primary_key(cur, table):
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", (table,),
    )
    missing = set(TABLES[table]) - {row[0] for row in cur.fetchall()}
    assert not missing, f"{table} missing columns: {sorted(missing)}"
    cur.execute(
        "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "AND CONSTRAINT_NAME = 'PRIMARY' ORDER BY ORDINAL_POSITION", (table,),
    )
    assert cur.fetchall() == [(TABLES[table][0],)]


@pytest.mark.parametrize("table", TABLES)
def test_insert_and_read_back(cur, table):
    seed_parents(cur, table)
    insert(cur, table)
    pk = TABLES[table][0]
    cur.execute(f"SELECT `{pk}` FROM `{table}` WHERE `{pk}` = 1")
    assert cur.fetchall() == [(1,)]


@pytest.mark.parametrize("child,column,parent", LINKS)
def test_foreign_key_and_optionality(cur, child, column, parent):
    cur.execute(
        "SELECT k.REFERENCED_TABLE_NAME, k.REFERENCED_COLUMN_NAME, c.IS_NULLABLE "
        "FROM information_schema.KEY_COLUMN_USAGE k "
        "JOIN information_schema.COLUMNS c USING (TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME) "
        "WHERE k.TABLE_SCHEMA = DATABASE() AND k.TABLE_NAME = %s AND k.COLUMN_NAME = %s "
        "AND k.REFERENCED_TABLE_SCHEMA = DATABASE()", (child, column),
    )
    optional = child == "Production_Monthly" and column in {"field_id", "block_id"}
    rows = cur.fetchall()
    assert len(rows) == 1
    target, key, nullable = rows[0]
    cur.execute("SELECT @@lower_case_table_names")
    if cur.fetchone()[0]:
        assert target.casefold() == parent.casefold()
    else:
        assert target == parent
    assert key == TABLES[parent][0]
    assert nullable == ("YES" if optional else "NO")


@pytest.mark.parametrize("child,column,parent", LINKS)
def test_broken_reference_rejected(cur, child, column, parent):
    seed_parents(cur, child)
    with pytest.raises(IntegrityError) as error:
        insert(cur, child, **{column: 999})
    assert error.value.errno == 1452


@pytest.mark.parametrize("field_id,block_id", [(None, 1), (1, None), (None, None)])
def test_production_optional_links(cur, field_id, block_id):
    seed_parents(cur, "Production_Monthly")
    insert(cur, "Production_Monthly", field_id=field_id, block_id=block_id)
    cur.execute("SELECT field_id, block_id FROM Production_Monthly WHERE production_id = 1")
    assert cur.fetchone() == (field_id, block_id)


def test_product_primary_key_rejects_duplicate(cur):
    insert(cur, "Product", name="Test gas")
    with pytest.raises(IntegrityError) as error:
        insert(cur, "Product", name="Test oil")
    assert error.value.errno == 1062


def test_product_can_have_sales_in_two_months(cur):
    seed_parents(cur, "Sale")
    insert(cur, "Sale", sale_id=1, month=6)
    insert(cur, "Sale", sale_id=2, month=7)
    cur.execute("SELECT month FROM Sale WHERE product_id = 1 ORDER BY month")
    assert cur.fetchall() == [(6,), (7,)]
