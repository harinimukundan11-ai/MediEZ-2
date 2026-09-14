"""
app.py
A unified Streamlit prototype with two interfaces:
  1. Patient interface
  2. Hospital interface

Run with:  streamlit run app.py

NOTE ON OTP DELIVERY (read me):
This is a self-contained prototype with no SMS/Email gateway wired up, and
no internet access at build time. Every place that would normally send an
OTP by SMS/e-mail instead displays it on-screen in a blue "simulated
message" banner. In a real deployment you would swap `simulate_send_otp()`
for a call to an SMS/email provider (Twilio, MSG91, SMTP, etc.) and stop
displaying the OTP directly.
"""

import streamlit as st
import os
from datetime import datetime

import db
import helpers

st.set_page_config(page_title="MediEZ", page_icon="🩺", layout="wide")
db.init_db()


# ============================================================================
# Small shared utilities
# ============================================================================
def simulate_send_otp(channel_label, destination, otp):
    st.info(f"📩 Simulated {channel_label} to **{destination}** — OTP: **{otp}**  \n"
            f"*(In production this would be sent silently via SMS/Email, not shown here.)*")


def init_state():
    defaults = {
        "interface": None,          # None | 'patient' | 'hospital'
        "patient_logged_in": False,
        "patient_id": None,
        "patient_login_stage": "id_entry",   # id_entry | otp_entry
        "patient_pending_id": None,
        "hospital_logged_in": False,
        "hospital_id": None,
        "hospital_login_stage": "id_entry",
        "hospital_pending_id": None,
        "symptom_flow": None,        # dict describing in-progress symptom Q&A
        "hospital_view_patient": None,   # patient_id currently unlocked for viewing
        "hospital_access_stage": "request",  # request | otp
        "hospital_access_pending_pid": None,
        "rx_medicines": [{}],        # list of medicine dicts being built in the prescription form
        "patient_current_otp": None,
        "hospital_current_otp": None,
        "hospital_access_current_otp": None,
        "patient_search_medical_history_active": False,  # was a search actually run (vs just typed)?
        "patient_search_medical_history_term": "",        # the term that search was last run with
        "hospital_search_medical_history_active": False,
        "hospital_search_medical_history_term": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


def go_home():
    for key in ["interface", "patient_logged_in", "patient_id", "patient_login_stage",
                "patient_pending_id", "hospital_logged_in", "hospital_id",
                "hospital_login_stage", "hospital_pending_id", "symptom_flow",
                "hospital_view_patient", "hospital_access_stage",
                "hospital_access_pending_pid", "rx_medicines",
                "patient_current_otp", "hospital_current_otp",
                "hospital_access_current_otp",
                "patient_search_medical_history_active", "patient_search_medical_history_term",
                "hospital_search_medical_history_active", "hospital_search_medical_history_term"]:
        del st.session_state[key]
    init_state()


# ============================================================================
# Landing page
# ============================================================================
def render_landing():
    st.title("🩺 UnifiedHealth")
    st.caption("One platform connecting patients and hospitals.")
    st.write("")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("I'm a Patient")
        st.write("Store your medical records, track prescriptions, and get quick "
                 "guidance for current health problems.")
        if st.button("Continue as Patient", use_container_width=True, type="primary"):
            st.session_state.interface = "patient"
            st.rerun()
    with col2:
        st.subheader("I'm a Hospital")
        st.write("Manage doctors, securely view patient records with consent, "
                 "and issue digital prescriptions.")
        if st.button("Continue as Hospital", use_container_width=True, type="primary"):
            st.session_state.interface = "hospital"
            st.rerun()


# ============================================================================
# PATIENT: Sign up / Login
# ============================================================================
def render_patient_auth():
    st.title("🧑‍⚕️ Patient Portal")
    if st.button("⬅ Back to home"):
        go_home()
        st.rerun()

    tab_signup, tab_login = st.tabs(["New here? Sign up", "Already registered? Log in"])

    with tab_signup:
        st.subheader("Create your patient account")
        with st.form("patient_signup_form"):
            name = st.text_input("Full name")
            phone = st.text_input("Phone number")
            age = st.text_input("Age")
            gender = st.selectbox("Gender", ["Female", "Male", "Other", "Prefer not to say"])
            location = st.text_input("City / Location")
            submitted = st.form_submit_button("Sign up", type="primary")

        if submitted:
            if not name.strip() or not phone.strip():
                st.error("Please enter at least your name and phone number.")
            else:
                new_id = helpers.generate_unique_id("PT")
                while db.patient_id_exists(new_id):
                    new_id = helpers.generate_unique_id("PT")
                db.create_patient(new_id, name.strip(), phone.strip(), age, gender, location)
                st.success("Account created successfully!")
                st.warning(
                    f"### Your unique Patient ID is: `{new_id}`\n"
                    "Please **note this down safely** — you'll need it to log in on any device."
                )

    with tab_login:
        st.subheader("Log in")
        if st.session_state.patient_login_stage == "id_entry":
            pid = st.text_input("Enter your Patient ID", key="patient_login_id_input")
            if st.button("Send OTP", key="patient_send_otp"):
                if not pid.strip():
                    st.error("Please enter your Patient ID.")
                elif not db.patient_id_exists(pid.strip()):
                    st.error("No patient found with this ID. Please check and try again.")
                else:
                    otp = helpers.generate_otp()
                    db.set_login_otp("patient", pid.strip(), otp)
                    st.session_state.patient_pending_id = pid.strip()
                    st.session_state.patient_login_stage = "otp_entry"
                    st.session_state.patient_current_otp = otp
                    st.rerun()
        else:
            pid = st.session_state.patient_pending_id
            patient = db.get_patient(pid)
            phone = patient["phone"] if patient else "your registered phone"
            st.write(f"Logging in as **{pid}**")
            simulate_send_otp("SMS", phone, st.session_state.get("patient_current_otp", ""))
            if st.button("Resend OTP"):
                otp = helpers.generate_otp()
                db.set_login_otp("patient", pid, otp)
                st.session_state.patient_current_otp = otp
                st.rerun()

            entered_otp = st.text_input("Enter OTP", key="patient_otp_input", max_chars=6)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Verify & Log in", type="primary"):
                    if db.verify_login_otp("patient", pid, entered_otp.strip()):
                        st.session_state.patient_logged_in = True
                        st.session_state.patient_id = pid
                        st.session_state.patient_login_stage = "id_entry"
                        st.rerun()
                    else:
                        st.error("Invalid or expired OTP. Please resend and try again.")
            with c2:
                if st.button("⬅ Use a different ID"):
                    st.session_state.patient_login_stage = "id_entry"
                    st.session_state.patient_pending_id = None
                    st.rerun()


# ============================================================================
# PATIENT: Dashboard
# ============================================================================
def render_patient_dashboard():
    patient = db.get_patient(st.session_state.patient_id)
    with st.sidebar:
        st.markdown(f"### 👋 {patient['name'] if patient else ''}")
        st.caption(f"Patient ID: `{st.session_state.patient_id}`")
        if st.button("Log out"):
            go_home()
            st.rerun()

    st.title("🧑‍⚕️ Patient Dashboard")
    tabs = st.tabs([
        "📁 Add Medical Records",
        "📄 Medical Summary",
        "🔎 Search Medical History",
        "📊 View Report",
        "🤒 Current Problem",
        "💊 Prescriptions",
        "⭐ Add Review",
    ])

    with tabs[0]:
        render_add_medical_records()
    with tabs[1]:
        render_medical_summary(db.get_records_for_patient(st.session_state.patient_id))
    with tabs[2]:
        render_search_medical_history(st.session_state.patient_id, key_prefix="patient")
    with tabs[3]:
        render_view_report()
    with tabs[4]:
        render_current_problem()
    with tabs[5]:
        render_view_prescriptions()
    with tabs[6]:
        render_add_review()


def render_add_medical_records():
    st.subheader("Add a medical record")
    st.write("Upload a photo or PDF of a report, prescription, discharge summary, etc. "
             "We'll automatically extract and index the text so you can search it later.")
    uploaded = st.file_uploader(
        "Choose a file", type=["pdf", "png", "jpg", "jpeg", "webp", "bmp", "tiff"]
    )
    if uploaded is not None:
        if st.button("Extract & Save", type="primary"):
            with st.spinner("Extracting text from your document..."):
                file_bytes = uploaded.getvalue()
                text = helpers.extract_text_from_file(file_bytes, uploaded.name)
                categories = helpers.categorize_text(text)

                safe_name = f"{st.session_state.patient_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded.name}"
                stored_path = os.path.join(db.UPLOAD_DIR, safe_name)
                try:
                    with open(stored_path, "wb") as f:
                        f.write(file_bytes)
                except Exception:
                    stored_path = ""

                ext = uploaded.name.lower().split(".")[-1]
                db.add_record(st.session_state.patient_id, uploaded.name, stored_path,
                               ext, text, categories)

            st.success("Record saved and text extracted!")
            if categories:
                st.write("**Detected tags:** " + ", ".join(categories))
            else:
                st.write("No specific tags detected automatically — the record was still saved.")
            with st.expander("Preview extracted text"):
                st.text(text if text else "(No text could be extracted from this file.)")

    st.divider()
    st.write("#### Your uploaded records")
    records = db.get_records_for_patient(st.session_state.patient_id)
    if not records:
        st.caption("No records uploaded yet.")
    else:
        for r in records:
            with st.expander(f"{r['filename']}  —  {r['uploaded_at']}"):
                if r["categories"]:
                    st.write("**Tags:** " + ", ".join(r["categories"]))
                st.text(r["extracted_text"][:2000] if r["extracted_text"] else "(no extracted text)")


def render_medical_summary(records, hospital_view=False):
    """Renders the structured 'MEDICAL SUMMARY' (Allergies, Previous Diseases,
    Previous Surgeries, Hospital History, Medicines, Diagnosis, Lab Tests),
    built from OCR/PDF-extracted text that's been cleaned of common OCR
    misreads and noise (see helpers.clean_ocr_text / build_medical_summary)."""
    st.markdown("## MEDICAL SUMMARY")
    if not records:
        st.caption("Upload some records to generate a medical summary here.")
        return
    summary = helpers.build_medical_summary(records)
    for section, items in summary.items():
        st.markdown(f"**{section}:**")
        if items:
            for item in items:
                st.write(f"- {item}")
        else:
            st.write("Not identified from uploaded records.")
        st.write("")


def _filter_records_by_keyword(records, term):
    """
    Matches a search term against filename, detected tags, AND the
    OCR-cleaned/corrected extracted text (not the raw DB text) - so a
    record whose scanned text was mangled by OCR (e.g. 'allergy' read as
    'ailergy') still matches once helpers.clean_ocr_text has fixed it up.
    Also tolerates small typos in the search term itself (e.g. typing
    'allery' still finds 'allergy') via helpers.fuzzy_text_contains.
    This keeps search results consistent with what the Medical Summary
    tab detects, since that tab matches on cleaned text too.
    """
    matched = []
    for r in records:
        cleaned = helpers.clean_ocr_text(r.get("extracted_text") or "")
        haystack = " ".join([
            r.get("filename") or "",
            cleaned,
            " ".join(r.get("categories") or []),
        ])
        if helpers.fuzzy_text_contains(haystack, term):
            matched.append(r)
    return matched


def render_search_medical_history(patient_id, key_prefix="patient"):
    """Renders a standalone 'Search Medical History' page: a search box
    with a placeholder + Search button, followed by an 'Uploaded Records'
    list (all records, or search matches when a search has been run).

    Reusable for both the patient's own dashboard and a hospital's view of
    a patient's record - key_prefix keeps each caller's widget/session keys
    separate so the two never collide or leak search state into each other.

    The search result has to survive Streamlit's rerun-on-every-interaction
    model (e.g. clicking to expand a record below shouldn't silently revert
    the list back to "all records"), so the last-run search term is kept in
    st.session_state rather than relying only on the button's return value.
    """
    active_key = f"{key_prefix}_search_medical_history_active"
    term_key = f"{key_prefix}_search_medical_history_term"

    st.subheader("Search Medical History")
    keyword = st.text_input(
        "Search",
        key=f"{key_prefix}_search_medical_history_kw",
        placeholder="allergy, surgery, hospital, medicine, diagnosis...",
    )
    if st.button("Search", key=f"{key_prefix}_search_medical_history_btn"):
        st.session_state[term_key] = keyword.strip()
        st.session_state[active_key] = bool(keyword.strip())

    st.divider()
    st.write("### Uploaded Records")

    active = st.session_state.get(active_key, False)
    term = st.session_state.get(term_key, "")

    all_records = db.get_records_for_patient(patient_id)
    if active and term:
        records = _filter_records_by_keyword(all_records, term)
        if not records:
            st.warning("No matching records found.")
    else:
        records = all_records

    if not records:
        st.caption("No records uploaded yet.")
    for r in records:
        with st.expander(f"{r['filename']} — {r['uploaded_at']}"):
            if r["categories"]:
                st.write("**Tags:** " + ", ".join(r["categories"]))
            cleaned = helpers.clean_ocr_text(r["extracted_text"] or "")
            if active and term:
                span = helpers.find_snippet_around_term(cleaned, term)
                if span:
                    start, end = span
                    st.write("**Matching snippet:**")
                    st.caption(f"...{cleaned[start:end]}...")
            st.text(cleaned[:2000] if cleaned else "(no extracted text)")


def render_view_report():
    st.subheader("Your health summary")
    st.write("#### 🚩 Past symptom-check summaries")
    sessions = db.get_symptom_sessions(st.session_state.patient_id)
    if not sessions:
        st.caption("No symptom checks recorded yet — try 'Current Problem' tab.")
    else:
        for s in sessions:
            flag_txt = " 🔴 RED FLAG" if s["red_flag"] else ""
            with st.expander(f"{s['symptom']}{flag_txt} — {s['created_at']}"):
                st.text(s["summary"])
                if s["pdf_path"] and os.path.exists(s["pdf_path"]):
                    with open(s["pdf_path"], "rb") as f:
                        st.download_button("Download PDF summary", f, file_name=os.path.basename(s["pdf_path"]),
                                            key=f"dl_{s['session_id']}")


def render_view_prescriptions():
    st.subheader("Prescriptions issued by your doctors")
    rxs = db.get_prescriptions_for_patient(st.session_state.patient_id)
    if not rxs:
        st.caption("No prescriptions have been added for you yet.")
        return
    for rx in rxs:
        with st.expander(f"{rx['created_at']} — Dr. {rx.get('doctor_name','')} "
                          f"({rx.get('doctor_department','')}) at {rx.get('hospital_name','')}"):
            if rx["medicines"]:
                st.write("**Medicines:**")
                for m in rx["medicines"]:
                    timing = ", ".join([t for t in ["Morning" if m.get("morning") else "",
                                                     "Evening" if m.get("evening") else "",
                                                     "Night" if m.get("night") else ""] if t])
                    food = m.get("food", "-")
                    st.write(f"- **{m.get('name','-')}** | Timing: {timing or '-'} | "
                             f"{food} food | Dosage: {m.get('dosage','-')} | "
                             f"Duration: {m.get('days','-')} day(s)")
            if rx["lab_tests"]:
                st.write("**Lab tests advised:**")
                for lt in rx["lab_tests"]:
                    st.write(f"- {lt}")
            if rx.get("notes"):
                st.write(f"**Notes:** {rx['notes']}")


def render_current_problem():
    st.subheader("Tell us what's going on")

    flow = st.session_state.symptom_flow

    if flow is None:
        st.write("Describe your current problem in your own words (e.g. *chest pain*, "
                 "*headache*, *fever*, or anything else you're experiencing).")
        problem_text = st.text_input("What's the problem?", key="problem_text_input")
        if st.button("Start", type="primary"):
            if not problem_text.strip():
                st.error("Please describe your problem first.")
            else:
                symptom_key = helpers.match_symptom(problem_text)
                questions = helpers.get_questions_for_symptom(symptom_key)
                st.session_state.symptom_flow = {
                    "label": problem_text.strip(),
                    "symptom_key": symptom_key,
                    "questions": questions,
                    "q_index": 0,
                    "answers": {},
                }
                st.rerun()
        return

    questions = flow["questions"]
    idx = flow["q_index"]

    if idx < len(questions):
        key, question = questions[idx]
        st.progress(idx / len(questions))
        st.write(f"**{question}**")
        answer = st.text_input("Your answer", key=f"symptom_answer_{idx}")
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Next ➡", type="primary"):
                if not answer.strip():
                    st.error("Please type an answer to continue.")
                else:
                    flow["answers"][key] = answer.strip()
                    flow["q_index"] += 1
                    st.session_state.symptom_flow = flow
                    st.rerun()
        with c2:
            if st.button("Cancel"):
                st.session_state.symptom_flow = None
                st.rerun()
        return

    # All questions answered -> build summary
    st.success("Thanks — here's your summary.")
    symptom_key = flow["symptom_key"]
    answers = flow["answers"]
    label = flow["label"]

    red_flag, reasons = helpers.detect_red_flag(symptom_key, answers)
    summary_text = helpers.build_text_summary(label, symptom_key, answers, red_flag, reasons)

    if red_flag:
        st.error("🔴 RED FLAG — your answers suggest this may need urgent medical attention. "
                 "Please consider visiting a hospital promptly.")
        for r in reasons:
            st.write(f"- {r}")
    else:
        st.info("No urgent red flags detected from your answers, but please consult a doctor "
                "if symptoms persist or worsen.")

    with st.expander("Full summary", expanded=True):
        st.text(summary_text)

    department = helpers.get_department_for_symptom(symptom_key)
    patient = db.get_patient(st.session_state.patient_id)
    location = (patient or {}).get("location", "")
    hospitals = db.get_reviews_ranked(department=department, location=location)
    if not hospitals:
        hospitals = db.get_reviews_ranked(department=department)

    if hospitals:
        st.write(f"#### 🏥 Suggested hospitals for {department}")
        for h in hospitals[:5]:
            st.write(f"- **{h['hospital_name']}** ({h['location'] or 'location N/A'}) — "
                     f"⭐ {h['avg_rating']:.1f} avg from {h['review_count']} review(s)")
    else:
        st.caption(f"No community reviews yet for {department} in our system — "
                   "once patients start adding reviews, suggestions will appear here.")

    if st.button("Generate PDF summary", type="primary"):
        pdf_filename = f"{st.session_state.patient_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_summary.pdf"
        pdf_path = os.path.join(db.PDF_DIR, pdf_filename)
        try:
            helpers.generate_symptom_pdf(
                pdf_path, patient["name"] if patient else "", st.session_state.patient_id,
                label, symptom_key, answers, red_flag, reasons, hospitals[:5]
            )
            db.add_symptom_session(st.session_state.patient_id, label, answers, summary_text,
                                    red_flag, department, pdf_path)
            st.success("PDF generated and saved to your report history!")
            with open(pdf_path, "rb") as f:
                st.download_button("⬇ Download PDF now", f, file_name=pdf_filename)
        except Exception as e:
            st.error(f"Could not generate PDF: {e}")

    if st.button("Start a new symptom check"):
        st.session_state.symptom_flow = None
        st.rerun()


def render_add_review():
    st.subheader("Add a hospital review")
    st.write("Help other patients by sharing your experience.")
    with st.form("add_review_form"):
        hospital_name = st.text_input("Hospital name")
        department = st.text_input("Department (e.g. Cardiology, General Medicine)")
        location = st.text_input("Location / City")
        rating = st.slider("Rating", 1, 5, 4)
        review_text = st.text_area("Your review")
        submitted = st.form_submit_button("Submit review", type="primary")
    if submitted:
        if not hospital_name.strip() or not department.strip():
            st.error("Please enter at least the hospital name and department.")
        else:
            db.add_review(hospital_name.strip(), department.strip(), location.strip(),
                           rating, review_text.strip(), st.session_state.patient_id)
            st.success("Thank you! Your review has been added.")

    st.divider()
    st.write("#### Recent reviews")
    reviews = db.get_all_reviews()[:10]
    if not reviews:
        st.caption("No reviews yet — be the first to add one!")
    for r in reviews:
        st.write(f"**{r['hospital_name']}** — {r['department']} — {'⭐' * r['rating']}")
        if r["review_text"]:
            st.caption(r["review_text"])
        st.write("---")


# ============================================================================
# HOSPITAL: Sign up / Login
# ============================================================================
def render_hospital_auth():
    st.title("🏥 Hospital Portal")
    if st.button("⬅ Back to home"):
        go_home()
        st.rerun()

    tab_signup, tab_login = st.tabs(["New here? Sign up", "Already registered? Log in"])

    with tab_signup:
        st.subheader("Register your hospital")
        with st.form("hospital_signup_form"):
            name = st.text_input("Hospital name")
            phone = st.text_input("Contact phone number")
            location = st.text_input("Location / City")
            submitted = st.form_submit_button("Sign up", type="primary")
        if submitted:
            if not name.strip() or not phone.strip():
                st.error("Please enter at least the hospital name and phone number.")
            else:
                new_id = helpers.generate_unique_id("HOS")
                while db.hospital_id_exists(new_id):
                    new_id = helpers.generate_unique_id("HOS")
                db.create_hospital(new_id, name.strip(), phone.strip(), location.strip())
                st.success("Hospital account created!")
                st.warning(
                    f"### Your unique Hospital ID is: `{new_id}`\n"
                    "Please **note this down safely** — you'll need it to log in on any device."
                )

    with tab_login:
        st.subheader("Log in")
        if st.session_state.hospital_login_stage == "id_entry":
            hid = st.text_input("Enter your Hospital ID", key="hospital_login_id_input")
            if st.button("Send OTP", key="hospital_send_otp"):
                if not hid.strip():
                    st.error("Please enter your Hospital ID.")
                elif not db.hospital_id_exists(hid.strip()):
                    st.error("No hospital found with this ID. Please check and try again.")
                else:
                    otp = helpers.generate_otp()
                    db.set_login_otp("hospital", hid.strip(), otp)
                    st.session_state.hospital_pending_id = hid.strip()
                    st.session_state.hospital_login_stage = "otp_entry"
                    st.session_state.hospital_current_otp = otp
                    st.rerun()
        else:
            hid = st.session_state.hospital_pending_id
            hospital = db.get_hospital(hid)
            phone = hospital["phone"] if hospital else "your registered phone"
            st.write(f"Logging in as **{hid}**")
            simulate_send_otp("SMS", phone, st.session_state.get("hospital_current_otp", ""))
            if st.button("Resend OTP"):
                otp = helpers.generate_otp()
                db.set_login_otp("hospital", hid, otp)
                st.session_state.hospital_current_otp = otp
                st.rerun()

            entered_otp = st.text_input("Enter OTP", key="hospital_otp_input", max_chars=6)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Verify & Log in", type="primary"):
                    if db.verify_login_otp("hospital", hid, entered_otp.strip()):
                        st.session_state.hospital_logged_in = True
                        st.session_state.hospital_id = hid
                        st.session_state.hospital_login_stage = "id_entry"
                        st.rerun()
                    else:
                        st.error("Invalid or expired OTP. Please resend and try again.")
            with c2:
                if st.button("⬅ Use a different ID"):
                    st.session_state.hospital_login_stage = "id_entry"
                    st.session_state.hospital_pending_id = None
                    st.rerun()


# ============================================================================
# HOSPITAL: Dashboard
# ============================================================================
def render_hospital_dashboard():
    hospital = db.get_hospital(st.session_state.hospital_id)
    with st.sidebar:
        st.markdown(f"### 🏥 {hospital['name'] if hospital else ''}")
        st.caption(f"Hospital ID: `{st.session_state.hospital_id}`")
        if st.button("Log out"):
            go_home()
            st.rerun()

    st.title("🏥 Hospital Dashboard")
    tabs = st.tabs(["➕ Add Doctor", "🔐 View Patient Record", "👨‍⚕️ View Doctor Details"])

    with tabs[0]:
        render_add_doctor()
    with tabs[1]:
        render_view_patient_record()
    with tabs[2]:
        render_view_doctor_details()


def render_add_doctor():
    st.subheader("Add a doctor")
    with st.form("add_doctor_form"):
        name = st.text_input("Doctor's name")
        phone = st.text_input("Phone number")
        email = st.text_input("Email address")
        department = st.text_input("Department (e.g. Cardiology, General Medicine, Neurology)")
        submitted = st.form_submit_button("Add Doctor", type="primary")
    if submitted:
        if not name.strip() or not email.strip():
            st.error("Please enter at least the doctor's name and email.")
        else:
            new_id = helpers.generate_unique_id("DOC")
            while db.get_doctor(new_id):
                new_id = helpers.generate_unique_id("DOC")
            db.create_doctor(new_id, st.session_state.hospital_id, name.strip(),
                              phone.strip(), email.strip(), department.strip())
            st.success("Doctor added successfully!")
            simulate_send_otp("Email", email.strip(), new_id)
            st.warning(f"### Doctor ID: `{new_id}`\nShare this with the doctor — "
                       "they'll need it to add prescriptions.")

    st.divider()
    st.write("#### Doctors at your hospital")
    doctors = db.get_doctors_for_hospital(st.session_state.hospital_id)
    if not doctors:
        st.caption("No doctors added yet.")
    else:
        for d in doctors:
            st.write(f"- **{d['name']}** ({d['department'] or 'Dept N/A'}) — ID: `{d['doctor_id']}`")


def render_view_patient_record():
    st.subheader("View a patient's record")
    st.caption("For privacy, an OTP is sent to the patient's registered phone. "
               "Ask the patient to read it out to you before you can view their records.")

    if st.session_state.hospital_view_patient:
        pid = st.session_state.hospital_view_patient
        patient = db.get_patient(pid)
        st.success(f"Access granted to records of **{patient['name'] if patient else pid}** (`{pid}`)")
        if st.button("🔒 Close this patient's record"):
            st.session_state.hospital_view_patient = None
            st.session_state.hospital_access_stage = "request"
            st.session_state.hospital_search_medical_history_active = False
            st.session_state.hospital_search_medical_history_term = ""
            st.rerun()

        records = db.get_records_for_patient(pid)

        with st.expander("📄 Medical Summary", expanded=True):
            render_medical_summary(records, hospital_view=True)

        with st.expander("🔎 Search Medical History", expanded=False):
            render_search_medical_history(pid, key_prefix="hospital")

        summary = helpers.build_summary_from_records(records)
        c1, c2 = st.columns(2)
        c1.metric("Total records", summary["total_records"])
        c2.metric("Categories detected", len(summary["categories"]))
        if summary["categories"]:
            st.write("**Category breakdown:** " +
                     ", ".join(f"{k} ({v})" for k, v in summary["categories"].items()))

        with st.expander("📁 All medical records"):
            if not records:
                st.caption("No records on file.")
            for r in records:
                st.write(f"**{r['filename']}** — {r['uploaded_at']}")
                if r["categories"]:
                    st.caption("Tags: " + ", ".join(r["categories"]))
                st.text(r["extracted_text"][:1500] if r["extracted_text"] else "(no extracted text)")
                st.write("---")

        with st.expander("🚩 Symptom-check summaries"):
            sessions = db.get_symptom_sessions(pid)
            if not sessions:
                st.caption("No symptom checks recorded.")
            for s in sessions:
                flag_txt = " 🔴 RED FLAG" if s["red_flag"] else ""
                st.write(f"**{s['symptom']}{flag_txt}** — {s['created_at']}")
                st.text(s["summary"])
                st.write("---")

        with st.expander("💊 Existing prescriptions"):
            rxs = db.get_prescriptions_for_patient(pid)
            if not rxs:
                st.caption("No prescriptions on file yet.")
            for rx in rxs:
                st.write(f"{rx['created_at']} — Dr. {rx.get('doctor_name','')} "
                         f"({rx.get('doctor_department','')})")

        st.divider()
        render_add_prescription_section(pid)
        return

    # --- Access flow: no patient unlocked yet ---
    if st.session_state.hospital_access_stage == "request":
        pid = st.text_input("Enter Patient ID")
        if st.button("Send OTP to patient's phone", type="primary"):
            if not pid.strip():
                st.error("Please enter a Patient ID.")
            elif not db.patient_id_exists(pid.strip()):
                st.error("No patient found with this ID.")
            else:
                otp = helpers.generate_otp()
                db.set_access_otp(st.session_state.hospital_id, pid.strip(), otp)
                st.session_state.hospital_access_pending_pid = pid.strip()
                st.session_state.hospital_access_stage = "otp"
                st.session_state.hospital_access_current_otp = otp
                st.rerun()
    else:
        pid = st.session_state.hospital_access_pending_pid
        patient = db.get_patient(pid)
        st.write(f"Requesting access to patient **{pid}**")
        simulate_send_otp("SMS", patient["phone"] if patient else "patient's phone",
                           st.session_state.get("hospital_access_current_otp", ""))
        if st.button("Resend OTP"):
            otp = helpers.generate_otp()
            db.set_access_otp(st.session_state.hospital_id, pid, otp)
            st.session_state.hospital_access_current_otp = otp
            st.rerun()
        entered_otp = st.text_input("Enter the OTP the patient tells you", max_chars=6)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Verify OTP & Open Record", type="primary"):
                if db.verify_access_otp(st.session_state.hospital_id, pid, entered_otp.strip()):
                    st.session_state.hospital_view_patient = pid
                    st.rerun()
                else:
                    st.error("Invalid or expired OTP.")
        with c2:
            if st.button("⬅ Enter a different Patient ID"):
                st.session_state.hospital_access_stage = "request"
                st.session_state.hospital_access_pending_pid = None
                st.rerun()


def render_add_prescription_section(patient_id):
    st.write("#### ➕ Add Prescription")
    doctor_id = st.text_input("Doctor ID (to authorize this prescription)",
                               key="rx_doctor_id_input")
    if not doctor_id.strip():
        st.caption("Enter a valid Doctor ID from this hospital to unlock the prescription form.")
        return

    if not db.doctor_belongs_to_hospital(doctor_id.strip(), st.session_state.hospital_id):
        st.error("This Doctor ID was not found at your hospital.")
        return

    doctor = db.get_doctor(doctor_id.strip())
    st.success(f"Verified: Dr. {doctor['name']} ({doctor['department'] or 'N/A'})")

    st.write("**Medicines**")
    for i, med in enumerate(st.session_state.rx_medicines):
        with st.container(border=True):
            cols = st.columns([3, 1, 1, 1])
            med["name"] = cols[0].text_input("Medicine name", key=f"med_name_{i}",
                                              value=med.get("name", ""))
            med["morning"] = cols[1].checkbox("Morning", key=f"med_morning_{i}",
                                               value=med.get("morning", False))
            med["evening"] = cols[2].checkbox("Evening", key=f"med_evening_{i}",
                                               value=med.get("evening", False))
            med["night"] = cols[3].checkbox("Night", key=f"med_night_{i}",
                                             value=med.get("night", False))
            cols2 = st.columns([1, 1, 1])
            med["food"] = cols2[0].radio("Food timing", ["Before food", "After food"],
                                          key=f"med_food_{i}", horizontal=True)
            med["dosage"] = cols2[1].text_input("Dosage (e.g. 500mg)", key=f"med_dosage_{i}",
                                                 value=med.get("dosage", ""))
            med["days"] = cols2[2].number_input("No. of days", min_value=1, max_value=365,
                                                 value=int(med.get("days") or 1), key=f"med_days_{i}")

    add_col, rm_col = st.columns(2)
    with add_col:
        if st.button("+ Add another medicine"):
            st.session_state.rx_medicines.append({})
            st.rerun()
    with rm_col:
        if len(st.session_state.rx_medicines) > 1 and st.button("- Remove last medicine"):
            st.session_state.rx_medicines.pop()
            st.rerun()

    lab_tests_raw = st.text_area("Lab test name(s) — one per line (optional)")
    notes = st.text_area("Additional notes (optional)")

    if st.button("Save Prescription", type="primary"):
        medicines = [m for m in st.session_state.rx_medicines if m.get("name", "").strip()]
        if not medicines:
            st.error("Please add at least one medicine with a name.")
        else:
            lab_tests = [t.strip() for t in lab_tests_raw.splitlines() if t.strip()]
            db.add_prescription(patient_id, doctor_id.strip(), st.session_state.hospital_id,
                                 medicines, lab_tests, notes.strip())
            st.success("Prescription saved!")
            st.session_state.rx_medicines = [{}]
            st.rerun()


def render_view_doctor_details():
    st.subheader("Doctors at your hospital")
    doctors = db.get_doctors_for_hospital(st.session_state.hospital_id)
    if not doctors:
        st.caption("No doctors added yet. Use the 'Add Doctor' tab first.")
        return
    for d in doctors:
        with st.expander(f"{d['name']} — {d['department'] or 'Dept N/A'}  (ID: {d['doctor_id']})"):
            st.write(f"📞 {d['phone'] or '-'}  |  ✉ {d['email'] or '-'}")
            st.write(f"Added on: {d['created_at']}")
            st.write("**Prescriptions issued by this doctor:**")
            rxs = db.get_prescriptions_by_doctor(d["doctor_id"])
            if not rxs:
                st.caption("No prescriptions issued yet.")
            for rx in rxs:
                st.write(f"- {rx['created_at']} — Patient: {rx.get('patient_name','')} "
                         f"(`{rx['patient_id']}`) — {len(rx['medicines'])} medicine(s)")


# ============================================================================
# Router
# ============================================================================
def main():
    if st.session_state.interface is None:
        render_landing()
    elif st.session_state.interface == "patient":
        if st.session_state.patient_logged_in:
            render_patient_dashboard()
        else:
            render_patient_auth()
    elif st.session_state.interface == "hospital":
        if st.session_state.hospital_logged_in:
            render_hospital_dashboard()
        else:
            render_hospital_auth()


if __name__ == "__main__":
    main()