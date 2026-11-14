"""Run from the host after docker compose up -d mysql-test. Uses only the Python standard library."""
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parent
COMPOSE=['docker','compose','-p','cn230-section6','-f',str(ROOT/'compose.test.yaml')]


def run_ops(invoke,restart):
    # Each invocation owns a fresh source and restore DB, so previous dumps cannot satisfy the test.
    tag=uuid.uuid4().hex[:12]
    source='cn230_ops_'+tag
    restore='cn230_restore_'+tag

    def sql(statement,database=None):
        args=['--batch','--skip-column-names']
        if database:
            args.append(database)
        return invoke('mysql',args,statement.encode('utf-8')).strip()

    def dump(database,data_only=False):
        args=['--single-transaction','--skip-dump-date','--order-by-primary',
              '--hex-blob','--no-tablespaces','--set-gtid-purged=OFF']
        if data_only:
            args.extend(['--no-create-info','--compact'])
        return invoke('mysqldump',args+[database],None)

    created=[]
    try:
        for name in (source,restore):
            sql('CREATE DATABASE '+name+' CHARACTER SET utf8mb4')
            created.append(name)
        invoke('mysql',[source],(ROOT/'schema.sql').read_bytes())
        sql("""START TRANSACTION;
            INSERT INTO Product(product_id,name) VALUES (91,'เก่า'),(92,'old'),(93,'delete');
            INSERT INTO Unit(unit_id,symbol,description) VALUES(91,'BBLD','barrels/day');
            INSERT INTO Supply_Monthly(supply_id,product_id,unit_id,area,daily_rate,month,year)
            VALUES(91,91,91,'ในประเทศ',12.34567890,4,2024);
            UPDATE Product SET name='แก้ไขล่าสุด' WHERE product_id=92;
            DELETE FROM Product WHERE product_id=93;
            COMMIT;""",source)
        expected=sql('SELECT product_id,name FROM Product ORDER BY product_id',source)
        assert 'แก้ไขล่าสุด'.encode() in expected and b'93' not in expected
        restart()
        assert sql('SELECT product_id,name FROM Product ORDER BY product_id',source)==expected
        print('PASS NFR-01 committed data survives a server restart')
        snapshot=dump(source)
        invoke('mysql',[restore],snapshot)
        sql('DROP TABLE Supply_Monthly',restore)
        assert not sql("SHOW TABLES LIKE 'Supply_Monthly'",restore)
        invoke('mysql',[restore],snapshot)
        assert sql('SHOW TABLES',source)==sql('SHOW TABLES',restore)
        assert dump(source,True)==dump(restore,True)
        assert sql('SELECT product_id,name FROM Product ORDER BY product_id',restore)==expected
        print('PASS NFR-03 SQL dump restores the latest committed insert, update and delete')
    finally:
        for name in created:
            sql('DROP DATABASE '+name)


def main():
    def invoke(tool,args,data):
        cmd=COMPOSE+['exec','-T','-e','MYSQL_PWD=test_root_password','mysql-test',
                     tool,'-uroot','--default-character-set=utf8mb4',*args]
        return subprocess.run(cmd,input=data,stdout=subprocess.PIPE,check=True).stdout

    def restart():
        subprocess.run(COMPOSE+['restart','mysql-test'],check=True)
        for _ in range(60):
            try:
                invoke('mysql',['-e','SELECT 1'],None)
                return
            except subprocess.CalledProcessError:
                time.sleep(1)
        raise RuntimeError('MySQL unavailable after restart')

    run_ops(invoke,restart)


if __name__=='__main__':
    main()

