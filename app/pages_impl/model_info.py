"""Model Information — coverage, calibration, and honest scope/limitations."""

from __future__ import annotations

import streamlit as st

from app.icons import icon
from app.services.analysis_service import _DRUGS, get_provider
from app.ui import components as C


def render(store, user) -> None:
    C.page_header(
        "Model information",
        subtitle="What BioShield AI covers, how confidence is calibrated, and where "
                 "its limits are. Coverage is shown before every submission.",
        icon_name="cpu",
        crumbs=[("System", None), ("Model information", None)],
    )

    prov = get_provider()
    C.stat_row([
        C.stat_tile("Model version", "v1", "XGBoost · genotype-only", "cpu"),
        C.stat_tile("Species", "1", "S. aureus (incl. MRSA)", "microscope"),
        C.stat_tile("Antibiotics", len(_DRUGS), "in current scope", "layers"),
        C.stat_tile("Provider", prov.name, "analysis backend", "database"),
    ])
    st.write("")

    left, right = st.columns([1.3, 1])
    with left:
        C.panel_open("Supported antibiotics", eyebrow="Coverage", icon_name="layers")
        rows = "".join(
            f'<div class="gf-row2" style="grid-template-columns:2fr 2fr 3fr;border-bottom:1px solid var(--gf-border)">'
            f'<div class="gf-name" style="font-size:.86rem">{C.esc(d.get("standardized_name") or d.get("antibiotic","").capitalize())}</div>'
            f'<div class="gf-sub">{C.esc(d.get("drug_class",""))}</div>'
            f'<div class="gf-sub"><span class="gf-mono" style="font-size:.74rem">'
            f'{C.esc((d.get("target_genes","") or "—").replace(";"," · "))}</span></div></div>'
            for d in _DRUGS)
        st.markdown(
            '<div class="gf-listhead" style="grid-template-columns:2fr 2fr 3fr;border-bottom:1px solid var(--gf-border)">'
            '<div>Antibiotic</div><div>Class</div><div>Molecular target(s)</div></div>' + rows,
            unsafe_allow_html=True)
        st.markdown('<div class="gf-sub" style="margin-top:8px">Antibiotics outside this set '
                    'return no-call by construction — the model will not guess beyond its scope.</div>',
                    unsafe_allow_html=True)
        C.panel_close()

    with right:
        C.panel_open("Status", eyebrow="System", icon_name="activity")
        st.markdown(
            C.badge("Operational", "work", "check-circle") + " "
            + C.badge(f"{prov.name.capitalize()} provider", "brand", "database"),
            unsafe_allow_html=True)
        st.markdown(
            f'<div class="gf-meta" style="margin-top:10px">'
            f'<div><div class="k">Last model update</div><div class="v">2026-07-19</div></div>'
            f'<div><div class="k">Species scope</div><div class="v"><em>S. aureus</em></div></div>'
            f'</div>', unsafe_allow_html=True)
        C.panel_close()
        st.write("")
        C.panel_open("Training-data summary", eyebrow="Provenance", icon_name="database")
        st.markdown(
            '<div class="gf-sub">Genomes are sourced from BV-BRC / NCBI. The final '
            'per-antibiotic XGBoost models use AMRFinderPlus genotype features and are '
            'refit on every labeled genome. Hyperparameters and sigmoid calibration use '
            'Mash-clustered out-of-fold predictions with inverse duplicate-family weights. '
            'The earlier Mash-separated test report is retained as historical evidence; '
            'fresh external validation is still required.</div>',
            unsafe_allow_html=True)
        C.panel_close()

    st.write("")
    g1, g2 = st.columns(2)
    with g1:
        _concept("Confidence calibration", "gauge",
                 "The production refit uses sigmoid calibration learned from grouped "
                 "out-of-fold predictions across the full labeled dataset. Reported "
                 "confidence is model confidence — not a guarantee of clinical effectiveness.")
        _concept("What no-call means", "minus-circle",
                 "When evidence is weak, conflicting, or out-of-distribution, the model "
                 "returns no-call instead of forcing a verdict. No-call is a valid, honest "
                 "outcome — not a processing error. No-call rate and accuracy-on-called are "
                 "reported separately.")
    with g2:
        _concept("Evidence categories", "flask",
                 "(i) Known resistance marker — a catalog-confirmed gene or mutation "
                 "(biological). (ii) Statistical association only — a model coefficient / "
                 "feature-importance signal, explicitly NOT proven causal. (iii) No known "
                 "signal — absence of markers.")
        _concept("Molecular-target gating", "target",
                 "A favorable ('likely to work') call is never made from absence of "
                 "resistance markers alone. The drug's molecular target must be confirmed "
                 "present; otherwise the result is no-call.")

    st.write("")
    C.panel_open("Known limitations", eyebrow="Honest scope", icon_name="alert-triangle")
    for text in [
        "Species scope is S. aureus only; no claims are made for other pathogens.",
        "Catalog-based detection cannot see novel resistance mechanisms absent from the "
        "reference set — a limitation inherent to any catalog approach.",
        "Requires an assembled, quality-checked contig FASTA; it does not process raw reads "
        "and never reads DNA from a patient sample.",
        "Performance is expected to drop on genetic groups unseen during training; this is "
        "reported, not hidden.",
        "This is a research prototype, not a cleared or approved clinical diagnostic device.",
    ]:
        st.markdown(f'<div style="display:flex;gap:9px;padding:5px 0"><span style="color:var(--gf-nocall);flex:none">'
                    f'{icon("chevron-right",15)}</span><span class="gf-sub">{C.esc(text)}</span></div>',
                    unsafe_allow_html=True)
    C.panel_close()


def _concept(title: str, ic: str, body: str) -> None:
    st.markdown(
        f'<div class="gf-panel" style="margin-bottom:14px"><div class="gf-eyebrow" '
        f'style="margin-bottom:6px">{icon(ic,14)}{C.esc(title)}</div>'
        f'<div class="gf-sub">{C.esc(body)}</div></div>',
        unsafe_allow_html=True)
