import pandas as pd
from sqlalchemy import create_engine

engine = create_engine('mysql+pymysql://root:Qwerty4321@localhost:3308/petroleum?charset=utf8mb4')

master_tables = ['Product', 'Field', 'Block', 'Unit']

print("=================== สรุปข้อมูล Master Tables ===================")
for table in master_tables:
    df = pd.read_sql_query(f"SELECT * FROM `{table}` LIMIT 5;", engine)
    count = pd.read_sql_query(f"SELECT COUNT(*) as cnt FROM `{table}`;", engine)['cnt'][0]
    print(f"\n📌 ตาราง: {table} (รวม {count} แถว)")
    print(df.to_string(index=False))