"""
helpers.py
Utility functions: ID/OTP generation, document text extraction, keyword based
categorisation of medical records, the symptom question trees, red-flag
detection, and PDF summary generation.
"""

import os
import io
import re
import random
import string
import difflib
from collections import OrderedDict
from datetime import datetime

import pytesseract

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


# ----------------------------------------------------------------------
# Tesseract OCR binary location
# ----------------------------------------------------------------------
# pytesseract only talks to the Tesseract *program* - it doesn't ship it.
# On macOS/Linux, `brew install tesseract` / `apt-get install tesseract-ocr`
# puts it on PATH automatically and no extra config is needed.
# On Windows, the installer usually does NOT add it to PATH, so we point
# pytesseract at the default install location if we can find it there.
#
# If your Tesseract lives somewhere else, either:
#   1) set an environment variable before running Streamlit:
#        Windows (PowerShell):  $env:TESSERACT_CMD = "C:\path\to\tesseract.exe"
#        macOS/Linux:           export TESSERACT_CMD=/path/to/tesseract
#   2) or just edit TESSERACT_CMD_OVERRIDE below with your exact path.
TESSERACT_CMD_OVERRIDE = ""  # e.g. r"C:\Program Files\Tesseract-OCR\tesseract.exe"

_env_cmd = os.environ.get("TESSERACT_CMD", "").strip()
_default_windows_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if TESSERACT_CMD_OVERRIDE:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD_OVERRIDE
elif _env_cmd:
    pytesseract.pytesseract.tesseract_cmd = _env_cmd
elif os.name == "nt" and os.path.exists(_default_windows_path):
    pytesseract.pytesseract.tesseract_cmd = _default_windows_path
# else: leave pytesseract's default, which relies on `tesseract` being on PATH
# (this is the normal case on macOS/Linux and on Windows installs where the
# "Add to PATH" checkbox was ticked during setup).


# ----------------------------------------------------------------------
# ID / OTP generation
# ----------------------------------------------------------------------
def generate_unique_id(prefix, length=6):
    suffix = "".join(random.choices(string.digits, k=length))
    return f"{prefix}-{suffix}"


def generate_otp(length=4):
    return "".join(random.choices(string.digits, k=length))


# ----------------------------------------------------------------------
# Text extraction from uploaded medical record files
# ----------------------------------------------------------------------
def _preprocess_image_for_ocr(image):
    """
    Optional accuracy boost: convert to grayscale + threshold with OpenCV
    before handing the image to Tesseract. Falls back to the original PIL
    image untouched if OpenCV isn't installed, or if anything goes wrong.
    """
    if not OPENCV_AVAILABLE:
        return image
    try:
        from PIL import Image
        arr = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return Image.fromarray(thresh)
    except Exception:
        return image


def extract_text_from_file(file_bytes, filename):
    """
    Returns extracted text (string). Supports PDF (via pdfplumber) and
    common image formats (via pytesseract OCR). Falls back gracefully
    if a library / binary is missing so the app never hard-crashes.
    """
    ext = filename.lower().split(".")[-1]
    text = ""
    try:
        if ext == "pdf":
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                pages_text = []
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    pages_text.append(page_text)
                text = "\n".join(pages_text)
        elif ext in ("png", "jpg", "jpeg", "webp", "bmp", "tiff"):
            from PIL import Image
            image = Image.open(io.BytesIO(file_bytes))
            image = _preprocess_image_for_ocr(image)
            text = pytesseract.image_to_string(image)
        else:
            text = ""
    except ImportError as e:
        text = (f"[Text extraction skipped: a required Python package is missing ({e}). "
                f"Run: pip install -r requirements.txt]")
    except Exception as e:
        err_str = str(e).lower()
        if "tesseract" in err_str and ("not installed" in err_str or "not in your path" in err_str
                                        or "no such file" in err_str):
            text = ("[Text extraction skipped: the Tesseract OCR program isn't installed on "
                    "this computer, or pytesseract can't find it (it's separate from the "
                    "pytesseract Python package). Install it - macOS: `brew install tesseract`, "
                    "Debian/Ubuntu: `sudo apt-get install tesseract-ocr`, Windows: get the "
                    "installer from https://github.com/UB-Mannheim/tesseract/wiki. If it's "
                    "installed but still not found, set TESSERACT_CMD_OVERRIDE at the top of "
                    "helpers.py to the exact path of tesseract.exe / tesseract. "
                    "The record is still saved, just without extracted text - re-upload it "
                    "after fixing this to get text extraction.]")
        else:
            text = f"[Could not automatically extract text from this file: {e}]"

    return text.strip()


