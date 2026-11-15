# Petroleum_CN230

Petroleum, Natural Gas & Fuels Database System — an academic project integrating MySQL, Neo4j/Cypher, and a petroleum data dashboard.

## Semantic Search + Gemini RAG

ใช้ Python 3.12 บนเครื่อง Windows ที่เชื่อม MySQL ได้ ค่าเริ่มต้นคือ 127.0.0.1:3308 ฐาน petroleum ผู้ใช้ root
อ่าน 6 ตารางกิจกรรมและ LEFT JOIN ตารางอ้างอิงตาม schema ทีม ตารางว่างจะมี 0 ข้อความ แต่ต้องมีโครงสร้างตารางครบ
รองรับ Sale, Production_Monthly, Supply_Monthly, Price_Monthly, Reserve_Annual และ Emission_Factor

## ติดตั้งและสร้างดัชนี
เปิด PowerShell ในโฟลเดอร์นี้
```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 petroleum_rag.py build
```
โปรแกรมถามรหัส MySQL โดยไม่แสดงอักขระขณะพิมพ์ โหลดโมเดล multilingual MiniLM ครั้งแรกจาก Hugging Face
ใช้เวลาตามจำนวนรายการและ CPU แต่ละตารางจะพิมพ์จำนวนแถวเมื่ออ่านครบ
สร้าง petroleum_index.sqlite เป็น snapshot ของข้อมูลพร้อม embedding ค้น cosine ด้วย NumPy ในเครื่อง
MySQL ใช้ SELECT และ read-only transaction ถ้าสร้างดัชนีใหม่ล้มเหลว ไฟล์ดัชนีเดิมยังใช้ได้
ค่าทศนิยมเก็บเป็นข้อความในหลักฐานเพื่อรักษาเลขเดิม NULL คงเป็น null และชื่อแหล่งคงต้นฉบับ
ข้อความยาวแบ่งตาม token limit แล้วรวมอันดับเป็นราย record ป้องกันรายการซ้ำใน Top-k

## ค้นและให้ Gemini ตอบ
```powershell
py -3.12 petroleum_rag.py ask --question "ขอดูข้อมูลการจำหน่ายก๊าซธรรมชาติ" --table Sale
py -3.12 petroleum_rag.py ask --question "รายการ S03 มีมูลค่าขายเท่าไรและมาจากแหล่งไหน" --table Sale --record-id S03
py -3.12 petroleum_rag.py ask --question "ข้อมูลการผลิตน้ำมันดิบ" --table Production_Monthly --product-id P01 --year 2024
```
โปรแกรมถาม Gemini API key หรืออ่านจาก GEMINI_API_KEY หากกำหนดไว้
Gemini ได้รับคำถามและหลักฐาน Top-k รวมชื่อแหล่ง ผลิตภัณฑ์ ตัวเลข และรหัสรายการ
ตั้ง GEMINI_MODEL หรือใช้ --gemini-model เพื่อเลือกโมเดลที่บัญชีเข้าถึงได้ ค่าเริ่มต้น gemini-2.5-flash
ผลค้นจริง S03 อ้างจากฐานของคุณ ตัวเลข 3,000,000 ใน notebook เป็นข้อมูลจำลอง
คำถามทั่วไปจะไม่แปลงปีหรือรหัสเป็น filter อัตโนมัติ ใช้ --year --month --record-id --product-id --field-id เมื่อต้องการจำกัดตรงเงื่อนไข
--search-only แสดงหลักฐานโดยไม่เรียก Gemini
--top-k 5 และ --threshold 0.0 เป็นค่าเริ่มต้น threshold เป็นตัวกรองความคล้ายที่ควรปรับจากคำถามประเมินของทีม

## ขอบเขตและการอัปเดต
- รัน build ใหม่หลังปรับ MySQL เพื่อสร้าง snapshot ใหม่ ระบบแสดงเวลา snapshot UTC ทุกครั้งที่ค้น
- ask อ่าน snapshot ภายในเครื่อง ข้อมูลต้นทางที่เปลี่ยนหลัง build จะเห็นเมื่อ build ใหม่
- เหมาะกับการค้นรายการและอธิบายหลักฐาน Top-k คำถามยอดรวม รายการสูงสุด หรือแนวโน้มทั้งฐานต้องมี SQL aggregate ที่ครอบคลุมทุกแถว
- มีคำสั่งให้ Gemini อ้างอิง [Table/id] และตอบว่าข้อมูลไม่พอเมื่อหลักฐานไม่รองรับ ตรวจคำตอบเทียบ JSON ที่แสดงด้วย
- คะแนน similarity เป็นการจัดอันดับความเกี่ยวข้อง ไม่ใช่การตรวจสอบความถูกต้องของคำตอบ
- โปรแกรมไม่เปิด interactive chatbot คำสั่ง ask รับคำถามครั้งละหนึ่งครั้ง

