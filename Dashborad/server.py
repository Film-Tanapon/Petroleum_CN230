"""Local read-only MySQL dashboard. Start: py -3.12 server.py"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import getpass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import mysql.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
QUERIES = {
    'sale': ('Sale', '''SELECT s.sale_id,s.product_id,s.field_id,s.year,s.month,
        COALESCE(f.name,s.field_id) field_name, COALESCE(p.name,s.product_id) product_name,
        s.volume_bbl,s.volume_mmscf,s.energy_mmbtu,s.sale_value,s.royalty,
        COALESCE(NULLIF(s.currency,''),'ไม่ระบุ') currency
        FROM Sale s LEFT JOIN Product p ON p.product_id=s.product_id
        LEFT JOIN Field f ON f.field_id=s.field_id ORDER BY s.year DESC,s.month DESC,s.sale_id'''),
    'production': ('Production_Monthly', '''SELECT s.production_id,s.product_id,s.field_id,
        s.block_id,s.unit_id,s.year,s.month,COALESCE(f.name,s.field_id) field_name,
        COALESCE(p.name,s.product_id) product_name,COALESCE(b.label,s.block_id) block,
        s.quantity,COALESCE(u.symbol,s.unit_id,'ไม่ระบุ') unit,s.oil_equivalent,s.production_days
        FROM Production_Monthly s LEFT JOIN Product p ON p.product_id=s.product_id
        LEFT JOIN Field f ON f.field_id=s.field_id LEFT JOIN Block b ON b.block_id=s.block_id
        LEFT JOIN Unit u ON u.unit_id=s.unit_id ORDER BY s.year DESC,s.month DESC,s.production_id'''),
    'supply': ('Supply_Monthly', '''SELECT s.supply_id,s.product_id,s.unit_id,s.year,s.month,
        COALESCE(p.name,s.product_id) product_name,s.area,s.daily_rate,
        COALESCE(u.symbol,s.unit_id,'ไม่ระบุ') unit FROM Supply_Monthly s
        LEFT JOIN Product p ON p.product_id=s.product_id LEFT JOIN Unit u ON u.unit_id=s.unit_id
        ORDER BY s.year DESC,s.month DESC,s.supply_id'''),
    'reserve': ('Reserve_Annual', '''SELECT s.reserve_id,s.product_id,s.block_id,s.unit_id,s.year,
        COALESCE(b.label,s.block_id) block,COALESCE(p.name,s.product_id) product_name,
        s.proven_reserves,COALESCE(u.symbol,s.unit_id,'ไม่ระบุ') unit
        FROM Reserve_Annual s LEFT JOIN Product p ON p.product_id=s.product_id
        LEFT JOIN Block b ON b.block_id=s.block_id LEFT JOIN Unit u ON u.unit_id=s.unit_id
        ORDER BY s.year DESC,s.reserve_id'''),
    'emission_factor': ('Emission_Factor', '''SELECT e.factor_id,e.product_id,e.unit_id,
        COALESCE(p.name,e.product_id) product_name,
        COALESCE(u.symbol,e.unit_id,'ไม่ระบุ') unit,e.factor_value,
        e.activity_type,e.basis
        FROM Emission_Factor e LEFT JOIN Product p ON p.product_id=e.product_id
        LEFT JOIN Unit u ON u.unit_id=e.unit_id
        ORDER BY e.factor_id'''),
}


def fetch_snapshot(settings):
    db = mysql.connector.connect(**settings, charset='utf8mb4', connection_timeout=10)
    try:
        db.start_transaction(readonly=True, consistent_snapshot=True,
                             isolation_level='REPEATABLE READ')
        datasets = {}
        for view, (table, sql) in QUERIES.items():
            with db.cursor(dictionary=True) as cursor:
                cursor.execute(sql)
                datasets[view] = {'rows': cursor.fetchall(), 'source': f'MySQL · {table}', 'rejected': 0}
        return {'datasets': datasets, 'loaded_at': datetime.now(timezone.utc).isoformat()}
    finally:
        db.rollback()
        db.close()


def json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f'Unsupported value type: {type(value).__name__}')


def database_error(error):
    code = getattr(error, 'errno', None)
    messages = {
        1045: 'MySQL ปฏิเสธการเข้าสู่ระบบ ตรวจ MYSQL_USER และ MYSQL_PASSWORD ใน .env',
        1049: 'ไม่พบฐานข้อมูล ตรวจ MYSQL_DATABASE ใน .env',
        2003: 'เชื่อม MySQL ไม่ได้ ตรวจว่า Docker ทำงานและ MYSQL_HOST / MYSQL_PORT ถูกต้อง',
        2005: 'ไม่พบโฮสต์ MySQL ตรวจ MYSQL_HOST',
        1054: 'คอลัมน์ฐานข้อมูลไม่ตรงกับ schema ของทีม ตรวจตาราง Sale, Production_Monthly, Supply_Monthly และ Reserve_Annual',
        1146: 'ไม่พบตารางที่ dashboard ต้องใช้ ตรวจชื่อฐานข้อมูลและชื่อตาราง',
        1142: 'บัญชี MySQL ไม่มีสิทธิ์ SELECT ตารางที่ต้องใช้',
    }
    return {'error': messages.get(code, 'อ่านข้อมูล MySQL ไม่สำเร็จ ตรวจบริการฐานข้อมูลและการเชื่อมต่อ'),
            'code': code}


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, mime):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/data':
            # Credentials stay in this process. The browser receives only report rows.
            try:
                result = fetch_snapshot(self.server.db_settings)
                body = json.dumps(result, ensure_ascii=False, default=json_value).encode('utf8')
                self.reply(200, body, 'application/json; charset=utf-8')
            except mysql.connector.Error as exc:
                body = json.dumps(database_error(exc), ensure_ascii=False).encode('utf8')
                self.reply(503, body, 'application/json; charset=utf-8')
            return
        files = {'/': ('index.html', 'text/html'), '/index.html': ('index.html', 'text/html'),
                 '/dashboard.js': ('dashboard.js', 'text/javascript'),
                 '/carbon': ('carbon.html', 'text/html'),
                 '/carbon.js': ('carbon.js', 'text/javascript'),
                 '/carbon-math.js': ('carbon-math.js', 'text/javascript')}
        files['/volume-math.js'] = ('volume-math.js', 'text/javascript')
        files['/boe-math.js'] = ('boe-math.js', 'text/javascript')
        if path not in files:
            self.reply(404, b'Not found', 'text/plain')
            return
        name, mime = files[path]
        self.reply(200, (ROOT / name).read_bytes(), mime + '; charset=utf-8')


def main():
    load_dotenv(ROOT.parent / '.env', override=False, encoding='utf-8-sig', interpolate=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=int(os.getenv('DASHBOARD_PORT', '8000')))
    args = parser.parse_args()
    password = os.environ.get('MYSQL_PASSWORD') or getpass.getpass('MySQL password: ')
    settings = {'host': os.getenv('MYSQL_HOST', '127.0.0.1'),
                'port': int(os.getenv('MYSQL_PORT', '3308')),
                'database': os.getenv('MYSQL_DATABASE', 'petroleum'),
                'user': os.getenv('MYSQL_USER', 'root'), 'password': password}
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.db_settings = settings
    print(f'Open http://127.0.0.1:{args.port} in your browser. Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