# ----------------------------------------------------------------------
# Keyword based categorisation / tagging of a medical record
# ----------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    "Allergy": ["allergy", "allergic", "allergies"],
    "Surgery": ["surgery", "surgical", "operation", "operated", "post-op", "postoperative"],
    "Hospital Admission": ["admitted", "admission", "discharge summary", "in-patient", "inpatient"],
    "Lab Report": ["lab report", "laboratory", "blood test", "hemoglobin", "cbc", "urine test",
                   "pathology", "specimen"],
    "Prescription": ["prescription", "rx", "tablet", "capsule", "dosage", "mg twice", "medicine"],
    "Diabetes": ["diabetes", "diabetic", "blood sugar", "glucose", "hba1c"],
    "Hypertension": ["hypertension", "blood pressure", "bp "],
    "Cardiac": ["cardiac", "heart", "ecg", "ekg", "cardiology"],
    "Imaging": ["x-ray", "xray", "mri", "ct scan", "ultrasound", "scan report"],
    "Vaccination": ["vaccine", "vaccination", "immunization", "immunisation"],
}


def categorize_text(text):
    if not text:
        return []
    lower = text.lower()
    found = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                found.append(category)
                break
    return found


def build_summary_from_records(records):
    """Build a simple aggregated summary dict from a patient's record list."""
    if not records:
        return {"total_records": 0, "categories": {}, "recent": []}

    category_counts = {}
    for r in records:
        for cat in r.get("categories", []):
            category_counts[cat] = category_counts.get(cat, 0) + 1

    recent = [
        {"filename": r["filename"], "uploaded_at": r["uploaded_at"],
         "categories": r.get("categories", [])}
        for r in records[:5]
    ]

    return {
        "total_records": len(records),
        "categories": category_counts,
        "recent": recent,
    }


# ----------------------------------------------------------------------
# OCR text clean-up / correction
# ----------------------------------------------------------------------
# A small curated vocabulary of words that show up often in medical
# records. Used to fuzzy-correct OCR misreads (e.g. "itestyle" ->
# "lifestyle", "asthina" -> "asthma") without needing any external
# spellcheck package (there's no internet access in this environment to
# install one). This is a best-effort heuristic pass, not a real
# spellchecker - it never invents medical facts, it only repairs likely
# character-level OCR mistakes against known terms.
MEDICAL_VOCAB = [
    "allergy", "allergic", "allergies", "asthma", "hypertension", "diabetes",
    "diabetic", "lifestyle", "medication", "medicine", "medicines", "surgery",
    "surgical", "operation", "hospital", "admission", "discharge", "diagnosis",
    "diagnosed", "prescription", "dosage", "tablet", "tablets", "capsule",
    "capsules", "cardiac", "cardiology", "hemoglobin", "glucose", "cholesterol",
    "blood", "pressure", "pathology", "laboratory", "specimen", "vaccination",
    "immunization", "chronic", "acute", "managed", "controlled", "mild",
    "moderate", "severe", "changes", "history", "report", "test", "tests",
    "results", "specific", "ige", "cheese", "cheddar", "penicillin", "aspirin",
    "insulin", "thyroid", "impression", "assessment", "notes", "follow-up",
]

# Common connective English words that also show up frequently in these
# documents - kept separate from MEDICAL_VOCAB purely for readability.
COMMON_WORDS = [
    "with", "not", "identified", "from", "uploaded", "records", "and",
    "the", "for", "was", "were", "this", "that", "patient", "doctor",
    "date", "name", "advised", "please", "note", "years", "old",
]

