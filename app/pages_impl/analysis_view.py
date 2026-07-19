"""Analysis view — asynchronous processing experience (and dispatch to report).

Uses a fragment that re-runs on an interval to poll processing status, so the
user sees pipeline stages advance in real time and can safely navigate away.
Progress is stage-based (no fabricated percentages).
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.icons import icon
from app.services.analysis_service import get_provider
from app.services.schemas import AnalysisStatus, PIPELINE_STAGES
from app.ui import components as C
from app.ui.shell import nav_to, param


def render(store, user) -> None:
    aid = param("analysis_id")
    a = store.get_analysis(aid) if aid else None
    if not a:
        C.page_header("Analysis not found", icon_name="cpu")
        if st.button("← Back to queue"):
            nav_to("queue")
        return

    # Completed analyses belong on the report page.
    if a.is_complete:
        nav_to("report", analysis_id=a.id)
        return

    p = store.get_patient(a.patient_id)
    case = store.case_of_analysis(a.id)
    C.page_header(
        "Analysis in progress" if a.status == AnalysisStatus.PROCESSING.value else "Analysis",
        subtitle=f"{p.full_name if p else '—'} · {case.title if case else '—'}",
        icon_name="cpu",
        crumbs=[("Analysis Queue", None), (a.id, None)],
    )

    # Identity meta
    st.markdown(
        f'<div class="gf-meta"><div><div class="k">Analysis ID</div>'
        f'<div class="v mono">{C.esc(a.id)}</div></div>'
        f'<div><div class="k">Genome</div><div class="v mono">'
        f'{C.esc(a.genome.filename if a.genome else "—")}</div></div>'
        f'<div><div class="k">Model</div><div class="v mono">{C.esc(a.model_version)}</div></div>'
        f'<div><div class="k">Status</div><div class="v">{C.status_badge(a.status)}</div></div>'
        f'</div>', unsafe_allow_html=True)
    st.write("")

    if a.status == AnalysisStatus.FAILED.value:
        _render_failed(store, a)
        return
    if a.status == AnalysisStatus.CANCELLED.value:
        _render_cancelled(store, a)
        return

    _render_processing(store, a)


@st.fragment(run_every=1.5)
def _render_processing(store, a) -> None:
    prov = get_provider()
    prov.get_analysis_status(a)  # advance based on wall-clock

    if a.is_terminal:
        # Re-render the whole page (leaves the fragment) to route appropriately.
        st.rerun()
        return

    elapsed = _elapsed(a)
    n = len(PIPELINE_STAGES)
    stage = min(a.current_stage, n - 1)

    left, right = st.columns([1.5, 1])
    with left:
        C.panel_open("Pipeline", eyebrow="Processing", icon_name="loader")
        st.markdown(C.pipeline_stepper(stage), unsafe_allow_html=True)
        C.panel_close()
    with right:
        C.panel_open("Job status", eyebrow="Live", icon_name="activity")
        pct = round((stage) / n * 100)
        st.progress(min(pct, 99) / 100.0,
                    text=f"Stage {stage + 1} of {n} · {PIPELINE_STAGES[stage][0]}")
        st.markdown(
            f'<div class="gf-meta" style="margin-top:10px"><div><div class="k">Elapsed</div>'
            f'<div class="v gf-tnum">{elapsed:.0f}s</div></div>'
            f'<div><div class="k">Started</div><div class="v">{C.relative_time(a.started_at or a.created_at)}</div></div>'
            f'</div>', unsafe_allow_html=True)
        st.markdown('<div class="gf-sub" style="margin-top:10px">Processing runs in the '
                    'background. You can leave this page — the analysis stays tied to the '
                    'patient and case, and you\'ll find it in the queue.</div>',
                    unsafe_allow_html=True)
        st.write("")
        if st.button("Cancel analysis", icon=":material/close:", key="cancel_an"):
            prov.cancel_analysis(a)
            store.log(f"Analysis {a.id} cancelled", a.patient_id, a.case_id, a.id)
            st.rerun()
        C.panel_close()


def _render_failed(store, a) -> None:
    st.markdown(
        f'<div class="gf-safety" style="background:var(--gf-fail-soft);'
        f'border-color:var(--gf-fail-border);border-left-color:var(--gf-fail);color:#6d1a1a">'
        f'<span class="ico" style="color:var(--gf-fail)">{icon("alert-triangle", 18)}</span>'
        f'<div><b>Analysis failed.</b> {C.esc(a.error_message or "An error occurred during processing.")}</div>'
        f'</div>', unsafe_allow_html=True)
    st.write("")

    failed_at = a.current_stage if a.current_stage else None
    genome_failed = a.genome and a.genome.qc_status == "failed"
    C.panel_open("Pipeline", eyebrow="Failed run", icon_name="cpu")
    st.markdown(C.pipeline_stepper(a.current_stage, failed_at=failed_at if not genome_failed else 1),
                unsafe_allow_html=True)
    C.panel_close()
    st.write("")

    if genome_failed:
        C.panel_open("Quality checks", eyebrow="Validation", icon_name="flask")
        for wmsg in a.genome.qc_warnings:
            st.error(wmsg)
        st.markdown('<div class="gf-sub">Re-run this case from the patient workspace with a '
                    'corrected FASTA assembly.</div>', unsafe_allow_html=True)
        C.panel_close()
    else:
        c1, c2, _ = st.columns([1.3, 1.3, 3])
        with c1:
            if st.button("Retry analysis", type="primary", icon=":material/refresh:",
                         use_container_width=True):
                get_provider().retry_analysis(a)
                store.log(f"Analysis {a.id} retried", a.patient_id, a.case_id, a.id)
                st.rerun()
        with c2:
            if st.button("Back to patient", icon=":material/arrow_back:",
                         use_container_width=True):
                nav_to("patient", patient_id=a.patient_id)


def _render_cancelled(store, a) -> None:
    st.info("This analysis was cancelled. You can start a new analysis for this case at any time.")
    if st.button("Retry analysis", type="primary", icon=":material/refresh:"):
        get_provider().retry_analysis(a)
        st.rerun()


def _elapsed(a) -> float:
    if not a.started_at:
        return 0.0
    try:
        started = datetime.fromisoformat(a.started_at.replace("Z", ""))
    except ValueError:
        return 0.0
    return max(0.0, (datetime.utcnow() - started).total_seconds())
