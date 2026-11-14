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