_CORRECTION_VOCAB = sorted({w.lower() for w in MEDICAL_VOCAB + COMMON_WORDS})

# Known exact OCR misreads seen in practice - checked first (cheap, exact,
# and safer than fuzzy-guessing). A blank value means the token is
# unrecoverable OCR noise and should be dropped rather than guessed at.
KNOWN_OCR_FIXES = {
    "itestyle": "lifestyle",
    "itestyie": "lifestyle",
    "iifestyle": "lifestyle",
    "asthina": "asthma",
    "asthama": "asthma",
    "asthrna": "asthma",
    "ceeiect": "",
    "ceeject": "",
    "eter": "",
}


def _correct_word(word):
    lower = word.lower()
    if lower in KNOWN_OCR_FIXES:
        fixed = KNOWN_OCR_FIXES[lower]
        if not fixed:
            return ""  # signal: drop this token, it's unrecoverable noise
        return fixed.capitalize() if word[:1].isupper() else fixed
    if lower in _CORRECTION_VOCAB or len(word) < 4 or not word.isalpha():
        return word
    match = difflib.get_close_matches(lower, _CORRECTION_VOCAB, n=1, cutoff=0.8)
    if match:
        fixed = match[0]
        return fixed.capitalize() if word[:1].isupper() else fixed
    return word


def clean_ocr_text(text):
    """
    Best-effort clean-up of noisy OCR text. Fixes a short-list of known
    misreads and fuzzy-corrects other words against a small medical
    vocabulary, dropping tokens that are flagged as unrecoverable noise.
    Safe to call on already-clean text (e.g. from pdfplumber) - it will
    simply leave recognised words untouched.
    """
    if not text:
        return text
    tokens = re.findall(r"[A-Za-z]+|[^A-Za-z\s]+|\s+", text)
    out = []
    for tok in tokens:
        if tok.isalpha():
            out.append(_correct_word(tok))
        else:
            out.append(tok)
    cleaned = "".join(out)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return cleaned.strip()


def _is_low_quality_line(line, min_known_ratio=0.4):
    """
    Heuristic noise filter: OCR sometimes pulls in unrelated boilerplate
    (page headers/footers, insurance clauses, etc). A line is treated as
    noise and excluded from the Medical Summary if fewer than
    min_known_ratio of its alphabetic words are either short (<=3 letters,
    usually fine e.g. 'mg', 'bp') or a recognised vocabulary word.
    """
    words = re.findall(r"[A-Za-z]+", line)
    if not words:
        return True
    known = sum(1 for w in words if len(w) <= 3 or w.lower() in _CORRECTION_VOCAB)
    return (known / len(words)) < min_known_ratio


def fuzzy_text_contains(haystack, term, cutoff=0.78):
    """
    Returns True if `term` (a search query, possibly containing a small
    typo like 'allery' for 'allergy') is found in `haystack` - either as
    a plain case-insensitive substring, or via a close fuzzy match against
    the individual words that appear in haystack. Multi-word terms require
    every word in the term to be found somewhere in haystack (AND).
    Words of 3 letters or fewer skip fuzzy matching (too short to compare
    safely - e.g. 'mg', 'bp') and must match exactly.
    """
    if not term or not term.strip():
        return False
    haystack_l = haystack.lower()
    haystack_words = set(re.findall(r"[a-z]+", haystack_l))
    for word in re.findall(r"[a-z]+", term.lower()):
        if word in haystack_l:
            continue
        if len(word) <= 3:
            return False
        if not difflib.get_close_matches(word, haystack_words, n=1, cutoff=cutoff):
            return False
    return True


def find_snippet_around_term(text, term, context=120):
    """
    Finds a (start, end) character range in `text` around the search term,
    for showing a 'matching snippet' preview. Tries an exact (case-
    insensitive) match first; if the term was a typo that only fuzzy-
    matched (see fuzzy_text_contains), falls back to locating the closest-
    matching word in `text` so the snippet still lands somewhere sensible.
    Returns None if nothing reasonable is found.
    """
    if not text or not term or not term.strip():
        return None
    low = text.lower()
    idx = low.find(term.strip().lower())
    if idx != -1:
        return max(0, idx - context), min(len(text), idx + len(term) + context)
    for word in re.findall(r"[a-zA-Z]+", term):
        if len(word) <= 3:
            continue
        for m in re.finditer(r"[A-Za-z]+", text):
            if difflib.SequenceMatcher(None, m.group(0).lower(), word.lower()).ratio() >= 0.78:
                return max(0, m.start() - context), min(len(text), m.end() + context)
    return None


