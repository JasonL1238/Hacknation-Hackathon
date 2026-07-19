"""Overview — clinical operations dashboard."""

from __future__ import annotations

import streamlit as st

from app.icons import icon
from app.services.analysis_service import get_provider
from app.services.schemas import AnalysisStatus, Prediction
from app.ui import components as C
from app.ui.shell import nav_to
from app.pages_impl.common import analysis_row, case_row


def render(store, user) -> None:
    C.page_header(
        "Overview",
        subtitle="Operational snapshot of your clinical research workspace. "
                 "All records shown are synthetic demonstration data.",
        icon_name="layout-grid",
    )

    # Advance any live processing analyses so the dashboard reflects real state.
    prov = get_provider()
    for a in store.list_analyses():
        if a.status == AnalysisStatus.PROCESSING.value:
            prov.get_analysis_status(a)

    analyses = store.list_analyses()
    processing = [a for a in analyses if a.status == AnalysisStatus.PROCESSING.value]
    completed = [a for a in analyses if a.is_complete]
    no_call_heavy = [a for a in analyses if a.status == AnalysisStatus.COMPLETED_NO_CALL.value]
    failed = [a for a in analyses if a.status == AnalysisStatus.FAILED.value]

    C.stat_row([
        C.stat_tile("Patients", len(store.list_patients()),
                    "in this workspace", "users"),
        C.stat_tile("Processing", len(processing),
                    "analyses running now", "loader",
                    value_color="var(--gf-brand)" if processing else None),
        C.stat_tile("No-call heavy", len(no_call_heavy),
                    "need lab prioritization", "minus-circle",
                    value_color="var(--gf-nocall)" if no_call_heavy else None),
        C.stat_tile("Attention", len(failed),
                    "failed uploads / errors", "alert-triangle",
                    value_color="var(--gf-fail)" if failed else None),
    ])
    st.write("")
    C.safety_banner()
    st.write("")

    left, right = st.columns([1.55, 1])

    # ── Left column: processing queue + recent cases ─────────────────────────
    with left:
        C.panel_open("Currently processing", eyebrow="Live", icon_name="loader")
        if processing:
            for a in processing:
                analysis_row(store, a, key=f"ov_proc_{a.id}")
        else:
            st.markdown('<div class="gf-sub" style="padding:6px 0">No analyses in progress. '
                        'Start one from <b>New Analysis</b>.</div>', unsafe_allow_html=True)
        C.panel_close()
        st.write("")

        C.panel_open("Recent cases", eyebrow="Workspace", icon_name="folder")
        cases = store.list_cases()[:5]
        if cases:
            for c in cases:
                case_row(store, c, key=f"ov_case_{c.id}")
        else:
            C.empty_state("No cases yet", "Create a patient and open a case to begin.",
                          "folder")
        st.write("")
        if st.button("View all cases", key="ov_all_cases", icon=":material/arrow_forward:"):
            nav_to("cases")
        C.panel_close()

    # ── Right column: alerts + activity + coverage ───────────────────────────
    with right:
        C.panel_open("Requires review", eyebrow="Alerts", icon_name="alert-triangle")
        alerts = []
        for a in no_call_heavy:
            p = store.get_patient(a.patient_id)
            alerts.append(("nocall", "No-call–heavy report",
                           f"{p.full_name if p else a.id} — prioritize lab testing.",
                           "report", a.id))
        for a in failed:
            p = store.get_patient(a.patient_id)
            reason = ("Genome validation failed" if a.genome and a.genome.qc_status == "failed"
                      else "Processing error — retry available")
            alerts.append(("fail", reason,
                           f"{p.full_name if p else a.id}",
                           "analysis", a.id))
        if alerts:
            for i, (tone, title, body, route, aid) in enumerate(alerts[:5]):
                ic = "minus-circle" if tone == "nocall" else "alert-triangle"
                st.markdown(
                    f'<div style="display:flex;gap:10px;padding:9px 0;border-bottom:1px solid var(--gf-border)">'
                    f'<span style="color:var(--gf-{tone});flex:none;margin-top:1px">{icon(ic,16)}</span>'
                    f'<div><div class="gf-name" style="font-size:.85rem">{C.esc(title)}</div>'
                    f'<div class="gf-sub">{C.esc(body)}</div></div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Open", key=f"ov_alert_{i}"):
                    nav_to(route, analysis_id=aid)
        else:
            st.markdown('<div class="gf-sub" style="padding:6px 0">Nothing needs attention.</div>',
                        unsafe_allow_html=True)
        C.panel_close()
        st.write("")

        C.panel_open("Model coverage", eyebrow="System", icon_name="cpu")
        prov = get_provider()
        from app.services.analysis_service import _DRUGS
        st.markdown(
            f'<div class="gf-meta"><div><div class="k">Species</div>'
            f'<div class="v"><em>S. aureus</em></div></div>'
            f'<div><div class="k">Antibiotics</div><div class="v gf-tnum">{len(_DRUGS)}</div></div>'
            f'<div><div class="k">Provider</div><div class="v">{prov.name}</div></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="gf-sub" style="margin-top:8px">Model '
                    '<span class="gf-mono">bioshield-xgboost-v1</span>. '
                    'Coverage is shown before every submission.</div>', unsafe_allow_html=True)
        if st.button("Model information", key="ov_model", icon=":material/arrow_forward:"):
            nav_to("model")
        C.panel_close()
        st.write("")

        C.panel_open("Recent activity", eyebrow="Audit", icon_name="history")
        events = []
        for e in store.activity[:6]:
            events.append({"message": e["message"], "at": C.relative_time(e["at"]),
                           "icon": "activity"})
        if events:
            st.markdown(C.timeline(events), unsafe_allow_html=True)
        else:
            st.markdown('<div class="gf-sub">No activity yet.</div>', unsafe_allow_html=True)
        C.panel_close()