## การตรวจสอบ
ตรวจด้วยข้อมูลจำลองและตัวสร้างเวกเตอร์ทดสอบแล้ว ตัวกรองตรงรหัส/ปี การรักษาเลขทศนิยม ภาษาไทย NULL
การรวม chunks ของแถวเดียว และการเก็บ index เดิมเมื่อ rebuild ล้มเหลว ผ่าน
ยังไม่ได้เชื่อม MySQL จริงของทีม ดาวน์โหลดโมเดลจริง หรือเรียก Gemini ด้วย API key ของทีม
หากขึ้น Failed ให้ตรวจ service MySQL, schema, สิทธิ์โมเดลและโควตา API ตามชนิด error ที่แสดง
ใช้ --search-only เพื่อแยกทดสอบ retrieval จาก Gemini

## Dashboard
คัดลอก `.env.example` เป็น `.env` แล้วกำหนดรหัสผ่าน MySQL ทั้ง `MYSQL_PASSWORD` และ `MYSQL_ROOT_PASSWORD` จากนั้นติดตั้ง dependencies ตามขั้นตอนด้านบน
เปิด Dashboard จากโฟลเดอร์โปรเจกต์:
```powershell
py -3.12 Dashborad/server.py
```
แล้วเปิด `http://127.0.0.1:8000` ในเบราว์เซอร์
แท็บคาร์บอนอ่านค่า Emission Factor จาก MySQL และแสดงเป็น kgCO₂e ต่อหน่วยเชื้อเพลิง

อ้างอิง
https://github.com/googleapis/python-genai
https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2


## Database schema (SRS)

`schema.sql` follows SRS sections 4.2-4.3 for all ten tables, including
`VARCHAR(50)` identifiers, column-specific decimal precision and nullable fields.
Document inconsistencies are resolved as follows:

- `Unit.unit_id` follows section 4.3.3 (section 4.2.3 prints `field_id`).
- `Supply_Monthly.area` follows section 4.2.6: `VARCHAR(100) NULL`, without a foreign key.
- `Reserve_Annual` keeps the name used by the relational schema (the dictionary heading has a typo).
- BR-08 keeps `UNIQUE(field_id, product_id, unit_id, month, year)` without currency.
  MySQL allows repeated unique-key groups containing NULL; missing dates remain nullable per SRS.
- BR-01 needs a post-import audit across Field, Production_Monthly and Block;
  foreign keys alone do not ensure that every Field has a production record.

Apply to an **empty** database after MySQL is ready (PowerShell):

```powershell
docker compose exec db mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS petroleum CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
$dbContainer = docker compose ps -q db
docker cp .\schema.sql "${dbContainer}:/tmp/petroleum-schema.sql"
docker compose exec db mysql -u root -p petroleum -e "source /tmp/petroleum-schema.sql"
```

This creates tables; it does not migrate an existing database. Do not delete existing
production tables to apply it. Back up and prepare an ALTER migration separately.

The CSV importer still needs separate alignment before a full import: its default
`--price-currency both` conflicts with BR-08 (choose one confirmed currency), and
gas prices need a confirmed `--gas-price-unit` because `Price_Monthly.unit_id` is required.
Rows with a missing required Sale/Price_Monthly field are skipped and listed with
their source record number in `petroleum_import_review.csv`. Gas prices without a
confirmed `--gas-price-unit` are also skipped and reported; their unit is not guessed.
For example, to rehearse importing THB prices while leaving unconfirmed gas prices
for later review:

```powershell
py -3.12 import_data.py --folder ".\CN230 Petrolium Data" --database petroleum --host 127.0.0.1 --port 3308 --user root --dry-run --price-currency THB
```

Source data can also exceed the SRS decimal ranges; review failures rather than widening
columns silently. Excel import is not implemented by this schema change.

All data import code lives in `import_data.py`. Select `--type csv` (default),
`--type emission`, or `--type reserve`; use `--help` with a mode for its options.
The default CSV folder is the project's `CN230 Petrolium Data` directory.

## Import Emission Factor from Excel

Run the CSV import first, then this importer: `import_data.py --apply` clears all ten
tables, including Emission_Factor. This Excel import mode only inserts/updates
factors present in the workbook and adds missing Product/Unit references. It does not
clear tables or remove factors absent from the workbook. Repeated imports update by
`factor_id` and leave identical records unchanged.

```powershell
py -3.12 -m pip install mysql-connector-python python-dotenv openpyxl
py -3.12 import_data.py --type emission --dry-run
py -3.12 import_data.py --type emission --apply
```

Connection defaults come from the project's `.env` or environment variables. If no
`MYSQL_PASSWORD` is supplied, the script prompts without echoing the password.
Override with `--host`, `--port`, `--database`, `--user`, or `--file` as needed:

```powershell
py -3.12 import_data.py --type emission --file ".\CN230 Petrolium Data\TGO_2569_Emission_Factor_Petroleum_Fuels.xlsx" --database petroleum --host 127.0.0.1 --port 3308 --user root --dry-run
```

The importer reads `MySQL_Import_Ready`, validates all records before connecting,
and stores the supplied total kgCO2e factor (not individual gas components).
It reuses Product names Natural Gas/LPG and exact unit symbols, ignoring case,
and adds the other fuel groups and missing units from the workbook mapping.
It refuses ambiguous references or IDs already assigned a different meaning.
Activity details (including blend type) remain in `activity_type` and `basis`.
Both dry runs and failures roll back all Product, Unit and factor writes together.

