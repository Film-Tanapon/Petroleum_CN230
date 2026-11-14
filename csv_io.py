"""CSV interchange for domestic supply. UTF-8 with BOM for Excel, DECIMAL values kept as text in transit."""
import csv
from pathlib import Path
from test_database import TABLES

COLUMNS=TABLES['Supply_Monthly']


def export_supply(cur,path):
    cur.execute('SELECT '+','.join(COLUMNS)+' FROM Supply_Monthly ORDER BY supply_id')
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(cur.fetchall())


def import_supply(cur,path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise ValueError('Unexpected CSV header')
        sql='INSERT INTO Supply_Monthly ('+','.join(COLUMNS)+') VALUES ('+','.join(['%s']*len(COLUMNS))+')'
        for row in reader:
            values=[None if row[k]=='' and k=='daily_rate' else row[k] for k in COLUMNS]
            cur.execute(sql,values)
