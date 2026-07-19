"""Cases — cross-patient case directory and a single-case workspace."""

from __future__ import annotations

import streamlit as st

from app.icons import icon
from app.ui import components as C
from app.ui.shell import nav_to, param
from app.pages_impl.common import case_row, analysis_row, list_header, priority_badge


def render_list(store, user) -> None:
    C.page_header(
        "Cases",
        subtitle="Infection and bacterial-isolate cases across all patients.",
        icon_name="folder",
        crumbs=[("Workspace", None), ("Cases", None)],
    )
    q = st.text_input("search_cases", label_visibility="collapsed",
                      placeholder="Search cases by title, patient, organism, or site…")
    cases = store.list_cases()
    if q:
        ql = q.lower()
        def match(c):
            p = store.get_patient(c.patient_id)
            hay = [c.title, c.infection_site, c.syndrome, p.full_name if p else "",
                   c.isolate.species if c.isolate else ""]
            return any(ql in str(h).lower() for h in hay)
        cases = [c for c in cases if match(c)]

    st.markdown(f'<div class="gf-sub" style="margin:2px 0 6px">{len(cases)} case(s)</div>',
                unsafe_allow_html=True)
    if not cases:
        C.empty_state("No cases", "Create a case from a patient workspace.", "folder")
        return
    C.panel_open()
    list_header([("Case", 4), ("Organism / site", 3), ("Status", 2.2), ("", 1.1)])
    st.markdown('<hr style="margin:2px 0 0"/>', unsafe_allow_html=True)
    for c in cases:
        case_row(store, c, key=f"cs_{c.id}")
    C.panel_close()


def render_detail(store, user) -> None:
    cid = param("case_id")
    c = store.get_case(cid) if cid else None
    if not c:
        C.page_header("Case not found", icon_name="folder")
        if st.button("← Back to cases"):
            nav_to("cases")
        return
    p = store.get_patient(c.patient_id)

    C.page_header(
        c.title,
        icon_name="folder",
        crumbs=[("Cases", None), (p.full_name if p else "—", None), (c.title, None)],
    )
    hl, hr = st.columns([4, 1.4])
    with hl:
        st.markdown(priority_badge(c.priority) + " "
                    + C.badge(f"{len(c.analyses)} analysis(es)", "neutral", "cpu", small=True),
                    unsafe_allow_html=True)
    with hr:
        st.write("")
        if st.button("Run new analysis", type="primary", use_container_width=True,
                     icon=":material/add:"):
            st.session_state["wizard"] = {"step": 2, "patient_id": c.patient_id}
            nav_to("new_analysis")

    st.write("")
    left, right = st.columns([1, 1])
    with left:
        C.panel_open("Clinical context", eyebrow="Case", icon_name="clipboard-list")
        _kv([
            ("Patient", p.full_name if p else "—"),
            ("Encounter", c.encounter_date or "—"),
            ("Infection site", c.infection_site or "—"),
            ("Syndrome", c.syndrome or "—"),
            ("Antibiotic exposure", c.antibiotic_exposure or "—"),
            ("Clinician", c.clinician or "—"),
        ])
        if c.notes:
            st.markdown(f'<div class="gf-sub" style="margin-top:8px">{C.esc(c.notes)}</div>',
                        unsafe_allow_html=True)
        C.panel_close()
    with right:
        C.panel_open("Isolate", eyebrow="Specimen", icon_name="microscope")
        if c.isolate:
            iso = c.isolate
            _kv([
                ("Species", iso.species),
                ("Gram stain", iso.gram_stain),
                ("Specimen", iso.specimen_type or "—"),
                ("Lab ID", iso.lab_id or "—"),
                ("Assembly", iso.assembly_id or "—"),
                ("Platform", iso.sequencing_platform or "—"),
                ("Assembly QC", iso.assembly_quality or "—"),
            ])
        else:
            st.markdown('<div class="gf-sub">No isolate recorded.</div>', unsafe_allow_html=True)
        C.panel_close()

    st.write("")
    C.panel_open("Analyses & history", eyebrow="Longitudinal", icon_name="history")
    if c.analyses:
        list_header([("Analysis", 3.4), ("Outcome", 3), ("Status", 2.2), ("", 1.2)])
        st.markdown('<hr style="margin:2px 0 0"/>', unsafe_allow_html=True)
        for a in sorted(c.analyses, key=lambda x: x.created_at, reverse=True):
            analysis_row(store, a, key=f"cd_{a.id}")
        # Comparison note when multiple analyses exist
        if len(c.analyses) > 1:
            st.markdown(
                '<div class="gf-sub" style="margin-top:10px">This case has multiple analyses. '
                'A new upload or model version always creates a <b>new</b> analysis record — '
                'prior reports are never overwritten, preserving the full history.</div>',
                unsafe_allow_html=True)
    else:
        C.empty_state("No analyses", "Run an analysis to generate the first report.", "cpu")
    C.panel_close()


def _kv(rows: list[tuple[str, str]]) -> None:
    inner = "".join(
        f'<div class="gf-kv"><span class="k">{C.esc(k)}</span>'
        f'<span class="v">{C.esc(v)}</span></div>' for k, v in rows)
    st.markdown(inner, unsafe_allow_html=True)
