"""Patients — directory, search, filters, and patient creation."""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.services.schemas import AnalysisStatus, Patient
from app.ui import components as C
from app.ui.shell import nav_to, param
from app.pages_impl.common import patient_row, list_header


def _matches(store, p: Patient, q: str) -> bool:
    if not q:
        return True
    ql = q.lower()
    hay = [p.full_name, p.mrn or "", p.id]
    for c in store.list_cases(p.id):
        hay.append(c.title)
        hay.append(c.id)
        for a in c.analyses:
            hay.append(a.id)
    return any(ql in str(h).lower() for h in hay)


@st.dialog("Create patient", width="large")
def create_patient_dialog(store, *, on_created_go_case: bool = False) -> None:
    st.markdown('<div class="gf-sub" style="margin-top:-6px">Enter synthetic demonstration '
                'details only. Fields marked * are required.</div>', unsafe_allow_html=True)
    with st.form("create_patient"):
        c1, c2 = st.columns(2)
        first = c1.text_input("First name *", placeholder="Jane")
        last = c2.text_input("Last name *", placeholder="Doe")
        c3, c4, c5 = st.columns(3)
        dob = c3.date_input("Date of birth", value=None, min_value=date(1900, 1, 1),
                            max_value=date.today(), format="YYYY-MM-DD")
        sex = c4.selectbox("Sex", ["", "Female", "Male", "Other", "Undisclosed"])
        mrn = c5.text_input("Medical record no.", placeholder="MRN-00000")
        c6, c7 = st.columns(2)
        inst = c6.text_input("Institution / facility", value="Demo General Hospital")
        clin = c7.text_input("Treating clinician", placeholder="Dr. …")
        notes = st.text_area("Care-team notes", placeholder="Optional internal notes",
                             height=80)
        st.caption("Required: first name, last name. Everything else is optional.")
        submitted = st.form_submit_button("Create patient", type="primary",
                                          use_container_width=True)

    if submitted:
        if not first.strip() or not last.strip():
            st.error("First and last name are required.")
            return
        p = Patient(
            first_name=first.strip(), last_name=last.strip(),
            mrn=mrn.strip(), sex=sex or None,
            date_of_birth=dob.isoformat() if dob else None,
            institution=inst.strip(), clinician=clin.strip(), care_notes=notes.strip(),
        )
        store.create_patient(p)
        st.session_state["_created_patient_id"] = p.id
        st.session_state["_toast"] = f"Patient {p.full_name} created."
        if on_created_go_case:
            st.session_state["wizard"] = {"step": 1, "patient_id": p.id}
            nav_to("new_analysis")
        else:
            nav_to("patient", patient_id=p.id)


def render(store, user) -> None:
    C.page_header(
        "Patients",
        subtitle="Search and manage patient records. Synthetic demonstration data — "
                 "do not enter real protected health information.",
        icon_name="users",
        crumbs=[("Workspace", None), ("Patients", None)],
    )

    top_l, top_r = st.columns([5, 1.4])
    with top_l:
        q = st.text_input("search_patients", value=param("q", "") or "",
                          label_visibility="collapsed",
                          placeholder="Search by name, MRN, case title, or analysis ID…")
    with top_r:
        if st.button("New patient", type="primary", use_container_width=True,
                     icon=":material/person_add:"):
            create_patient_dialog(store)

    f1, f2, f3 = st.columns([2, 2, 2])
    status_filter = f1.selectbox(
        "Analysis status", ["Any status", "Completed", "Processing", "No-call heavy",
                            "Failed", "No analyses"])
    organisms = sorted({c.isolate.species for c in store.list_cases() if c.isolate})
    organism_filter = f2.selectbox("Organism", ["Any organism"] + organisms)
    sort_by = f3.selectbox("Sort", ["Recently updated", "Name (A–Z)", "Most cases"])

    patients = [p for p in store.list_patients() if _matches(store, p, q)]

    def _latest_status(p):
        al = store.list_analyses(patient_id=p.id)
        return al[0].status if al else None

    if status_filter != "Any status":
        want = {
            "Completed": {AnalysisStatus.COMPLETED.value},
            "Processing": {AnalysisStatus.PROCESSING.value},
            "No-call heavy": {AnalysisStatus.COMPLETED_NO_CALL.value},
            "Failed": {AnalysisStatus.FAILED.value},
        }.get(status_filter)
        if status_filter == "No analyses":
            patients = [p for p in patients if not store.list_analyses(patient_id=p.id)]
        else:
            patients = [p for p in patients if _latest_status(p) in want]
    if organism_filter != "Any organism":
        patients = [p for p in patients
                    if any(c.isolate and c.isolate.species == organism_filter
                           for c in store.list_cases(p.id))]

    if sort_by == "Name (A–Z)":
        patients.sort(key=lambda p: p.last_name.lower())
    elif sort_by == "Most cases":
        patients.sort(key=lambda p: len(store.list_cases(p.id)), reverse=True)

    st.markdown(f'<div class="gf-sub" style="margin:4px 0 6px">{len(patients)} patient(s)</div>',
                unsafe_allow_html=True)

    if not patients:
        C.empty_state(
            "No patients match your search" if q else "No patients yet",
            "Try a different search term or clear the filters." if q
            else "Create your first patient to start building a case.",
            "search" if q else "users",
        )
        return

    C.panel_open()
    list_header([("Patient", 4), ("Latest case", 3.4), ("Status", 2.4), ("", 1.1)])
    st.markdown('<hr style="margin:2px 0 0"/>', unsafe_allow_html=True)
    for p in patients[:50]:
        patient_row(store, p, key=f"pt_{p.id}")
    C.panel_close()
    if len(patients) > 50:
        st.caption(f"Showing first 50 of {len(patients)} results — refine your search to narrow.")