# ----------------------------------------------------------------------
# Structured "Medical Summary" extraction
# ----------------------------------------------------------------------
# Ordered so a sentence that matches more than one section's keywords
# lands in the first (most specific) section it matches.
SUMMARY_SECTIONS = [
    ("Allergies", ["allergy", "allergic", "allergies"]),
    ("Previous Diseases", ["hypertension", "diabetes", "diabetic", "asthma",
                           "thyroid", "chronic condition", "disease"]),
    ("Previous Surgeries", ["surgery", "surgical", "operation", "operated",
                            "post-op", "postoperative"]),
    ("Hospital History", ["admitted", "admission", "discharge", "in-patient",
                          "inpatient", "hospitalized", "hospitalised"]),
    ("Medicines", ["medication", "medicine", "tablet", "capsule", "dosage",
                  " mg", "prescribed", "prescription"]),
    ("Diagnosis", ["diagnosis", "diagnosed", "impression", "assessment"]),
    ("Lab Tests", ["lab report", "laboratory", "blood test", "hemoglobin",
                  "cbc", "urine test", "pathology", "specimen", "lab test",
                  "test result", "specific ige"]),
]


def _split_sentences(text):
    text = text.replace("\n", ". ")
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" .\n\t") for p in parts if p.strip(" .\n\t")]


def build_medical_summary(records):
    """
    Build the structured 'Medical Summary' (Allergies, Previous Diseases,
    Previous Surgeries, Hospital History, Medicines, Diagnosis, Lab Tests)
    from a patient's uploaded records.

    Each record's extracted text is first OCR-cleaned (see clean_ocr_text),
    then scanned sentence by sentence for each section's keywords. Any
    sentence that looks like low-confidence OCR noise is dropped rather
    than shown garbled. Returns an ordered dict of
    section title -> list of bullet strings (empty list = nothing
    identified for that section, which callers should render as
    "Not identified from uploaded records.").
    """
    summary = OrderedDict((title, []) for title, _ in SUMMARY_SECTIONS)
    seen = {title: set() for title, _ in SUMMARY_SECTIONS}

    for r in records or []:
        raw_text = r.get("extracted_text") or ""
        # Skip our own "[extraction skipped/failed: ...]" placeholder text.
        if not raw_text or raw_text.strip().startswith("["):
            continue
        cleaned = clean_ocr_text(raw_text)
        for sentence in _split_sentences(cleaned):
            if _is_low_quality_line(sentence):
                continue
            lower = sentence.lower()
            for title, keywords in SUMMARY_SECTIONS:
                if any(kw in lower for kw in keywords):
                    key = lower
                    if key not in seen[title]:
                        seen[title].add(key)
                        summary[title].append(sentence)
                    break  # a sentence lands in only its first matching section
    return summary