## Carbon scenario dashboard

Start `py -3.12 Dashborad/server.py`, then open `http://127.0.0.1:8000/carbon`
or choose the carbon scenario link in the existing dashboard header.
Import production CSV and Emission Factor Excel first. The page reads the same
MySQL snapshot and never writes to the database.

This is a hypothetical combustion scenario for produced natural gas, **not actual
production-process emissions**. Select a stationary Natural Gas NCV factor in SCF
and a combustion share, then filter by year, month, or field. The calculation is
MMSCFD × 1,000,000 × production_days × share × kgCO2e/SCF ÷ 1,000.
Unsupported products/units and missing production days are shown as uncalculable,
not zero. Coverage is by record count. CSV exports include the scenario, factor,
share and exclusion reasons. Actual production emissions require activity inputs
such as fuel consumed, electricity, flaring and methane leakage.

Calculation regression checks: `node --test Test/test_carbon_math.cjs`.

## Import annual proven reserves

`import_data.py --type reserve` reads the three `2025_p1-*.xlsx` files in
`CN230 Petrolium Data/Reserve-2`. Their contents cover 2017-2025, not only 2025.
Use the existing schema; no additional table is required.

```powershell
py -3.12 import_data.py --type reserve --dry-run
py -3.12 import_data.py --type reserve --apply
```

Connection defaults come from `.env`; override using `--host`, `--port`,
`--database`, and `--user`. Use `--folder` to change the Reserve-2 directory.
The importer preserves native units: MMbbl for oil/condensate and Bcf for gas,
without changing the numerical scale. Missing reserves remain NULL, not zero.
Values are rounded HALF_UP to six decimal places per the existing schema.
`reserve_import_review.csv` records the source row, original/stored values,
rounding and use of cached Excel formula results (including external formulas).
Cached values are not recalculated; a formula without a cached result stops import.

Existing Product, Unit and exact Block labels are reused; missing references are
added. Grouped block labels and footnote asterisks are retained without guessing
individual blocks. Reruns match product/block/unit/year, update changed values,
and do not duplicate or clear existing rows. Ambiguous references or duplicate
existing grains stop and roll back the transaction.

Run CSV import **before** the reserve and Emission Factor importers because
`import_data.py --apply` resets all ten tables. Refresh the dashboard afterward.
Checks: `py -3.12 -m unittest discover -s Test -p test_import_reserve_annual.py`.

## Production and supply dashboard volumes

The production and supply tabs show separate totals for liquid and gas volumes,
instead of averaging source daily rates. Choose m3/standard m3 or bbl/MMSCF;
liquids and gas are never added into a single total. A separate selector chooses
which family drives the trend and ranking graphs.

Production volume uses quantity × actual production_days. Supply volume is an
estimate using daily_rate × calendar days in the month, including leap years.
1 bbl = 0.158987294928 m3; 1 MMSCF = 28,316.846592 standard m3, assuming
the source standard gas conditions. This is volume conversion, not oil/energy
equivalence. Unsupported units or missing inputs stay null and are counted in
coverage. Converted monthly volume, unit, days and exclusion reasons are included
in the table and both CSV export modes. The underlying MySQL records are unchanged.

Checks: `node --test Test/test_volume_math.cjs`.

### BOED and MMBOE display

The production/supply tabs default to BOED and the reserve tab uses MMBOE.
Existing physical-volume display modes are still selectable. This changes only
the display, not stored MySQL values. Production uses the source oil_equivalent
as BOED for gas/condensate when present, and crude oil uses 1 bbl = 1 BOE.
Positive production with zero oil_equivalent is excluded as inconsistent rather
than silently treated as zero. Missing equivalents can use the displayed estimates.

Gas defaults to 174.4 BOE/MMSCF and condensate to 0.9096 BOE/bbl. These are
**inferred estimates** from median positive equivalent/rate ratios in the project's
production CSVs, not certified thermal factors or universal conversion constants.
They are editable on the dashboard and apply to supply, reserve, and production
records without source equivalents. Actual heat content can require other factors.
For comparison, USGS uses a different approximate convention of 6,000 cubic feet
of gas per BOE in its assessment:
https://pubs.usgs.gov/circ/1995/circ1118/resass/metric.html

Monthly production BOE = BOED × actual production_days; supply BOE = estimated
BOED × calendar days. The main BOED card is total BOE divided by distinct calendar
days in the months represented in the filtered data, not a sum of daily rates across
months or an average per record. Months missing entirely from the filtered data are
not inferred. Graphs use the same definition month by month; field rankings use the
same overall date denominator for comparability. Coverage excludes unavailable
inputs, and totals may be partial.

Reserve conversion: Bcf × 1,000 × gas BOE/MMSCF ÷ 1,000,000 = MMBOE;
crude MMbbl = MMBOE, condensate MMbbl × condensate BOE/bbl = MMBOE.
Reserve totals/rankings require one year to avoid adding stock snapshots across
years. CSV exports include source units, converted values, basis and assumptions.
Checks: `node --test Test/test_boe_math.cjs`.
