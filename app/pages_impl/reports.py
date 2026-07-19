"""Reports — searchable library of completed analysis reports."""

from __future__ import annotations

import streamlit as st

from app.services.schemas import AnalysisStatus, Prediction
from app.ui import components as C
from app.pages_impl.common import analysis_row, list_header


def render(store, user) -> None:
    C.page_header(
        "Reports",
        subtitle="Every completed antibiotic-response report. Search, filter, open, "
                 "export, or print.",
        icon_name="file-text",
        crumbs=[("Analysis", None), ("Reports", None)],
    )

    all_reports = [a for a in store.list_analyses() if a.is_complete]

    f1, f2, f3, f4 = st.columns([2.4, 2, 2, 2])
    q = f1.text_input("Search", placeholder="Patient, analysis ID, genome…",
                      label_visibility="collapsed")
    species_opts = sorted({a.species for a in all_reports})
    species = f2.selectbox("Species", ["Any species"] + species_opts)
    result_kind = f3.selectbox("Outcome", ["Any outcome", "Has resistance (fail)",
                                          "Favorable only", "No-call heavy"])
    models = sorted({a.model_version for a in all_reports})
    model = f4.selectbox("Model version", ["Any version"] + models)

    reports = all_reports
    if q:
        ql = q.lower()
        def match(a):
            p = store.get_patient(a.patient_id)
            hay = [a.id, p.full_name if p else "", a.genome.filename if a.genome else ""]
            return any(ql in str(h).lower() for h in hay)
        reports = [a for a in reports if match(a)]
    if species != "Any species":
        reports = [a for a in reports if a.species == species]
    if model != "Any version":
        reports = [a for a in reports if a.model_version == model]
    if result_kind == "Has resistance (fail)":
        reports = [a for a in reports if a.counts()[Prediction.FAIL.value] > 0]
    elif result_kind == "Favorable only":
        reports = [a for a in reports
                   if a.counts()[Prediction.FAIL.value] == 0
                   and a.counts()[Prediction.WORK.value] > 0]
    elif result_kind == "No-call heavy":
        reports = [a for a in reports if a.status == AnalysisStatus.COMPLETED_NO_CALL.value]

    st.markdown(f'<div class="gf-sub" style="margin:2px 0 6px">{len(reports)} report(s)</div>',
                unsafe_allow_html=True)
    if not reports:
        C.empty_state("No reports match", "Adjust the filters or run a new analysis.",
                      "file-text")
        return

    C.panel_open()
    list_header([("Report", 3.4), ("Outcome", 3), ("Status", 2.2), ("", 1.2)])
    st.markdown('<hr style="margin:2px 0 0"/>', unsafe_allow_html=True)
    for a in reports:
        analysis_row(store, a, key=f"rep_{a.id}")
    C.panel_close()