# ----------------------------------------------------------------------
# Symptom -> dynamic question trees
# ----------------------------------------------------------------------
# Each entry: list of (key, question) asked strictly one at a time.
SYMPTOM_QUESTIONS = {
    "chest pain": [
        ("duration", "Since when have you had the chest pain? (e.g. 10 minutes, 2 days)"),
        ("nature", "How would you describe the pain? (sharp / dull / crushing / burning)"),
        ("radiate", "Does the pain spread to your arm, jaw, neck or back? (yes/no, describe)"),
        ("breathlessness", "Are you feeling short of breath right now? (yes/no)"),
        ("sweating_nausea", "Any sweating, nausea or dizziness along with the pain? (yes/no)"),
        ("history", "Do you have any past history of heart disease, high BP or diabetes?"),
    ],
    "headache": [
        ("duration", "Since when have you had this headache?"),
        ("location", "Where exactly is the pain? (one side / both sides / back of head / whole head)"),
        ("severity", "On a scale of 1 to 10, how severe is the pain?"),
        ("vision", "Any blurred vision, sensitivity to light, or vision changes? (yes/no)"),
        ("vomiting", "Any vomiting or nausea along with the headache? (yes/no)"),
        ("history", "Have you had similar headaches before, or any history of migraine?"),
    ],
    "fever": [
        ("duration", "Since when do you have the fever? (in days)"),
        ("temperature", "Do you know your temperature reading? (approximate, in F or C)"),
        ("associated", "Any other symptoms with the fever? (cough, body ache, rash, sore throat, etc.)"),
        ("chills", "Are you experiencing chills or shivering? (yes/no)"),
        ("travel", "Any recent travel history or contact with a sick person?"),
    ],
}

# Fallback generic set for any other free-typed problem
GENERIC_QUESTIONS = [
    ("duration", "Since when have you had this problem?"),
    ("severity", "On a scale of 1 to 10, how severe would you say it is?"),
    ("worsen", "Is there anything that makes it worse or better?"),
    ("other_symptoms", "Are you experiencing any other symptoms along with it?"),
    ("history", "Do you have any relevant past medical history?"),
]

SYMPTOM_DEPARTMENT_MAP = {
    "chest pain": "Cardiology",
    "headache": "Neurology",
    "fever": "General Medicine",
}


def match_symptom(problem_text):
    """Match free-typed problem text to one of our known symptom trees."""
    lower = problem_text.lower()
    for key in SYMPTOM_QUESTIONS:
        if key in lower:
            return key
    return None


def get_questions_for_symptom(symptom_key):
    if symptom_key and symptom_key in SYMPTOM_QUESTIONS:
        return SYMPTOM_QUESTIONS[symptom_key]
    return GENERIC_QUESTIONS


def get_department_for_symptom(symptom_key):
    return SYMPTOM_DEPARTMENT_MAP.get(symptom_key, "General Medicine")


# ----------------------------------------------------------------------
# Red flag detection
# ----------------------------------------------------------------------
def detect_red_flag(symptom_key, answers):
    """
    answers: dict of {question_key: answer_text}
    Very simple, transparent keyword based triage logic. This is NOT a
    medical diagnosis tool - it only highlights answers that commonly
    warrant urgent in-person evaluation, so the summary can flag them.
    """
    def yes(val):
        return bool(val) and val.strip().lower().startswith(("y", "yes"))

    reasons = []

    if symptom_key == "chest pain":
        if yes(answers.get("breathlessness", "")):
            reasons.append("chest pain with shortness of breath")
        if yes(answers.get("sweating_nausea", "")):
            reasons.append("chest pain with sweating/nausea")
        radiate = (answers.get("radiate", "") or "").lower()
        if "yes" in radiate or "arm" in radiate or "jaw" in radiate:
            reasons.append("pain radiating to arm/jaw/back")

    elif symptom_key == "headache":
        if yes(answers.get("vision", "")):
            reasons.append("headache with vision changes")
        if yes(answers.get("vomiting", "")):
            reasons.append("headache with vomiting")
        try:
            sev = int("".join(ch for ch in str(answers.get("severity", "0")) if ch.isdigit()) or 0)
            if sev >= 9:
                reasons.append("extremely severe headache (9-10/10)")
        except Exception:
            pass

    elif symptom_key == "fever":
        temp_raw = (answers.get("temperature", "") or "").lower()
        digits = "".join(ch for ch in temp_raw if (ch.isdigit() or ch == "."))
        try:
            if digits:
                temp_val = float(digits)
                if ("c" in temp_raw and temp_val >= 40) or (temp_val >= 103 and "c" not in temp_raw):
                    reasons.append("very high fever")
        except Exception:
            pass
        duration_raw = (answers.get("duration", "") or "").lower()
        digits_d = "".join(ch for ch in duration_raw if ch.isdigit())
        try:
            if digits_d and int(digits_d) >= 5:
                reasons.append("fever lasting 5 or more days")
        except Exception:
            pass

    else:
        try:
            sev = int("".join(ch for ch in str(answers.get("severity", "0")) if ch.isdigit()) or 0)
            if sev >= 9:
                reasons.append("very high severity reported (9-10/10)")
        except Exception:
            pass

    return (len(reasons) > 0), reasons


