"""Completed analysis report — the product centerpiece.

Renders the per-antibiotic decision-support matrix with sortable / filterable /
searchable / expandable rows, calibrated-confidence visualization, the signature
Evidence Trace, and honest separation of biological vs statistical evidence.
"""

from __future__ import annotations

import streamlit as st

from app.icons import icon
from app.services import llm_summary
from app.services.schemas import (
    EVIDENCE_META, PREDICTION_META, Prediction, TargetGate, to_dict,
)
from app.ui import components as C
from app.ui.shell import nav_to, param


def render(store, user) -> None:
    aid = param("analysis_id")
    a = store.get_analysis(aid) if aid else None
    if not a:
        C.page_header("Report not found", icon_name="file-text")
        if st.button("← Back to reports"):
            nav_to("reports")
        return
    if not a.is_complete:
        nav_to("analysis", analysis_id=a.id)
        return

    p = store.get_patient(a.patient_id)
    case = store.case_of_analysis(a.id)
    iso = case.isolate if case else None

    C.page_header(
        "Antibiotic-response report",
        subtitle=f"{p.full_name if p else '—'} · {case.title if case else '—'}",
        icon_name="file-text",
        crumbs=[("Reports", None), (a.id, None)],
    )

    # ── Header meta ───────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="gf-meta"><div><div class="k">Analysis ID</div>'
        f'<div class="v mono">{C.esc(a.id)}</div></div>'
        f'<div><div class="k">Species</div><div class="v"><em>{C.esc(a.species)}</em></div></div>'
        f'<div><div class="k">Isolate</div><div class="v mono">{C.esc(iso.lab_id if iso else "—")}</div></div>'
        f'<div><div class="k">Model</div><div class="v mono">{C.esc(a.model_version)}</div></div>'
        f'<div><div class="k">Completed</div><div class="v">{C.relative_time(a.completed_at or a.created_at)}</div></div>'
        f'</div>'
        f'<div class="gf-meta" style="margin-top:8px"><div><div class="k">Genome file</div>'
        f'<div class="v mono">{C.esc(a.genome.filename if a.genome else "—")}</div></div>'
        f'<div><div class="k">Quality</div><div class="v">'
        f'{C.qc_badge(a.genome.qc_status if a.genome else "pending", small=True)}</div></div>'
        f'<div><div class="k">Submission ID</div><div class="v mono">'
        f'{C.esc(a.genome.checksum if a.genome else "—")}</div></div></div>',
        unsafe_allow_html=True)

    st.write("")
    C.safety_banner(
        "<b>Research prototype — confirm every result with standard laboratory testing.</b> "
        "This report is decision support for a qualified professional, not a diagnosis or "
        "treatment decision. Predictions describe resistance that already exists in the "
        "submitted genome; the system never designs or modifies any organism."
    )
    st.write("")

    if a.overall_warnings:
        for wmsg in a.overall_warnings:
            st.warning(wmsg)
        st.write("")

    if a.detected_amr_features:
        with st.expander(
            f"AMRFinderPlus detected {len(a.detected_amr_features)} AMR gene/mutation feature(s)"
        ):
            genes = [f for f in a.detected_amr_features if "_" not in f]
            mutations = [f for f in a.detected_amr_features if "_" in f]
            st.markdown(C.gene_tags(genes, mutations, []), unsafe_allow_html=True)

    # ── AI plain-language summary (flag-gated, grounded on the structured report) ─
    _render_ai_summary(a)

    # ── Summary tiles ────────────────────────────────────────────────────────
    counts = a.counts()
    C.stat_row([
        C.stat_tile("Likely to fail", counts[Prediction.FAIL.value], "resistance predicted",
                    "x-circle", value_color="var(--gf-fail)"),
        C.stat_tile("Likely to work", counts[Prediction.WORK.value], "favorable (target-gated)",
                    "check-circle", value_color="var(--gf-work)"),
        C.stat_tile("No-call", counts[Prediction.NO_CALL.value], "insufficient evidence",
                    "minus-circle", value_color="var(--gf-nocall)"),
        C.stat_tile("Antibiotics", len(a.results), "in model scope", "cpu"),
    ])
    st.write("")

    # ── Matrix controls ──────────────────────────────────────────────────────
    C.panel_open("Antibiotic-response matrix", eyebrow="Decision support", icon_name="layers")
    f1, f2, f3 = st.columns([2.2, 2, 2])
    result_filter = f1.selectbox("Result", ["All results", "Likely to fail", "Likely to work",
                                            "No-call"])
    min_conf = f2.slider("Min confidence", 0, 100, 0, step=5, format="%d%%")
    search = f3.text_input("Search antibiotic", placeholder="e.g. cefoxitin")

    results = list(a.results)
    if result_filter != "All results":
        want = {"Likely to fail": Prediction.FAIL.value, "Likely to work": Prediction.WORK.value,
                "No-call": Prediction.NO_CALL.value}[result_filter]
        results = [r for r in results if r.prediction == want]
    if min_conf:
        results = [r for r in results if r.confidence * 100 >= min_conf]
    if search:
        results = [r for r in results if search.lower() in r.antibiotic.lower()]

    st.markdown('<div class="gf-sub" style="margin:2px 0 4px">Expand any antibiotic for the '
                'full evidence breakdown.</div>', unsafe_allow_html=True)

    if not results:
        st.markdown('<div class="gf-sub" style="padding:8px 0">No antibiotics match these filters.</div>',
                    unsafe_allow_html=True)
    for r in results:
        _result_row(r)
    C.panel_close()


