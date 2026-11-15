# Petroleum CN230

ระบบฐานข้อมูลปิโตรเลียม MySQL พร้อม Dashboard, Import CSV/Excel, Gemini RAG และส่งออก Cypher

## 1. เตรียมเครื่อง

ติดตั้ง **Docker Desktop** และ **Python 3.12** แล้วเปิด Docker Desktop
รันทุกคำสั่งใน **PowerShell ที่โฟลเดอร์รากของโปรเจกต์**

```powershell
py -3.12 -m pip install -r requirements.txt
```

ครั้งแรกคัดลอกไฟล์ตั้งค่า หากมี `.env` แล้วให้แก้ไฟล์เดิม:

```powershell
Copy-Item .env.example .env
notepad .env
```

ตั้ง `MYSQL_HOST=127.0.0.1`, `MYSQL_PORT=3308`, `MYSQL_DATABASE=petroleum`, `MYSQL_USER=root`
และตั้ง **MYSQL_PASSWORD กับ MYSQL_ROOT_PASSWORD ให้เป็นรหัสผ่านเดียวกัน**

## 2. รัน Docker และสร้างตารางครั้งแรก

```powershell
docker compose up -d
docker compose ps
docker compose logs -f db
```

รอ `ready for connections` แล้วกด `Ctrl+C` ออกจาก log จากนั้นสร้างฐานข้อมูลและตาราง:

```powershell
docker compose exec db mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS petroleum CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
$dbContainer = docker compose ps -q db
docker cp .\database\schema.sql "${dbContainer}:/tmp/petroleum-schema.sql"
docker compose exec db mysql -u root -p petroleum -e "source /tmp/petroleum-schema.sql"
```

ป้อน `MYSQL_ROOT_PASSWORD` เมื่อถูกถาม ขั้นสร้างตารางใช้กับฐานข้อมูลว่างครั้งแรกเท่านั้น หากมีตารางแล้วให้ข้าม

## 3. Import ข้อมูล

**รัน CSV → Emission Factor → Reserve ตามลำดับ** เพราะ CSV แบบ `--apply` ล้างข้อมูลเดิมทั้ง 10 ตาราง
`--dry-run` ทดลองแล้ว rollback ให้ตรวจผลก่อนรัน `--apply` เพื่อบันทึกจริง

```powershell
# 1) CSV
py -3.12 -m scripts.import_data --type csv --database petroleum --price-currency THB --dry-run
py -3.12 -m scripts.import_data --type csv --database petroleum --price-currency THB --apply

# 2) Emission Factor
py -3.12 -m scripts.import_data --type emission --dry-run
py -3.12 -m scripts.import_data --type emission --apply

# 3) Reserve Annual
py -3.12 -m scripts.import_data --type reserve --dry-run
py -3.12 -m scripts.import_data --type reserve --apply
```

- อ่านข้อมูลจาก `CN230 Petrolium Data/` อัตโนมัติ
- CSV ถามรหัสผ่านหากไม่มีตัวแปรแวดล้อม `MYSQL_PASSWORD`; โหมด Excel อ่าน `.env` ให้
- ตัวอย่างเลือก THB สกุลเดียวเพื่อให้ตรง unique key ของ schema
- ราคาก๊าซที่ไม่ยืนยันหน่วยจะถูกข้าม เพิ่ม `--gas-price-unit` เมื่อยืนยันหน่วยต้นทางแล้ว
- ตรวจแถวที่ข้ามใน `outputs/petroleum_import_review.csv` และรายงานปริมาณสำรองใน `outputs/reserve_import_review.csv`
- หากข้อมูลเกินช่วงตัวเลขของ schema โปรแกรมจะหยุดและ rollback ให้ตรวจข้อมูลก่อนรันใหม่

## 4. เปิด Dashboard

```powershell
py -3.12 Dashborad/server.py
```