def build_text_summary(symptom_label, symptom_key, answers, red_flag, reasons):
    lines = [f"Reported problem: {symptom_label}", ""]
    questions = get_questions_for_symptom(symptom_key)
    for key, question in questions:
        ans = answers.get(key, "Not answered")
        lines.append(f"Q: {question}")
        lines.append(f"A: {ans}")
        lines.append("")
    if red_flag:
        lines.append("RED FLAG: The following responses may indicate a condition that "
                      "needs urgent in-person medical evaluation:")
        for r in reasons:
            lines.append(f" - {r}")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# PDF generation (uses reportlab, always available in this environment)
# ----------------------------------------------------------------------
def generate_symptom_pdf(output_path, patient_name, patient_id, symptom_label,
                          symptom_key, answers, red_flag, reasons, hospital_suggestions=None):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                     TableStyle, HRFlowable)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleStyle", parent=styles["Title"], fontSize=18)
    normal = styles["Normal"]
    heading = styles["Heading2"]

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                             topMargin=18 * mm, bottomMargin=18 * mm,
                             leftMargin=18 * mm, rightMargin=18 * mm)
    story = []

    if red_flag:
        flag_style = ParagraphStyle(
            "RedFlag", parent=styles["Normal"], textColor=colors.white,
            backColor=colors.HexColor("#c0392b"), fontSize=13, leading=16,
            spaceAfter=10, spaceBefore=0, alignment=1, borderPadding=8,
        )
        story.append(Paragraph(
            "RED FLAG - POSSIBLE URGENT CONDITION - PLEASE SEEK "
            "IMMEDIATE MEDICAL ATTENTION", flag_style))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Patient Symptom Summary", title_style))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", color=colors.grey))
    story.append(Spacer(1, 8))

    meta_table = Table([
        ["Patient Name", patient_name or "-"],
        ["Patient ID", patient_id],
        ["Reported Problem", symptom_label],
        ["Generated On", datetime.now().strftime("%d %b %Y, %I:%M %p")],
    ], colWidths=[45 * mm, 120 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#333333")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Questions &amp; Answers", heading))
    story.append(Spacer(1, 4))

    questions = get_questions_for_symptom(symptom_key)
    qa_rows = [["Question", "Answer"]]
    for key, question in questions:
        qa_rows.append([question, answers.get(key, "Not answered")])

    qa_table = Table(qa_rows, colWidths=[95 * mm, 70 * mm])
    qa_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(qa_table)
    story.append(Spacer(1, 14))

    if red_flag:
        story.append(Paragraph("Reasons for Red Flag", heading))
        for r in reasons:
            story.append(Paragraph(f"- {r}", normal))
        story.append(Spacer(1, 12))

    if hospital_suggestions:
        story.append(Paragraph("Suggested Hospitals (based on reviews near you)", heading))
        rows = [["Hospital", "Department", "Avg Rating", "Reviews"]]
        for h in hospital_suggestions:
            rating = h.get("avg_rating")
            rating_str = f"{rating:.1f}" if isinstance(rating, (int, float)) else "-"
            rows.append([h.get("hospital_name", "-"), h.get("department", "-"),
                         rating_str, str(h.get("review_count", 0))])
        hosp_table = Table(rows, colWidths=[55 * mm, 45 * mm, 30 * mm, 30 * mm])
        hosp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#27632a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(hosp_table)
        story.append(Spacer(1, 10))

    story.append(Spacer(1, 10))
    disclaimer = ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=8,
                                 textColor=colors.grey)
    story.append(Paragraph(
        "This summary is generated from patient-reported answers using a simple keyword "
        "based check. It is not a medical diagnosis. Please consult a qualified doctor "
        "for evaluation and treatment.", disclaimer))

    doc.build(story)
    return output_path