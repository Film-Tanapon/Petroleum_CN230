"""SRS pages 7–8. Audits also run read-only on the team snapshot in test_acceptance."""
import pytest
from mysql.connector import Error
from tests.test_database import TABLES, insert, seed_parents

MONEY = [('Price_Monthly','unit_price'), ('Sale','royalty'), ('Sale','sale_value'),
         ('Emission_Factor','factor_value')]
VOLUMES = [('Production_Monthly','quantity'), ('Supply_Monthly','daily_rate'),
           ('Sale','volume_bbl'), ('Sale','volume_mmscf'), ('Reserve_Annual','proven_reserves')]
REFERENCES = {
    'BR-02': [('Price_Monthly', key, parent) for key, parent in
              [('field_id','Field'), ('product_id','Product'), ('unit_id','Unit')]],
    'BR-03': [(t,'product_id','Product') for t in
              ['Production_Monthly','Supply_Monthly','Reserve_Annual','Sale','Emission_Factor']],
    'BR-04': [('Reserve_Annual','block_id','Block')],
    'BR-05': [(t,'unit_id','Unit') for t in
              ['Emission_Factor','Supply_Monthly','Reserve_Annual','Production_Monthly']],
}
AUDITS = {
    'BR-01': """SELECT f.field_id FROM Field f WHERE NOT EXISTS (
                    SELECT 1 FROM Production_Monthly p JOIN Block b USING(block_id)
                    WHERE p.field_id=f.field_id)""",
    'BR-08': """SELECT field_id,product_id,unit_id,month,year FROM Price_Monthly
                GROUP BY field_id,product_id,unit_id,month,year HAVING COUNT(*)>1""",
    'BR-09': """SELECT production_id FROM Production_Monthly WHERE month NOT BETWEEN 1 AND 12
                OR production_days<0 OR production_days>DAY(LAST_DAY(
                STR_TO_DATE(CONCAT(year,'-',month,'-01'),'%Y-%c-%d')))""",
}
for rule, edges in REFERENCES.items():
    for child, col, parent in edges:
        AUDITS[f'{rule}/{child}/{col}'] = (
            f'SELECT c.{TABLES[child][0]} FROM {child} c LEFT JOIN {parent} p '
            f'ON c.{col}=p.{col} WHERE p.{col} IS NULL'
        )
for rule, measures in [('BR-06', MONEY), ('BR-07', VOLUMES)]:
    for table, col in measures:
        AUDITS[f'{rule}/{table}/{col}'] = f'SELECT {TABLES[table][0]} FROM {table} WHERE {col}<0'


def test_BR01_field_requires_one_real_block(cur):
    seed_parents(cur, 'Production_Monthly')
    cur.execute(AUDITS['BR-01'])
    assert cur.fetchall() == [(1,)]
    insert(cur, 'Production_Monthly', block_id=None)
    cur.execute(AUDITS['BR-01'])
    assert cur.fetchall() == [(1,)]
    insert(cur, 'Production_Monthly', production_id=2, block_id=1)
    cur.execute(AUDITS['BR-01'])
    assert cur.fetchall() == []


@pytest.mark.parametrize('rule,child,col,parent', [
    (rule,*edge) for rule,edges in REFERENCES.items() for edge in edges])
def test_BR02_to_BR05_missing_parent(cur, rule, child, col, parent):
    seed_parents(cur, child)
    insert(cur, child)
    cur.execute(AUDITS[f'{rule}/{child}/{col}'])
    assert cur.fetchall() == []
    with pytest.raises(Error) as exc:
        insert(cur, child, **{TABLES[child][0]:2, col:999})
    assert exc.value.errno == 1452


@pytest.mark.parametrize('table,col', MONEY + VOLUMES)
def test_BR06_BR07_negative_rejected_zero_allowed(cur, table, col):
    seed_parents(cur, table)
    insert(cur, table, **{col:0})
    with pytest.raises(Error) as exc:
        cur.execute(f'UPDATE {table} SET {col}=-1')
    assert exc.value.errno == 3819  # MySQL CHECK violation


def test_BR08_price_grain_excludes_currency(cur):
    seed_parents(cur,'Price_Monthly')
    insert(cur,'Price_Monthly')
    with pytest.raises(Error) as exc:
        insert(cur,'Price_Monthly',price_id=2,currency='USD')
    assert exc.value.errno == 1062
    insert(cur,'Price_Monthly',price_id=3,month=7)
    insert(cur,'Price_Monthly',price_id=4,year=2026)


@pytest.mark.parametrize('year,month,days,valid', [
    (2024,2,29,True),(2024,2,30,False),(2025,2,29,False),(2025,2,28,True),
    (2025,4,30,True),(2025,4,31,False),(2025,1,31,True),(2025,1,32,False),
    (2025,6,0,True),(2025,6,-1,False),(2025,0,1,False),(2025,13,1,False)])
def test_BR09_calendar(cur, year, month, days, valid):
    seed_parents(cur,'Production_Monthly')
    row = dict(year=year,month=month,production_days=days)
    if valid:
        insert(cur,'Production_Monthly',**row)
    else:
        with pytest.raises(Error) as exc:
            insert(cur,'Production_Monthly',**row)
        assert exc.value.errno == 3819
