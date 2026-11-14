"""Reference SQL for the SRS. Tests and benchmarks call the same statements.
Parameters are inclusive Gregorian years. FR-02 takes one expected field/product pair.
"""
FR01 = """
SELECT 'production' activity, p.product_id, p.year, p.month, u.symbol, p.quantity amount
FROM Production_Monthly p JOIN Unit u USING(unit_id)
WHERE p.year BETWEEN %s AND %s
UNION ALL
SELECT 'supply', s.product_id, s.year, s.month, u.symbol, s.daily_rate
FROM Supply_Monthly s JOIN Unit u USING(unit_id) WHERE s.year BETWEEN %s AND %s
UNION ALL
SELECT 'sale', product_id, year, month, 'bbl', volume_bbl FROM Sale
WHERE volume_bbl IS NOT NULL AND year BETWEEN %s AND %s
UNION ALL
SELECT 'sale', product_id, year, month, 'MMSCF', volume_mmscf FROM Sale
WHERE volume_mmscf IS NOT NULL AND year BETWEEN %s AND %s
UNION ALL
SELECT 'sale', product_id, year, month, 'MMBtu', energy_mmbtu FROM Sale
WHERE energy_mmbtu IS NOT NULL AND year BETWEEN %s AND %s
"""

FR02 = """
WITH RECURSIVE calendar(period) AS (
    SELECT CAST(CONCAT(%s,'-01-01') AS DATE)
    UNION ALL SELECT period + INTERVAL 1 MONTH FROM calendar
    WHERE period < CAST(CONCAT(%s,'-12-01') AS DATE)
)
SELECT YEAR(period), MONTH(period) FROM calendar
WHERE NOT EXISTS (
    SELECT 1 FROM Production_Monthly p WHERE p.field_id=%s AND p.product_id=%s
    AND p.year=YEAR(period) AND p.month=MONTH(period)
) ORDER BY period
"""

FR03 = """
SELECT product_id, year, block_id, GROUPING(block_id) AS annual_total,
       CASE WHEN COUNT(oil_equivalent * production_days) = COUNT(*)
            THEN SUM(oil_equivalent * production_days) END AS production_boe
FROM Production_Monthly WHERE year BETWEEN %s AND %s
GROUP BY product_id, year, block_id WITH ROLLUP
HAVING GROUPING(product_id)=0 AND GROUPING(year)=0
"""
# GROUPING(block_id) distinguishes the annual subtotal from an unknown block.

FR04 = """
WITH production AS (
    SELECT p.product_id,p.block_id,p.year,
           CASE UPPER(u.symbol) WHEN 'BBLD' THEN 'bbl' WHEN 'BBL/DAY' THEN 'bbl'
                WHEN 'MMSCFD' THEN 'mmscf' END AS base_unit,
           CASE WHEN COUNT(p.quantity * p.production_days)=COUNT(*)
                THEN SUM(p.quantity * p.production_days) END AS produced
    FROM Production_Monthly p JOIN Unit u USING(unit_id)
    WHERE p.year BETWEEN %s AND %s
    GROUP BY p.product_id,p.block_id,p.year,base_unit
), reserves AS (
    SELECT r.product_id,r.block_id,r.year,
           CASE UPPER(u.symbol) WHEN 'BBL' THEN 'bbl' WHEN 'MMBBL' THEN 'bbl'
                WHEN 'MMSCF' THEN 'mmscf' WHEN 'BCF' THEN 'mmscf' END AS base_unit,
           CASE WHEN COUNT(r.proven_reserves)=COUNT(*) THEN
               SUM(r.proven_reserves * CASE UPPER(u.symbol) WHEN 'MMBBL' THEN 1000000
                                        WHEN 'BCF' THEN 1000 ELSE 1 END) END AS reserve_qty
    FROM Reserve_Annual r JOIN Unit u USING(unit_id)
    WHERE r.year BETWEEN %s AND %s GROUP BY r.product_id,r.block_id,r.year,base_unit
)
SELECT r.product_id,r.block_id,r.year,r.base_unit,r.reserve_qty,p.produced,
       r.reserve_qty / NULLIF(p.produced,0) AS reserve_to_production
FROM reserves r LEFT JOIN production p USING(product_id,block_id,year,base_unit)
"""

FR05 = """
WITH attribution AS (
    SELECT field_id,product_id,year,month,
           CASE WHEN COUNT(DISTINCT block_id)=1 AND COUNT(block_id)=COUNT(*)
                THEN MIN(block_id) END AS block_id
    FROM Production_Monthly WHERE year BETWEEN %s AND %s
    GROUP BY field_id,product_id,year,month
)
SELECT a.block_id,s.year,s.currency,
       CASE WHEN COUNT(s.sale_value)=COUNT(*) THEN SUM(s.sale_value) END AS sales,
       CASE WHEN COUNT(s.royalty)=COUNT(*) THEN SUM(s.royalty) END AS royalty
FROM Sale s LEFT JOIN attribution a USING(field_id,product_id,year,month)
WHERE s.year BETWEEN %s AND %s GROUP BY a.block_id,s.year,s.currency
"""

def statements(start, end, field, product):
    years = (start, end)
    return {
        'FR-01': (FR01, years * 5),
        'FR-02': (FR02, (*years, field, product)),
        'FR-03': (FR03, years),
        'FR-04': (FR04, years * 2),
        'FR-05': (FR05, years * 2),
    }
