from decimal import Decimal
import pytest
from scripts.reports import statements
from tests.test_database import insert


@pytest.fixture
def report(cur):
    for table in ('Field','Block','Product'):
        insert(cur,table)
    insert(cur,'Unit',symbol='BBLD')
    insert(cur,'Unit',unit_id=2,symbol='MMbbl')
    insert(cur,'Production_Monthly',month=1,quantity=10,oil_equivalent=10,production_days=2)
    insert(cur,'Production_Monthly',month=3,production_id=2,quantity=0,oil_equivalent=0)
    insert(cur,'Supply_Monthly',month=1,daily_rate=13)
    insert(cur,'Sale',month=1,sale_value=17,royalty=2,volume_bbl=7,
           volume_mmscf=None, energy_mmbtu=None)
    insert(cur,'Reserve_Annual',unit_id=2,proven_reserves=Decimal('0.0001'))
    def run(code, end=2025):
        sql, params = statements(2025,end,1,1)[code]
        cur.execute(sql,params)
        return cur.fetchall()
    return run


def test_FR01_activity_year_and_units(report,cur):
    insert(cur,'Supply_Monthly',supply_id=2,year=2024)
    assert sorted(report('FR-01')) == sorted([
        ('production',1,2025,1,'BBLD',10),('production',1,2025,3,'BBLD',0),
        ('supply',1,2025,1,'BBLD',13),('sale',1,2025,1,'bbl',7)])


def test_FR02_missing_month_year_and_zero(report,cur):
    insert(cur,'Field',field_id=2)
    insert(cur,'Production_Monthly',production_id=3,field_id=2,month=2,production_days=28)
    insert(cur,'Product',product_id=2)
    insert(cur,'Production_Monthly',production_id=4,product_id=2,month=2,production_days=28)
    expected={(year,month) for year in (2025,2026) for month in range(1,13)}
    assert set(report('FR-02',2026)) == expected-{(2025,1),(2025,3)}


def test_FR03_annual_totals_and_traceability(report,cur):
    insert(cur,'Block',block_id=2)
    insert(cur,'Production_Monthly',production_id=3,block_id=2,oil_equivalent=3,production_days=2)
    insert(cur,'Product',product_id=2)
    insert(cur,'Production_Monthly',product_id=2,production_id=4,block_id=None,oil_equivalent=None)
    assert set(report('FR-03')) == {
        (1,2025,1,0,20),(1,2025,2,0,6),(1,2025,None,1,26),
        (2,2025,None,0,None),(2,2025,None,1,None)}


def test_FR04_reserve_ratio_and_zero_output(report,cur):
    insert(cur,'Block',block_id=2)
    insert(cur,'Reserve_Annual',reserve_id=2,unit_id=2,block_id=2,proven_reserves=1)
    insert(cur,'Production_Monthly',production_id=3,block_id=2,quantity=0)
    assert set(report('FR-04')) == {
        (1,1,2025,'bbl',100,20,5),(1,2,2025,'bbl',1000000,0,None)}


def test_FR05_allocation_and_currency(report,cur):
    insert(cur,'Production_Monthly',production_id=3,month=1)  # same block twice
    insert(cur,'Sale',sale_id=2,month=1,currency='USD',sale_value=8,royalty=1)
    insert(cur,'Block',block_id=2)
    insert(cur,'Production_Monthly',production_id=4,month=3,block_id=2)
    insert(cur,'Sale',sale_id=3,month=3,sale_value=9,royalty=3)  # ambiguous
    insert(cur,'Sale',sale_id=4,month=5,sale_value=4,royalty=1)  # no mapping
    assert set(report('FR-05')) == {
        (1,2025,'THB',17,2),(1,2025,'USD',8,1),(None,2025,'THB',13,4)}