def _render_ai_summary(a) -> None:
    """Flag-gated OpenAI summary. Renders nothing unless OPENAI_API_KEY is set."""
    if not llm_summary.is_enabled():
        return
    key = f"ai_summary::{a.id}"
    if key not in st.session_state:
        with st.spinner("Generating plain-language summary…"):
            st.session_state[key] = llm_summary.summarize(a.results, species=a.species)
    text = st.session_state.get(key)
    if not text:
        return
    C.panel_open("Plain-language summary", eyebrow="AI-generated · grounded on the report",
                 icon_name="sparkles")
    st.markdown(f'<div class="gf-sub" style="line-height:1.6">{C.esc(text)}</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="gf-sub" style="margin-top:8px;opacity:.7">Generated by OpenAI '
                'from the structured predictions above — it adds no new findings and is not '
                'an independent prediction. Verify with laboratory testing.</div>',
                unsafe_allow_html=True)
    C.panel_close()


def _result_row(r) -> None:
    pm = PREDICTION_META.get(r.prediction, PREDICTION_META["no_call"])
    tone = pm["tone"]
    color = {"work": "var(--gf-work)", "fail": "var(--gf-fail)",
             "nocall": "var(--gf-nocall)"}[tone]
    tg_map = {TargetGate.PASSED.value: C.badge("Target present", "work", "target", small=True),
              TargetGate.FAILED.value: C.badge("Target absent", "fail", "target", small=True),
              TargetGate.UNKNOWN.value: C.badge("Target unknown", "neutral", "target", small=True)}
    ev = EVIDENCE_META.get(r.evidence_category, EVIDENCE_META["no_known_resistance_signal"])

    with st.container():
        head_l, head_c, head_r = st.columns([3, 2.2, 2.2])
        with head_l:
            st.markdown(
                f'<div style="display:flex;gap:12px;align-items:center">'
                f'<div style="width:3px;align-self:stretch;min-height:38px;border-radius:3px;background:{color}"></div>'
                f'<div><div class="gf-result-name">{C.esc(r.antibiotic)}</div>'
                f'<div class="gf-result-class">{C.esc(r.drug_class or "—")}</div></div></div>',
                unsafe_allow_html=True)
        with head_c:
            st.markdown(C.prediction_badge(r.prediction) + "<br>"
                        + f'<span class="gf-b-sm gf-badge gf-b-{"brand" if ev["roman"]!="—" else "neutral"}" '
                          f'style="margin-top:5px">{icon(ev["icon"],12)}Evidence {ev["roman"]}</span>',
                        unsafe_allow_html=True)
        with head_r:
            pct = round(r.confidence * 100)
            prob_r = round(r.resistance_probability * 100)
            st.markdown(
                f'<div style="text-align:right"><span class="gf-conf-num gf-tnum" '
                f'style="color:{color};font-size:1.25rem">{pct}%</span>'
                f'<div class="gf-conf-cap">class confidence · P(R) {prob_r}%</div></div>',
                unsafe_allow_html=True)

        with st.expander("Evidence & explanation"):
            # Evidence Trace (signature component)
            st.markdown('<div class="gf-eyebrow" style="margin-bottom:7px">Evidence trace</div>',
                        unsafe_allow_html=True)
            st.markdown(
                C.evidence_trace(
                    features_found=len(r.supporting_genes) + len(r.supporting_mutations),
                    target_gate=r.target_gate, prediction=r.prediction,
                    confidence=r.confidence, tone=tone),
                unsafe_allow_html=True)
            st.write("")

            cc1, cc2 = st.columns([1.2, 1])
            with cc1:
                # Evidence category box (honest separation)
                box_cls = {"i": "gf-evd-i", "ii": "gf-evd-ii", "iii": "gf-evd-iii",
                           "—": "gf-evd-conflicting"}[ev["roman"]]
                st.markdown(
                    f'<div class="gf-evd-box {box_cls}"><span class="ico">{icon(ev["icon"],17)}</span>'
                    f'<div><b>{C.esc(ev["title"])}</b>{C.esc(ev["detail"])}</div></div>',
                    unsafe_allow_html=True)
                st.write("")
                st.markdown(
                    f'<div class="gf-kv"><span class="k">Explanation</span>'
                    f'<span class="v">{C.esc(r.explanation or "—")}</span></div>'
                    f'<div class="gf-kv"><span class="k">Detected genes / mutations</span>'
                    f'<span class="v">{C.gene_tags(r.supporting_genes, r.supporting_mutations, [])}</span></div>'
                    f'<div class="gf-kv"><span class="k">Statistical associations</span>'
                    f'<span class="v">{C.gene_tags([], [], r.statistical_features)}</span></div>'
                    f'<div class="gf-kv"><span class="k">Molecular-target gate</span>'
                    f'<span class="v">{tg_map.get(r.target_gate, "—")}</span></div>',
                    unsafe_allow_html=True)
            with cc2:
                st.markdown('<div class="gf-eyebrow" style="margin-bottom:7px">Confidence</div>',
                            unsafe_allow_html=True)
                st.markdown(
                    C.confidence_meter(r.confidence, r.confidence_band, tone,
                                       r.crossed_threshold, r.no_call_threshold_hit),
                    unsafe_allow_html=True)
                st.write("")
                st.markdown('<div class="gf-eyebrow" style="margin-bottom:5px">Limitations</div>',
                            unsafe_allow_html=True)
                lim = "".join(f'<li>{C.esc(x)}</li>' for x in r.limitations) or "<li>—</li>"
                st.markdown(f'<ul class="gf-sub" style="margin:0;padding-left:16px">{lim}</ul>',
                            unsafe_allow_html=True)
            st.markdown(
                '<div class="gf-sub" style="margin-top:8px">Confirm this result through '
                'standard laboratory susceptibility testing before any clinical action.</div>',
                unsafe_allow_html=True)


