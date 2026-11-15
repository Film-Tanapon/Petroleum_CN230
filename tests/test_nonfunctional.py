import os
from decimal import Decimal
import mysql.connector
from mysql.connector import Error
import pytest
from scripts.csv_io import export_supply, import_supply
from tests.test_database import insert, TABLES


def connect(user,password):
    return mysql.connector.connect(host=os.getenv('MYSQL_TEST_HOST','mysql-test'),
        port=int(os.getenv('MYSQL_TEST_PORT','3306')),database='cn230_test',
        user=user,password=password,charset='utf8mb4')


def test_NFR01_rollback_after_failed_related_write(connection,cur):
    insert(cur,'Product')
    insert(cur,'Unit')
    with pytest.raises(Error) as exc:
        insert(cur,'Supply_Monthly',product_id=999)
    assert exc.value.errno == 1452
    connection.rollback()
    for table in ['Product','Unit','Supply_Monthly']:
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        assert cur.fetchone()==(0,)


def test_NFR01_isolation_and_committed_visibility(connection,cur):
    observer=connect(os.getenv('MYSQL_TEST_USER','tester'),os.getenv('MYSQL_TEST_PASSWORD','test_password'))
    try:
        observer.autocommit=True
        with observer.cursor() as other:
            insert(cur,'Product',product_id=776)
            other.execute('SELECT COUNT(*) FROM Product WHERE product_id=776')
            assert other.fetchone()==(0,)
            connection.commit()
            other.execute('SELECT COUNT(*) FROM Product WHERE product_id=776')
            assert other.fetchone()==(1,)
    finally:
        observer.close()
        cur.execute('DELETE FROM Product WHERE product_id=776')
        connection.commit()


def test_NFR04_admin_crud(cur):
    insert(cur,'Product')
    cur.execute("UPDATE Product SET name='updated' WHERE product_id=1")
    cur.execute('SELECT name FROM Product WHERE product_id=1')
    assert cur.fetchall()==[('updated',)]
    cur.execute('DELETE FROM Product WHERE product_id=1')
    assert cur.rowcount==1


@pytest.mark.parametrize('table',TABLES)
def test_NFR04_reader_can_read_but_cannot_write(table):
    db=connect(os.getenv('MYSQL_READER_USER','reader'),os.getenv('MYSQL_READER_PASSWORD','read_test'))
    pk=TABLES[table][0]
    try:
        with db.cursor() as c:
            c.execute(f'SELECT {pk} FROM {table} LIMIT 1')
            c.fetchall()
            for sql in [f'INSERT INTO {table} ({pk}) VALUES (888)',
                        f'UPDATE {table} SET {pk}={pk} WHERE 1=0',
                        f'DELETE FROM {table} WHERE 1=0']:
                with pytest.raises(Error) as exc:
                    c.execute(sql)
                assert exc.value.errno in (1142,1143), sql
    finally:
        db.rollback()
        db.close()


def test_NFR05_utf8_csv_export_and_reimport(cur,tmp_path):
    insert(cur,'Unit')
    insert(cur,'Product')
    label='ในประเทศ, "Thailand"'
    quantity=Decimal('1234567890.12345678')
    insert(cur,'Supply_Monthly',area=label,daily_rate=quantity)
    insert(cur,'Supply_Monthly',supply_id=2,daily_rate=None)
    path=tmp_path/'supply.csv'
    export_supply(cur,path)
    assert label.split(',')[0] in path.read_text(encoding='utf-8-sig')
    cur.execute('DELETE FROM Supply_Monthly')
    import_supply(cur,path)
    cur.execute('SELECT area,daily_rate FROM Supply_Monthly ORDER BY supply_id')
    assert cur.fetchall()==[(label,quantity),('Domestic',None)]


def test_T01_second_writer_waits_for_first(connection, cur):
    """1205 proves a lock wait, and a retry proves release by connection one."""
    other = connect(os.getenv('MYSQL_TEST_USER', 'tester'), os.getenv('MYSQL_TEST_PASSWORD', 'test_password'))
    try:
        insert(cur, 'Product', product_id=779)
        connection.commit()
        cur.execute("UPDATE Product SET name='holder' WHERE product_id=779")
        with other.cursor() as c:
            c.execute("SET SESSION innodb_lock_wait_timeout=1")
            with pytest.raises(Error) as exc:
                c.execute("UPDATE Product SET name='second' WHERE product_id=779")
            assert exc.value.errno == 1205
            other.rollback()
            connection.commit()
            c.execute("UPDATE Product SET name='second' WHERE product_id=779")
            assert c.rowcount == 1
            other.commit()
        cur.execute("SELECT name FROM Product WHERE product_id=779")
        assert cur.fetchone() == ('second',)
    finally:
        other.close()
        connection.rollback()
        cur.execute("DELETE FROM Product WHERE product_id=779")
        connection.commit()
