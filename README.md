# UnifiedHealth — Patient & Hospital Records App (Streamlit)

A single Streamlit app with two coordinated interfaces — **Patient** and
**Hospital** — sharing one SQLite database so data flows correctly between
the two sides (e.g. a prescription a hospital adds shows up instantly in the
patient's "Prescriptions" tab).

## 1. Install

You need Python 3.9+ and, for photo OCR, the **Tesseract OCR** binary
installed on your system (the `pytesseract` package only talks to it, it
doesn't include it):

```bash
# macOS
brew install tesseract

# Debian/Ubuntu
sudo apt-get install tesseract-ocr

# Windows: install from https://github.com/UB-Mannheim/tesseract/wiki
# and make sure `tesseract.exe` is on your PATH.
```

Then install the Python packages:

```bash
pip install -r requirements.txt
```

## 2. Run

```bash
streamlit run app.py
```

This opens the app in your browser (default `http://localhost:8501`).
A SQLite file is created automatically at `data/health_app.db` the first
time you run it — no manual DB setup needed. Uploaded files are saved
under `uploads/`, and generated PDF summaries under `pdfs/`.

## 3. How it's organized

```
app.py        - all Streamlit screens/routing (patient + hospital)
db.py         - SQLite schema + every read/write function used by app.py
helpers.py    - ID/OTP generation, text extraction, categorisation,
                symptom question trees, red-flag logic, PDF generation
requirements.txt
data/         - SQLite database lives here (auto-created)
uploads/      - uploaded medical record files (auto-created)
pdfs/         - generated symptom-summary PDFs (auto-created)
```

## 4. Feature walkthrough

### Patient interface
- **Sign up / Log in** — sign up with phone + basic details to get a unique
  Patient ID (e.g. `PT-482913`). Log in from any device using that ID; an
  OTP step follows (see note on OTP below).
- **Add Medical Records** — upload a photo or PDF. Text is auto-extracted
  (PDF via `pdfplumber`, images via Tesseract OCR) and auto-tagged into
  categories (Allergy, Surgery, Lab Report, Diabetes, Cardiac, etc.) using
  keyword matching, so records become searchable immediately.
- **View Report** — a summary (record counts, category breakdown), a free-text
  search across all extracted record text, and a history of past symptom
  check summaries.
- **Current Problem** — type your problem in free text. For **chest pain**,
  **headache**, and **fever** the app asks a tailored sequence of follow-up
  questions, one at a time, purely from what you type (no multiple-choice
  menus). Anything else falls back to a short generic question set. At the
  end you get a plain-language summary, a 🔴 **red-flag** warning if answers
  match common urgent-care patterns, hospital suggestions for the relevant
  department (ranked using reviews stored in-app), and a downloadable PDF.
- **Prescriptions** — every prescription a hospital/doctor has added for this
  patient, in one place.
- **Add Review** — patients can rate a hospital + department + location,
  which directly feeds the hospital-suggestion ranking above.

### Hospital interface
- **Sign up / Log in** — same ID + OTP pattern as patients, but for the
  hospital as an organisation.
- **Add Doctor** — register a doctor (name, phone, email, department) and get
  a unique Doctor ID (in production this would be emailed to the doctor).
- **View Patient Record** — enter a Patient ID to request access; an OTP is
  generated and (in this demo) shown on screen standing in for "sent to the
  patient's phone" — the patient reads it out to hospital staff, who enter it
  to unlock the record. Once unlocked you see the patient's full record
  summary, uploaded documents, past symptom checks, and existing
  prescriptions, plus an **Add Prescription** panel gated by a valid Doctor
  ID from that hospital. The prescription form captures medicine name,
  morning/evening/night timing, before/after food, dosage, number of days,
  and optional lab tests.
- **View Doctor Details** — lists every doctor added by the hospital, and for
  each one, every prescription they've issued and to whom.

## 5. Important notes on the simulated bits

- **OTP delivery is simulated.** There's no SMS/email gateway wired up (and
  none was available to integrate in this build environment), so every OTP
  is shown directly on-screen in a blue "Simulated SMS/Email" banner instead
  of being sent silently. Swap `simulate_send_otp()` in `app.py` for a real
  provider (Twilio, MSG91, AWS SNS, SMTP, etc.) before using this with real
  patients.
- **Red-flag detection is a simple, transparent keyword/threshold check**, not
  a medical diagnosis. It exists to prompt people toward urgent care sooner,
  not to replace one. The PDF and in-app summary both carry this disclaimer.
- **Hospital suggestions** are ranked from reviews stored inside this app's
  own database (added via "Add Review"), not from an external maps/reviews
  API — the app works fully offline and self-contained.
- Symptom question trees currently cover **chest pain, headache, and fever**
  in detail, with a sensible generic fallback for everything else. Add more
  entries to `SYMPTOM_QUESTIONS` / `SYMPTOM_DEPARTMENT_MAP` in `helpers.py`
  to extend coverage.

## 6. Extending it

- Add more categories to `CATEGORY_KEYWORDS` in `helpers.py` to improve
  auto-tagging of uploaded records.
- Add more symptoms to `SYMPTOM_QUESTIONS` (and matching red-flag rules in
  `detect_red_flag`) to cover more "Current Problem" cases.
- Swap SQLite for Postgres/MySQL by changing `db.get_conn()` — every other
  function only uses standard SQL, so the rest of `db.py` needs minimal
  changes.
