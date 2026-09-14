"""
db.py
SQLite data layer for the Patient-Hospital Health Records app.
Every function opens its own short-lived connection so it is safe to call
from inside a Streamlit script that reruns top-to-bottom on every interaction.
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "health_app.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
PDF_DIR = os.path.join(BASE_DIR, "pdfs")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            patient_id   TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            phone        TEXT NOT NULL,
            age          TEXT,
            gender       TEXT,
            location     TEXT,
            created_at   TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            hospital_id  TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            phone        TEXT NOT NULL,
            location     TEXT,
            created_at   TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            doctor_id    TEXT PRIMARY KEY,
            hospital_id  TEXT NOT NULL,
            name         TEXT NOT NULL,
            phone        TEXT,
            email        TEXT,
            department   TEXT,
            created_at   TEXT NOT NULL,
            FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS records (
            record_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id      TEXT NOT NULL,
            filename        TEXT,
            stored_path     TEXT,
            filetype        TEXT,
            extracted_text  TEXT,
            categories      TEXT,
            uploaded_at     TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS prescriptions (
            prescription_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id       TEXT NOT NULL,
            doctor_id        TEXT NOT NULL,
            hospital_id      TEXT NOT NULL,
            medicines_json   TEXT,
            lab_tests_json   TEXT,
            notes            TEXT,
            created_at       TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS symptom_sessions (
            session_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id   TEXT NOT NULL,
            symptom      TEXT,
            qa_json      TEXT,
            summary      TEXT,
            red_flag     INTEGER,
            department   TEXT,
            pdf_path     TEXT,
            created_at   TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            review_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_name TEXT NOT NULL,
            department    TEXT,
            location      TEXT,
            rating        INTEGER,
            review_text   TEXT,
            patient_id    TEXT,
            created_at    TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS login_otp (
            role         TEXT NOT NULL,
            entity_id    TEXT NOT NULL,
            otp          TEXT NOT NULL,
            expires_at   TEXT NOT NULL,
            PRIMARY KEY (role, entity_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS access_otp (
            hospital_id  TEXT NOT NULL,
            patient_id   TEXT NOT NULL,
            otp          TEXT NOT NULL,
            expires_at   TEXT NOT NULL,
            PRIMARY KEY (hospital_id, patient_id)
        )
    """)

    conn.commit()
    conn.close()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- patients
def create_patient(patient_id, name, phone, age, gender, location):
    conn = get_conn()
    conn.execute(
        "INSERT INTO patients (patient_id, name, phone, age, gender, location, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (patient_id, name, phone, age, gender, location, now_str()),
    )
    conn.commit()
    conn.close()


