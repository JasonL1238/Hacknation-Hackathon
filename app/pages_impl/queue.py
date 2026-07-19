"""Analysis Queue — all analyses with status filters and live processing."""

from __future__ import annotations

import streamlit as st

from app.services.analysis_service import get_provider
from app.services.schemas import AnalysisStatus
from app.ui import components as C
from app.ui.shell import nav_to
from app.pages_impl.common import analysis_row, list_header

_FILTERS = [
    ("All", None),
    ("Processing", {AnalysisStatus.PROCESSING.value}),
    ("Completed", {AnalysisStatus.COMPLETED.value, AnalysisStatus.COMPLETED_NO_CALL.value}),
    ("No-call heavy", {AnalysisStatus.COMPLETED_NO_CALL.value}),
    ("Failed", {AnalysisStatus.FAILED.value}),
    ("Cancelled", {AnalysisStatus.CANCELLED.value}),
]


def render(store, user) -> None:
    C.page_header(
        "Analysis queue",
        subtitle="Every submission across the workspace. Processing jobs update live.",
        icon_name="list-checks",
        crumbs=[("Analysis", None), ("Queue", None)],
    )
    _live_queue(store)


@st.fragment(run_every=2.0)
def _live_queue(store) -> None:
    prov = get_provider()
    analyses = store.list_analyses()
    for a in analyses:
        if a.status == AnalysisStatus.PROCESSING.value:
            prov.get_analysis_status(a)

    counts = {label: 0 for label, _ in _FILTERS}
    for a in analyses:
        for label, statuses in _FILTERS:
            if statuses is None or a.status in statuses:
                counts[label] += 1

    labels = [f"{label} ({counts[label]})" for label, _ in _FILTERS]
    choice = st.radio("queue_filter", labels, horizontal=True,
                      label_visibility="collapsed")
    idx = labels.index(choice)
    _, statuses = _FILTERS[idx]

    rows = [a for a in analyses if statuses is None or a.status in statuses]
    if not rows:
        C.empty_state("Nothing here", "No analyses match this filter.", "list-checks")
        return

    C.panel_open()
    list_header([("Analysis", 3.4), ("Outcome", 3), ("Status", 2.2), ("", 1.2)])
    st.markdown('<hr style="margin:2px 0 0"/>', unsafe_allow_html=True)
    for a in rows:
        analysis_row(store, a, key=f"q_{a.id}")
    C.panel_close()
