# Mae Pla Green Pen AI Trader

> Professional XAUUSD Gold Trading Analysis System

---

## สารบัญ

1. [ภาพรวม](#ภาพรวม)
2. [สถาปัตยกรรมโปรเจกต์](#สถาปัตยกรรมโปรเจกต์)
3. [ฟีเจอร์](#ฟีเจอร์)
4. [วิธีติดตั้งสำหรับมือใหม่ (ละเอียดทุกขั้นตอน)](#วิธีติดตั้งสำหรับมือใหม่)
5. [วิธีติดตั้งแบบ Docker](#วิธีติดตั้งแบบ-docker)
6. [การตั้งค่า](#การตั้งค่า)
7. [คำสั่ง CLI](#คำสั่ง-cli)
8. [ระบบ Scoring](#ระบบ-scoring)
9. [ทดสอบ (Testing)](#ทดสอบ-testing)
10. [กฎการเทรด](#กฎการเทรด)
11. [LINE Notifications](#line-notifications)
12. [License & Disclaimer](#license--disclaimer)

---

## ภาพรวม

**Mae Pla Green Pen AI Trader** คือระบบวิเคราะห์ทองคำ XAUUSD แบบมืออาชีพ ที่ใช้หลักการ "แม่ปลา เขียนเขียว" ในการวิเคราะห์ กราฟ หลาย Timeframe, ตรวจจับโครงสร้างตลาด (HH/HL, LH/LL), หา Level Support/Resistance, วิเคราะห์ Grid ระดับจิตวิทยา, วิเคราะห์ Price Action และสร้างแผนเทรดอัตโนมัติ

---

## สถาปัตยกรรมโปรเจกต์

```
pencilgreen/
├── .env                    # รหัสผ่าน MT5 (ไม่ต้อง commit)
├── config.yaml             # ตั้งค่าหลักของแอป
├── requirements.txt        # รายการ library ที่ต้องลง
├── Dockerfile              # สำหรับ build Docker image
├── docker-compose.yml      # สำหรับรันหลาย services
├── src/                    # ซอร์สโค้ดหลัก
│   ├── main.py             # CLI entry point
│   ├── config.py           # โหลด config
│   ├── backtest.py         # Backtesting engine
│   ├── log_setup.py        # ตั้งค่า logging
│   ├── analysis/           # โมดูลวิเคราะห์
│   │   ├── cycle_engine.py     # วิเคราะห์ Cycle ทองคำ
│   │   ├── frame_engine.py     # วิเคราะห์ Frame (ATH, 1000 จุด)
│   │   ├── trend_engine.py     # วิเคราะห์ Trend หลาย TF
│   │   ├── market_structure.py # ตรวจจับ HH/HL, LH/LL
│   │   ├── support_resistance.py # หา Support/Resistance
│   │   ├── grid_analysis.py    # วิเคราะห์ Grid 0/5
│   │   └── price_action.py     # ตรวจจับ Pin Bar, Engulfing
│   ├── engine/             # เอนจิ้นหลัก
│   │   ├── signal_engine.py    # สร้างสัญญาณเทรด
│   │   ├── risk_manager.py     # จัดการความเสี่ยง
│   │   └── trade_executor.py   # ส่งคำสั่งเทรด
│   ├── data/               # ชั้นข้อมูล
│   │   ├── mt5_connector.py    # เชื่อมต่อ MT5
│   │   └── journal.py         # บันทึกเทรด journal
│   └── notification/       # ระบบแจ้งเตือน
│       └── line_notify.py      # แจ้งเตือนผ่าน LINE
├── tests/                  # ชุดทดสอบ
│   ├── conftest.py
│   ├── test_analysis.py
│   ├── test_backtest.py
│   ├── test_risk.py
│   └── test_signal.py
├── data/                   # SQLite database
└── logs/                   # ไฟล์บันทึก
```

---

## ฟีเจอร์

| ฟีเจอร์ | รายละเอียด |
|---------|-----------|
| Multi-Timeframe Analysis | วิเคราะห์ Monthly, Weekly, Daily, H4, H1, M15 |
| Market Structure | ตรวจจับ HH/HL, LH/LL อัตโนมัติ |
| Support & Resistance | หา Zone S/R ด้วย clustering |
| Grid 0/5 Analysis | หาราคาจิตวิทยา (เช่น 3300, 3305) |
| 1000-Point Frame | วิเคราะห์ตำแหน่ง Cycle ของทองคำ |
| ATH Frame | คำนวณระยะจาก All-Time High |
| Price Action | ตรวจจับ Engulfing, Pin Bar, Wick |
| Setup Scoring (0-10) | ให้คะแนน Setup พร้อม Grade A+ ถึง NO TRADE |
| Risk Management | คำนวณ Position Size, R:R, Daily Loss Limit |
| LINE Notify | แจ้งเตือนแบบ Real-time ผ่าน LINE |
| SQLite Database | บันทึกสัญญาณ, เทรด, Performance |
| MT5 Integration | เชื่อมต่อข้อมูล Live และส่งคำสั่งเทรด |
| Simulated Mode | โหมดทดสอบไม่ต้องต่อ MT5 |
| Docker Support | รันแบบ Container ได้ทันที |

---

## วิธีติดตั้งสำหรับมือใหม่

> **ข้อสำคัญ:** ถ้าคอมคุณไม่เคยลงอะไรเลย ทำตามขั้นตอนด้านล่างนี้ทีละขั้น

### ทางเลือก A: ติดตั้ง Manual (ต้องลง Python เอง)

---

#### ขั้นตอนที่ 1: ลง Git

Git คือโปรแกรมสำหรับ download โค้ดจาก GitHub มาไว้ในคอม

1. **เปิดเว็บไซต์:** https://git-scm.com/download/win
2. **กดดาวน์โหลด** ไฟล์ `Git-2.55.0.2-64-bit.exe` (หรือเวอร์ชันล่าสุด)
3. **ดับเบิลคลิก** ไฟล์ที่โหลดเสร็จ
4. **กด Next ไปเรื่อยๆ** จนจบ (ไม่ต้องแก้ค่าอะไรเลย ใช้ default ได้เลย)
5. **ทดสอบ:** เปิด Command Prompt แล้วพิมพ์:
   ```
   git --version
   ```
   ถ้าขึ้น `git version 2.55.0.windows.1` หรืออะไรประมาณนี้ = สำเร็จ

---

#### ขั้นตอนที่ 2: ลง Python

Python คือภาษาโปรแกรมที่โปรเจกต์นี้ใช้

1. **เปิดเว็บไซต์:** https://www.python.org/downloads/
2. **กดปุ่ม "Download Python 3.12.x"** (สีเหลืองๆ ตรงหน้าเว็บ)
3. **ดับเบิลคลิก** ไฟล์ที่โหลดเสร็จ
4. **สำคัญมาก!** ตอนหน้าต่าง install เปิดขึ้นมา ให้ **ติ๊กช่อง "Add python.exe to PATH"** ที่ด้านล่างก่อน แล้วค่อยกด **"Install Now"**
5. **รอจนเสร็จ** แล้วกด Close
6. **ทดสอบ:** เปิด Command Prompt ใหม่ แล้วพิมพ์:
   ```
   python --version
   ```
   ถ้าขึ้น `Python 3.12.x` = สำเร็จ

> **หมายเหตุ:** ถ้าไม่ติ๊ก "Add to PATH" จะใช้คำสั่ง `python` ใน Command Prompt ไม่ได้ ต้อง uninstall แล้วลงใหม่

---

#### ขั้นตอนที่ 3: ลง VS Code (ถ้าต้องการแก้ไขโค้ด)

VS Code คือโปรแกรมแก้ไขโค้ดที่ดีที่สุดตอนนี้ ฟรี ไม่จำเป็นต้องลงถ้าแค่ต้องการรัน

1. **เปิดเว็บไซต์:** https://code.visualstudio.com/download
2. **กดปุ่ม "Windows"** แล้วเลือก **"User Installer x64"**
3. **ดับเบิลคลิก** ไฟล์ที่โหลดเสร็จ
4. **กด Next ไปเรื่อยๆ** จนจบ

> **ถ้าไม่ลง VS Code** ใช้ Command Prompt หรือ Notepad ก็ได้ แต่จะแก้โค้ดยาก

---

#### ขั้นตอนที่ 4: Clone โปรเจกต์มาไว้ในคอม

1. **สร้างโฟลเดอร์** สำหรับเก็บโปรเจกต์ เช่น สร้าง `C:\Projects`
2. **เปิด Command Prompt** (ค้นหาใน Windows Search ว่า "cmd")
3. **พิมพ์คำสั่งทีละบรรทัด:**
   ```
   cd C:\Projects
   git clone https://github.com/somjit2134/maepla-greenpen-ai-trader.git
   cd maepla-greenpen-ai-trader
   ```

---

#### ขั้นตอนที่ 5: ตั้งค่า Virtual Environment

Virtual Environment คือการแยก environment ของโปรเจกต์นี้ออกจากตัวอื่น

1. **ยังอยู่ใน Command Prompt โฟลเดอร์โปรเจกต์** พิมพ์:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
2. **สังเกต:** หน้า Command Prompt จะขึ้น `(venv)` ต้นบรรทัด = สำเร็จ

---

#### ขั้นตอนที่ 6: ลง Dependencies

```
pip install -r requirements.txt
```

รอจนเสร็จ (ใช้เวลา 1-5 นาที แล้วแต่เน็ต)

---

#### ขั้นตอนที่ 7: ตั้งค่า .env

ไฟล์ `.env` คือไฟล์ที่เก็บรหัสผ่าน MT5 (ไม่ต้อง commit ขึ้น Git)

1. **สร้างไฟล์ `.env`** ในโฟลเดอร์โปรเจกต์ (ใช้ Notepad สร้าง)
2. **ใส่ข้อมูล:**
   ```
   MT5_LOGIN=เลขบัญชีของคุณ
   MT5_PASSWORD=รหัสผ่าน MT5 ของคุณ
   MT5_SERVER=ชื่อ Server ของ Broker
   ```

> **หมายเหตุ:** ถ้าไม่มีบัญชี MT5 จะรันแบบ simulate ได้เลย ไม่ต้องแก้ไฟล์นี้

---

#### ขั้นตอนที่ 8: ทดสอบรัน

```
python -m src.main /analyze --simulate
```

ถ้าไม่มี error = ติดตั้งสำเร็จ!

---

### ทางเลือก B: ติดตั้งแบบ Docker (แนะนำสำหรับมือใหม่)

> Docker คือการรันโปรแกรมใน "Container" แยกจากเครื่อง ไม่ต้องมานั่ง setup Python เอง

---

#### ขั้นตอนที่ 1: ลง Git

เหมือนขั้นตอนที่ 1 ด้านบน

- **Download:** https://git-scm.com/download/win

---

#### ขั้นตอนที่ 2: ลง Docker Desktop

1. **เปิดเว็บไซต์:** https://www.docker.com/products/docker-desktop/
2. **กดปุ่ม "Download for Windows"**
3. **ดับเบิลคลิก** ไฟล์ที่โหลดเสร็จ
4. **ตอน install ต้องติ๊กช่อง "Use WSL 2 instead of Hyper-V"**
5. **รอจนเสร็จ** แล้ว **restart คอม** (สำคัญ!)
6. **หลัง restart** เปิด Docker Desktop ขึ้นมา รอจน icon สีเขียว (_running)

> **หมายเหตุ:** Docker Desktop ฟรีสำหรับ personal use, small business (<250 คน, <10 ล้านเหรียญ/ปี)

---

#### ขั้นตอนที่ 3: Clone และรัน

1. **เปิด Command Prompt**
2. **พิมพ์:**
   ```
   git clone https://github.com/somjit2134/maepla-greenpen-ai-trader.git
   cd maepla-greenpen-ai-trader
   docker compose up -d
   ```

เสร็จแล้ว! โปรแกรมจะรันอัตโนมัติใน mode simulate

---

#### คำสั่ง Docker อื่นๆ

```bash
# รัน backtest
docker compose --profile backtest run maepla-backtest

# รันทดสอบ
docker compose --profile test run maepla-test

# หยุดรัน
docker compose down

# ดู log
docker compose logs -f
```

---

## การตั้งค่า

แก้ไฟล์ `config.yaml`:

```yaml
mt5:
  path: "C:\\Program Files\\MetaTrader 5\\terminal64.exe"  # path ของ MT5
  timeout_seconds: 30

symbol:
  name: "XAUUSD"
  at: 5603.0  # All-Time High ของทองคำ

risk:
  risk_per_trade_percent: 1.0   # เสี่ยง 1% ต่อเทรด
  max_risk_percent: 2.0          # สูงสุด 2% ต่อเทรด
  max_daily_loss_percent: 5.0    # ขาดทุนสูงสุดต่อวัน 5%
  min_rr: 2.0                    # Risk:Reward ขั้นต่ำ 1:2

notification:
  line_notify_token: ""          # ใส่ token จาก LINE Notify
  line_notify_enabled: false     # เปิด/ปิดแจ้งเตือน
```

> **สำคัญ:** ไม่ต้องแก้ `mt5.login`, `mt5.password`, `mt5.server` ใน config.yaml เพราะโหลดจากไฟล์ `.env` แล้ว

---

## คำสั่ง CLI

| คำสั่ง | คำอธิบาย | ตัวอย่าง |
|--------|----------|---------|
| `/analyze` | วิเคราะห์ XAUUSD แบบเต็ม | `python -m src.main /analyze --simulate` |
| `/scan` | สแกนทุก Setup | `python -m src.main /scan --simulate` |
| `/buysetup` | หา Setup BUY เท่านั้น | `python -m src.main /buysetup --simulate` |
| `/sellsetup` | หา Setup SELL เท่านั้น | `python -m src.main /sellsetup --simulate` |
| `/risk` | คำนวณ Position Size | `python -m src.main /risk --entry 4075 --stop 4060 --target 4100 --balance 10000` |
| `/backtest` | รัน Backtest | `python -m src.main /backtest --simulate --periods 1000` |
| `/journal` | ดู/เพิ่ม Trade Journal | `python -m src.main /journal view` |
| `/monitor` | โหมดตรวจสอบต่อเนื่อง | `python -m src.main /monitor --simulate --interval 60` |

### ตัวอย่างการใช้งาน

```bash
# วิเคราะห์แบบ simulate (ไม่ต้องต่อ MT5)
python -m src.main /analyze --simulate

# วิเคราะห์แบบ Live (ต้องมี MT5 เปิดอยู่)
python -m src.main /analyze

# คำนวณ Lot Size สำหรับเทรด
python -m src.main /risk --entry 3350 --stop 3340 --target 3370 --balance 10000

# ตรวจสอบต่อเนื่องทุก 60 วินาที
python -m src.main /monitor --simulate --interval 60

# ดู Trade Journal
python -m src.main /journal view

# เพิ่ม Journal Entry
python -m src.main /journal add --direction BUY --entry-price 3350 --exit-price 3370 --profit 20 --lesson "รอ Confirm ก่อนเข้า"
```

---

## ระบบ Scoring

| คะแนน | Grade | คำแนะนำ |
|-------|-------|---------|
| 9-10 | **A+ Setup** | โอกาสสำเร็จสูงมาก เข้าเทรดได้ |
| 7-8 | **Good Setup** | ควรพิจารณาเทรด |
| 5-6 | **Watchlist** | เฝ้าระวัง อย่าเพิ่งเข้า |
| <5 | **NO TRADE** | ห้ามเทรด อยู่ห่างๆ |

---

## ทดสอบ (Testing)

```bash
# รันทดสอบทั้งหมด
python -m pytest tests/ -v

# รันทดสอบพร้อม Coverage
python -m pytest tests/ --cov=src --cov-report=term

# รันทดสอบเฉพาะไฟล์
python -m pytest tests/test_analysis.py -v

# รันทดสอบเฉพาะ Test Case
python -m pytest tests/test_analysis.py -v -k "test_bullish_structure"
```

---

## กฎการเทรด

1. **อย่าเดา** - รอราคาเดินทางมาถึง Level สำคัญก่อน
2. **Multi-timeframe ต้องตรงกัน** - ทุก Timeframe ต้องเห็นตรงกัน
3. **Risk:Reward ขั้นต่ำ 1:2** - ห้ามเทรดถ้า R:R ต่ำกว่านี้
4. **เสี่ยงสูงสุด 2% ต่อเทรด** - รักษาเงินทุนไว้
5. **ระวังข่าว** - หลีกเลี่ยงการเทรดช่วงข่าว Impact สูง
6. **ห้ามเทรดแก้แค้น** - อย่าเทรดเพราะอารมณ์
7. **บันทึกทุกเทรด** - เรียนรู้จากทุกผลลัพธ์

---

## LINE Notifications

เปิดแจ้งเตือนผ่าน LINE:

1. ไปที่ https://notify-bot.line.me/
2. -login ด้วย LINE
3. สร้าง Token ใหม่
4. ใส่ Token ในไฟล์ `config.yaml`:
   ```yaml
   notification:
     line_notify_token: "YOUR_LINE_TOKEN"
     line_notify_enabled: true
   ```

---

## Database

โปรเจกต์ใช้ SQLite (`data/trading.db`) เก็บข้อมูล:

| Table | ข้อมูลที่เก็บ |
|-------|-------------|
| signals | สัญญาณวิเคราะห์ทั้งหมด |
| trades | บันทึกเทรดที่ทำจริง |
| performance | สถิติ Performance |
| journal | Trade Journal |

---

## License & Disclaimer

**License:** ระบบเทรดส่วนบุคคล ใช้เพื่อการศึกษาและใช้งานส่วนตัวเท่านั้น

**Disclaimer:** การเทรดในตลาดการเงินมีความเสี่ยงสูง ระบบนี้เป็นเครื่องมือวิเคราะห์เท่านั้น ไม่รับประกันผลกำไร อย่าเสี่ยงเกินกว่าที่จะรับไหว