def get_patient(patient_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def patient_id_exists(patient_id):
    return get_patient(patient_id) is not None


# ---------------------------------------------------------------- hospitals
def create_hospital(hospital_id, name, phone, location):
    conn = get_conn()
    conn.execute(
        "INSERT INTO hospitals (hospital_id, name, phone, location, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (hospital_id, name, phone, location, now_str()),
    )
    conn.commit()
    conn.close()


def get_hospital(hospital_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM hospitals WHERE hospital_id = ?", (hospital_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def hospital_id_exists(hospital_id):
    return get_hospital(hospital_id) is not None


# ---------------------------------------------------------------- doctors
def create_doctor(doctor_id, hospital_id, name, phone, email, department):
    conn = get_conn()
    conn.execute(
        "INSERT INTO doctors (doctor_id, hospital_id, name, phone, email, department, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doctor_id, hospital_id, name, phone, email, department, now_str()),
    )
    conn.commit()
    conn.close()


def get_doctor(doctor_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM doctors WHERE doctor_id = ?", (doctor_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_doctors_for_hospital(hospital_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM doctors WHERE hospital_id = ? ORDER BY created_at DESC",
        (hospital_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def doctor_belongs_to_hospital(doctor_id, hospital_id):
    doc = get_doctor(doctor_id)
    return bool(doc) and doc["hospital_id"] == hospital_id


# ---------------------------------------------------------------- records
def add_record(patient_id, filename, stored_path, filetype, extracted_text, categories):
    conn = get_conn()
    conn.execute(
        "INSERT INTO records (patient_id, filename, stored_path, filetype, extracted_text, "
        "categories, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (patient_id, filename, stored_path, filetype, extracted_text,
         json.dumps(categories), now_str()),
    )
    conn.commit()
    conn.close()


def get_records_for_patient(patient_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM records WHERE patient_id = ? ORDER BY uploaded_at DESC",
        (patient_id,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["categories"] = json.loads(d["categories"]) if d["categories"] else []
        except Exception:
            d["categories"] = []
        out.append(d)
    return out


def search_records(patient_id, keyword):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM records WHERE patient_id = ? AND "
        "(extracted_text LIKE ? OR filename LIKE ? OR categories LIKE ?) "
        "ORDER BY uploaded_at DESC",
        (patient_id, f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["categories"] = json.loads(d["categories"]) if d["categories"] else []
        except Exception:
            d["categories"] = []
        out.append(d)
    return out


# ---------------------------------------------------------------- prescriptions
def add_prescription(patient_id, doctor_id, hospital_id, medicines, lab_tests, notes):
    conn = get_conn()
    conn.execute(
        "INSERT INTO prescriptions (patient_id, doctor_id, hospital_id, medicines_json, "
        "lab_tests_json, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (patient_id, doctor_id, hospital_id, json.dumps(medicines),
         json.dumps(lab_tests), notes, now_str()),
    )
    conn.commit()
    conn.close()


def get_prescriptions_for_patient(patient_id):
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.*, d.name as doctor_name, d.department as doctor_department,
                  h.name as hospital_name
           FROM prescriptions p
           LEFT JOIN doctors d ON p.doctor_id = d.doctor_id
           LEFT JOIN hospitals h ON p.hospital_id = h.hospital_id
           WHERE p.patient_id = ? ORDER BY p.created_at DESC""",
        (patient_id,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["medicines"] = json.loads(d["medicines_json"]) if d["medicines_json"] else []
        d["lab_tests"] = json.loads(d["lab_tests_json"]) if d["lab_tests_json"] else []
        out.append(d)
    return out


def get_prescriptions_by_doctor(doctor_id):
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.*, pt.name as patient_name
           FROM prescriptions p
           LEFT JOIN patients pt ON p.patient_id = pt.patient_id
           WHERE p.doctor_id = ? ORDER BY p.created_at DESC""",
        (doctor_id,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["medicines"] = json.loads(d["medicines_json"]) if d["medicines_json"] else []
        d["lab_tests"] = json.loads(d["lab_tests_json"]) if d["lab_tests_json"] else []
        out.append(d)
    return out


# ---------------------------------------------------------------- symptom sessions
def add_symptom_session(patient_id, symptom, qa, summary, red_flag, department, pdf_path):
    conn = get_conn()
    conn.execute(
        "INSERT INTO symptom_sessions (patient_id, symptom, qa_json, summary, red_flag, "
        "department, pdf_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (patient_id, symptom, json.dumps(qa), summary, int(red_flag), department,
         pdf_path, now_str()),
    )
    conn.commit()
    conn.close()


def get_symptom_sessions(patient_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM symptom_sessions WHERE patient_id = ? ORDER BY created_at DESC",
        (patient_id,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["qa"] = json.loads(d["qa_json"]) if d["qa_json"] else {}
        out.append(d)
    return out


# ---------------------------------------------------------------- reviews
def add_review(hospital_name, department, location, rating, review_text, patient_id):
    conn = get_conn()
    conn.execute(
        "INSERT INTO reviews (hospital_name, department, location, rating, review_text, "
        "patient_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (hospital_name, department, location, rating, review_text, patient_id, now_str()),
    )
    conn.commit()
    conn.close()


def get_reviews_ranked(department=None, location=None):
    """Rank hospitals by average rating for a department, optionally filtered by location."""
    conn = get_conn()
    query = """SELECT hospital_name, department, location,
                      AVG(rating) as avg_rating, COUNT(*) as review_count
               FROM reviews WHERE 1=1"""
    params = []
    if department:
        query += " AND department LIKE ?"
        params.append(f"%{department}%")
    if location:
        query += " AND location LIKE ?"
        params.append(f"%{location}%")
    query += " GROUP BY hospital_name, department ORDER BY avg_rating DESC, review_count DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_reviews(hospital_name=None):
    conn = get_conn()
    if hospital_name:
        rows = conn.execute(
            "SELECT * FROM reviews WHERE hospital_name LIKE ? ORDER BY created_at DESC",
            (f"%{hospital_name}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- OTP (login)
def set_login_otp(role, entity_id, otp, ttl_minutes=5):
    conn = get_conn()
    expires = (datetime.now() + timedelta(minutes=ttl_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO login_otp (role, entity_id, otp, expires_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(role, entity_id) DO UPDATE SET otp=excluded.otp, expires_at=excluded.expires_at",
        (role, entity_id, otp, expires),
    )
    conn.commit()
    conn.close()


def verify_login_otp(role, entity_id, otp):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM login_otp WHERE role = ? AND entity_id = ?", (role, entity_id)
    ).fetchone()
    conn.close()
    if not row:
        return False
    if row["otp"] != otp:
        return False
    if datetime.now() > datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S"):
        return False
    return True


# ---------------------------------------------------------------- OTP (hospital access to patient record)
def set_access_otp(hospital_id, patient_id, otp, ttl_minutes=5):
    conn = get_conn()
    expires = (datetime.now() + timedelta(minutes=ttl_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO access_otp (hospital_id, patient_id, otp, expires_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(hospital_id, patient_id) DO UPDATE SET otp=excluded.otp, expires_at=excluded.expires_at",
        (hospital_id, patient_id, otp, expires),
    )
    conn.commit()
    conn.close()


def verify_access_otp(hospital_id, patient_id, otp):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM access_otp WHERE hospital_id = ? AND patient_id = ?",
        (hospital_id, patient_id),
    ).fetchone()
    conn.close()
    if not row:
        return False
    if row["otp"] != otp:
        return False
    if datetime.now() > datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S"):
        return False
    return True