เปิด [Dashboard](http://127.0.0.1:8000) หรือ [สถานการณ์คาร์บอน](http://127.0.0.1:8000/carbon)
รีเฟรชหลัง import และกด `Ctrl+C` เพื่อหยุด server
ค่าคาร์บอนเป็นสถานการณ์จำลอง ส่วนค่าพลังงานเทียบเท่าบางรายการใช้สมมติฐานที่ปรับได้ในหน้าเว็บ

## คำสั่งอื่น

### ค้นข้อมูล / Gemini RAG

```powershell
# สร้างดัชนีใหม่หลังเปลี่ยนข้อมูล MySQL
py -3.12 -m scripts.petroleum_rag build

# ค้นอย่างเดียว ไม่เรียก Gemini
py -3.12 -m scripts.petroleum_rag ask --question "ข้อมูลการจำหน่ายก๊าซธรรมชาติ" --table Sale --search-only

# ให้ Gemini ตอบจากหลักฐานที่ค้นพบ
py -3.12 -m scripts.petroleum_rag ask --question "ข้อมูลการผลิตน้ำมันดิบปี 2024" --table Production_Monthly --year 2024

# ดูโมเดล Gemini ที่บัญชีใช้ได้
py -3.12 -m scripts.petroleum_rag models
```

ครั้งแรกดาวน์โหลดโมเดล embedding ดัชนีอยู่ใน `outputs/petroleum_index.sqlite`
ตั้ง `GEMINI_API_KEY` และ `GEMINI_MODEL` ใน `.env` หรือป้อน API key เมื่อถูกถาม
คำตอบใช้รายการที่ค้นพบ ควรตรวจหลักฐานและใช้ SQL สำหรับยอดรวมทั้งฐานข้อมูล

### ส่งออก Cypher สำหรับ Neo4j

```powershell
py -3.12 -m scripts.export_petroleum_cypher
```

โปรแกรมถามรหัสผ่าน MySQL และสร้าง `outputs/petroleum.cypher`

### จัดการ Docker

```powershell
docker compose ps                   # ดูสถานะ
docker compose logs --tail 50 db     # ดู log
docker compose stop                 # หยุด เก็บ container ไว้
docker compose start                # เปิด container เดิม
```

Compose ปัจจุบันไม่กำหนด volume ให้ฐานข้อมูลหลัก ใช้ `stop` / `start` เพื่อเก็บข้อมูลใน container เดิม และสำรองข้อมูลก่อนลบหรือสร้าง container ใหม่

### ทดสอบและดูตัวเลือก

```powershell
# ทดสอบ Excel โดยไม่เชื่อมฐานข้อมูล
py -3.12 -m unittest discover -s tests -p "test_import_*.py"

# ทดสอบสูตร Dashboard ต้องติดตั้ง Node.js
node --test tests/test_boe_math.cjs tests/test_carbon_math.cjs tests/test_volume_math.cjs

# ฐานทดสอบแยกจาก petroleum โดย cn230_test ต้องว่างก่อนเริ่ม
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests

# ตัวเลือก import เช่น เปลี่ยนไฟล์หรือการเชื่อมต่อ
py -3.12 -m scripts.import_data --type csv --help
py -3.12 -m scripts.import_data --type emission --help
py -3.12 -m scripts.import_data --type reserve --help
```

## โครงสร้างโฟลเดอร์

| โฟลเดอร์ | เนื้อหา |
| --- | --- |
| `scripts/` | Import, export, RAG และเครื่องมือฐานข้อมูล |
| `Dashborad/` | Dashboard และ server |
| `database/` | Schema และบัญชีทดสอบ |
| `CN230 Petrolium Data/` | CSV และ Excel ต้นฉบับ |
| `tests/` | ชุดทดสอบ |
| `outputs/` | รายงาน ดัชนี และไฟล์ส่งออก |
| `backups/`, `tmp/` | ข้อมูลสำรองและไฟล์ชั่วคราว |