def _export_text(store, a) -> str:
    p = store.get_patient(a.patient_id)
    case = store.case_of_analysis(a.id)
    iso = case.isolate if case else None
    L = []
    L.append("BIOSHIELD AI — ANTIBIOTIC-RESPONSE REPORT")
    L.append("=" * 60)
    L.append("RESEARCH PROTOTYPE — confirm every result with standard laboratory")
    L.append("testing. Decision support only; a trained professional decides.")
    L.append("Synthetic demonstration data.")
    L.append("")
    L.append(f"Patient:      {p.full_name if p else '—'}   MRN: {p.mrn if p else '—'}")
    L.append(f"Case:         {case.title if case else '—'}")
    L.append(f"Isolate:      {iso.lab_id if iso else '—'}   Species: {a.species}")
    L.append(f"Analysis ID:  {a.id}")
    L.append(f"Model:        {a.model_version}")
    L.append(f"Genome file:  {a.genome.filename if a.genome else '—'}  "
             f"(submission {a.genome.checksum if a.genome else '—'})")
    L.append(f"Completed:    {a.completed_at or a.created_at}")
    L.append("")
    L.append("-" * 60)
    for r in a.results:
        pm = PREDICTION_META.get(r.prediction, PREDICTION_META["no_call"])
        ev = EVIDENCE_META.get(r.evidence_category, {})
        L.append(f"{r.antibiotic}  ({r.drug_class})")
        L.append(f"  Prediction:  {pm['label']}   Confidence: {round(r.confidence*100)}% "
                 f"(band {round(r.confidence_band[0]*100)}-{round(r.confidence_band[1]*100)}%)")
        L.append(f"  Evidence:    ({ev.get('roman','—')}) {ev.get('title','')}")
        L.append(f"  Target gate: {r.target_gate}")
        if r.supporting_genes or r.supporting_mutations:
            L.append(f"  Markers:     {', '.join(r.supporting_genes + r.supporting_mutations)}")
        if r.statistical_features:
            L.append(f"  Statistical: {', '.join(r.statistical_features)} (NOT proven causal)")
        L.append(f"  Note:        {r.explanation}")
        for lim in r.limitations:
            L.append(f"    - {lim}")
        L.append("")
    L.append("-" * 60)
    L.append("MANDATORY: Confirm all results with standard laboratory susceptibility")
    L.append("testing. This is not a cleared or approved diagnostic device.")
    return "\n".join(L)


def _export_json(a) -> str:
    import json
    payload = {
        "analysisId": a.id, "patientId": a.patient_id, "caseId": a.case_id,
        "isolateId": a.isolate_id, "status": a.status, "species": a.species,
        "modelVersion": a.model_version, "createdAt": a.created_at,
        "completedAt": a.completed_at,
        "qualityChecks": {"status": a.genome.qc_status if a.genome else "pending",
                          "warnings": a.genome.qc_warnings if a.genome else []},
        "results": [to_dict(r) for r in a.results],
        "overallWarnings": a.overall_warnings,
        "requiresLabConfirmation": a.requires_lab_confirmation,
        "_notice": "Research prototype — synthetic demonstration data. Confirm with lab testing.",
    }
    return json.dumps(payload, indent=2)
