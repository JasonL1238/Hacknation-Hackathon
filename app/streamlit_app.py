"""
BioShield AI — Streamlit Demo (Module 03)
S. aureus AMR prediction: fail / work / no-call with calibrated confidence.

Consumes:
  - DATA_SPEC §6  report objects  (from src/genome_firewall/report.py)
  - DATA_SPEC §7  metrics.json    (from src/genome_firewall/evaluate.py)
  - reliability / PR-curve PNGs  (from reports/)

IMPORTANT: Research prototype — every result must be confirmed by standard laboratory
testing. Decision support only; a trained professional makes the decision.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

# ─── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
APP = ROOT / "app"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROCESSED = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"
DRUGS_DB = ROOT / "db" / "drugs_saureus.csv"

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="BioShield AI — S. aureus AMR",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─── Design system (professional / clinical theme) ───────────────────────────
def _inject_css() -> None:
    """Inject the BioShield AI design system.

    Palette follows the data-viz status convention: verdict colors are the
    reserved status ramp (critical / good / neutral), always paired with an
    icon + label — never color alone. Brand accent is blue, kept distinct from
    the green 'work' verdict.
    """
    st.markdown(
        """<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@300;400;500;600;700&display=swap');
:root {
  --gf-ink: #0f172a;
  --gf-ink-2: #475569;
  --gf-muted: #64748b;
  --gf-plane: #f8fafc;
  --gf-surface: #ffffff;
  --gf-border: #e6ebf2;
  --gf-border-strong: #d3dbe6;
  --gf-brand: #1e40af;
  --gf-brand-2: #3b82f6;
  --gf-brand-soft: #eaf1fe;
  --gf-brand-border: #dbeafe;
  --gf-accent: #d97706;  --gf-accent-soft: #fdf1e3;
  --gf-fail: #dc2626;    --gf-fail-soft: #fdecec;
  --gf-work: #16a34a;    --gf-work-soft: #e8f6ee;
  --gf-nocall: #64748b;  --gf-nocall-soft: #eef2f7;
  --gf-warn: #d97706;
  --gf-mono: 'Fira Code', ui-monospace, SFMono-Regular, Menlo, monospace;
  --gf-grad: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
  --gf-grad-text: linear-gradient(120deg, #1e3a8a 0%, #2563eb 55%, #0ea5a4 100%);
  --gf-glow: 0 8px 22px rgba(37,99,235,.30);
  --gf-shadow: 0 1px 2px rgba(15,23,42,.04), 0 6px 20px rgba(15,23,42,.06);
  --gf-shadow-hover: 0 4px 8px rgba(15,23,42,.06), 0 16px 38px rgba(15,23,42,.13);
}

/* Page plane + typography */
html { font-size: 17px; }
.stApp {
  background:
    radial-gradient(1100px 460px at 50% -260px, rgba(59,130,246,.14), transparent 62%),
    var(--gf-plane);
}
html, body, [class*="css"] {
  font-family: 'Fira Sans', system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
}
[data-testid="stAppViewContainer"] .block-container {
  max-width: 1100px; padding-top: 2.6rem; padding-bottom: 4rem;
}
h1, h2, h3 { color: var(--gf-ink); letter-spacing: -0.02em; font-weight: 800; }
h1 { font-size: 2.35rem; line-height: 1.06; }
h2 { font-size: 1.55rem; }
h3 { font-size: 1.2rem; }
p, li, label, .stMarkdown { color: var(--gf-ink-2); font-size: 1.02rem; }

/* Strip default Streamlit chrome for a cleaner product feel */
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer { display: none !important; }
[data-testid="stHeader"] { background: transparent; height: 0; }

/* Sidebar */
[data-testid="stSidebar"] {
  background: var(--gf-surface);
  border-right: 1px solid var(--gf-border);
}
[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }

/* Buttons */
.stButton > button, .stLinkButton > a, .stDownloadButton > button {
  border-radius: 10px; font-weight: 600; border: 1px solid var(--gf-border-strong);
  transition: background .15s ease, border-color .15s ease, color .15s ease, filter .15s ease;
  box-shadow: none; cursor: pointer;
}
.stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {
  background: var(--gf-grad); border: none; box-shadow: var(--gf-glow);
}
.stButton > button:hover { border-color: var(--gf-brand); color: var(--gf-brand); }
.stButton > button[kind="primary"], .stButton > button[kind="primary"] * { color: #fff !important; }
.stButton > button[kind="primary"]:hover { filter: brightness(1.06); color: #fff !important; transform: translateY(-1px); }

/* Visible keyboard focus rings (accessibility) */
.stButton > button:focus-visible, .stLinkButton > a:focus-visible,
.stTextInput input:focus-visible, .stTabs [data-baseweb="tab"]:focus-visible {
  outline: 2px solid var(--gf-brand); outline-offset: 2px;
}

/* Tabs → clean underline segmented control */
.stTabs [data-baseweb="tab-list"] { gap: 8px; border-bottom: 1px solid var(--gf-border); }
.stTabs [data-baseweb="tab"] {
  font-weight: 600; color: var(--gf-muted); padding: 10px 4px; font-size: 1.02rem; background: transparent;
}
.stTabs [aria-selected="true"] { color: var(--gf-brand); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--gf-grad) !important; height: 3px; border-radius: 3px; }

/* Inputs */
[data-baseweb="input"], [data-baseweb="select"] > div, .stTextInput input {
  border-radius: 10px !important;
}

/* Dataframe polish */
[data-testid="stDataFrame"] { border: 1px solid var(--gf-border); border-radius: 12px; }

/* ── Custom components ─────────────────────────────────────────────── */

.gf-ico { stroke-width: 2; }
.gf-hero {
  display: flex; flex-direction: column; gap: 6px; margin: 4px 0 8px;
}
.gf-hero-row {
  display: flex; align-items: center; gap: 18px;
}
.gf-hero-mark {
  width: 56px; height: 56px; border-radius: 16px; flex: none;
  display: grid; place-items: center; color: #fff;
  background: var(--gf-grad); box-shadow: var(--gf-glow); border: none;
}
.gf-hero h1 { margin: 0; line-height: 1.04; }
.gf-hero-sub { color: var(--gf-ink-2); font-size: 1.06rem; margin-top: 0; }
.gf-pill {
  display: inline-flex; align-items: center; font-size: .66rem; font-weight: 800; letter-spacing: .09em;
  text-transform: uppercase; color: #fff; background: var(--gf-grad);
  padding: 4px 11px; border-radius: 999px; border: none; vertical-align: middle;
  box-shadow: 0 2px 8px rgba(37,99,235,.28);
}

/* Mandatory safety banner */
.gf-banner {
  display: flex; gap: 12px; align-items: flex-start;
  background: var(--gf-fail-soft);
  border: 1px solid rgba(220,38,38,0.24); border-left: 4px solid var(--gf-fail);
  color: #7a1d1d; border-radius: 12px; padding: 14px 16px; margin: 10px 0 22px;
  font-size: .9rem; line-height: 1.45;
}
.gf-banner b { color: #641717; }
.gf-banner .gf-banner-ico { color: var(--gf-fail); margin-top: 1px; flex: none; }

/* KPI tiles */
.gf-tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 6px 0 4px; }
.gf-tile {
  background: var(--gf-surface); border: 1px solid var(--gf-border);
  border-radius: 14px; padding: 16px 18px; box-shadow: var(--gf-shadow);
}
.gf-tile .gf-tile-val { font-size: 2rem; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }
.gf-tile .gf-tile-lbl {
  font-size: .78rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
  color: var(--gf-muted); margin-top: 6px; display: flex; align-items: center; gap: 7px;
}

/* Report card */
.gf-card {
  background: var(--gf-surface); border: 1px solid var(--gf-border);
  border-radius: 16px; padding: 18px 20px; margin: 14px 0;
  box-shadow: var(--gf-shadow);
}
.gf-card, .gf-tile {
  transition: box-shadow .18s ease, transform .18s ease, border-color .18s ease;
}
.gf-card:hover, .gf-tile:hover {
  box-shadow: var(--gf-shadow-hover); transform: translateY(-1px); border-color: var(--gf-brand-border);
}
.gf-card-top { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.gf-card-titles { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.gf-drug { font-size: 1.32rem; font-weight: 800; color: var(--gf-ink); letter-spacing: -0.01em; }
.gf-badge {
  display: inline-flex; align-items: center; gap: 6px; font-size: .82rem; font-weight: 700;
  padding: 4px 11px; border-radius: 999px; white-space: nowrap;
}
.gf-conf { text-align: right; line-height: 1; }
.gf-conf-num { font-size: 1.35rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.gf-conf-lbl { display: block; font-size: .72rem; color: var(--gf-muted); text-transform: uppercase; letter-spacing: .04em; margin-top: 3px; }
.gf-meter { height: 8px; border-radius: 999px; background: #e6ebf2; margin: 14px 0 16px; overflow: hidden; }
.gf-meter-fill { height: 100%; border-radius: 999px; transition: width .4s ease; }
.gf-evd {
  display: flex; gap: 9px; align-items: flex-start; font-size: .88rem; line-height: 1.45;
  background: var(--gf-plane); border: 1px solid var(--gf-border);
  border-radius: 10px; padding: 10px 12px; color: var(--gf-ink-2);
}
.gf-evd strong { color: var(--gf-ink); }
.gf-evd .gf-ico { flex: none; margin-top: 1px; }
.gf-row { display: flex; align-items: baseline; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
.gf-row-label { font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--gf-muted); min-width: 190px; }
.gf-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.gf-chip {
  font-family: var(--gf-mono); font-size: .78rem;
  background: var(--gf-brand-soft); color: var(--gf-brand);
  border: 1px solid var(--gf-brand-border); border-radius: 7px; padding: 2px 8px;
}
.gf-chip--muted { background: var(--gf-nocall-soft); color: var(--gf-muted); border-color: var(--gf-border); font-family: 'Fira Sans', system-ui; }
.gf-target { font-weight: 600; font-size: .9rem; }
.gf-reasons { margin: 12px 0 0; padding-left: 18px; color: var(--gf-ink-2); font-size: .85rem; }
.gf-reasons li { margin: 3px 0; }
/* Login page */
.gf-login { text-align: center; margin: 6px 0 2px; display: flex; flex-direction: column; align-items: center; }
.gf-login-row { display: flex; flex-direction: row; align-items: center; justify-content: center; gap: 14px; }
.gf-login-mark { margin: 0; width: 56px; height: 56px; border-radius: 16px; }
.gf-login-title { font-size: 2.15rem; margin: 0; font-weight: 800; letter-spacing: -0.02em; }
.gf-login-sub { margin: 12px auto 0; max-width: 360px; }
.gf-login-hint { text-align: center; font-size: .82rem; color: var(--gf-muted); margin: 10px 4px 2px; line-height: 1.4; }
.gf-or { display: flex; align-items: center; text-align: center; color: var(--gf-muted); font-size: .74rem; text-transform: uppercase; letter-spacing: .07em; margin: 20px 0 8px; }
.gf-or::before, .gf-or::after { content: ""; flex: 1; height: 1px; background: var(--gf-border); }
.gf-or span { padding: 0 12px; }
.gf-login-foot { text-align: center; font-size: .74rem; color: var(--gf-muted); margin-top: 22px; }

/* Login form: roomier inputs */
.stForm { border: none !important; padding: 0 !important; }
.stTextInput input { padding: 10px 12px !important; }

/* Respect reduced-motion preference */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition-duration: .001ms !important; animation-duration: .001ms !important; }
  .gf-card:hover, .gf-tile:hover { transform: none; }
}
</style>""",
        unsafe_allow_html=True,
    )


_inject_css()

# ─── Authentication ──────────────────────────────────────────────────────────
from app.auth import is_authenticated, is_guest, render_login_page, render_user_sidebar  # noqa: E402
from app.database import (  # noqa: E402
    upsert_user_profile,
    create_patient,
    list_patients,
    create_genome_analysis,
    update_analysis_status,
    save_predictions,
    list_analyses,
    get_predictions_for_analysis,
)
from app.storage import upload_fasta  # noqa: E402
from app.icons import icon  # noqa: E402

# Gate: require authentication
if not is_authenticated():
    render_login_page()
    st.stop()

# Ensure user profile exists in public.users table.
# Guest/demo sessions are in-memory only and never touch Supabase.
_user = st.session_state["user"]
_user_id = _user["id"]
_user_meta = _user.get("user_metadata", {})
if not is_guest():
    try:
        upsert_user_profile(
            user_id=_user_id,
            email=_user.get("email", ""),
            full_name=_user_meta.get("full_name"),
        )
    except Exception as e:  # noqa: BLE001 - never let profile sync break the app
        st.warning(f"Could not sync user profile (continuing anyway): {e}")

# ─── Header / hero ───────────────────────────────────────────────────────────
st.markdown(
    '<div class="gf-hero">'
    f'<div class="gf-hero-mark">{icon("shield-check", 26)}</div>'
    '<div>'
    '<h1><span class="gf-wordmark">BioShield AI</span></h1>'
    '<div class="gf-hero-sub">Calibrated antibiotic-resistance prediction for '
    '<em>Staphylococcus aureus</em> — per-drug verdict, confidence, and honest evidence.</div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

# ─── Mandatory safety banner (cannot be dismissed) ───────────────────────────
st.markdown(
    '<div class="gf-banner">'
    f'<span class="gf-banner-ico">{icon("alert-triangle", 20)}</span>'
    '<div><b>Research prototype — confirm every result with standard laboratory testing.</b> '
    'Decision support only; a trained professional makes the decision. '
    'This tool predicts and explains resistance that <em>already exists</em> in a genome — '
    'it never designs, modifies, or optimises any organism.</div>'
    '</div>',
    unsafe_allow_html=True,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _load_metrics() -> dict | None:
    p = PROCESSED / "metrics.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


def _load_precomputed_reports(genome_id: str) -> list[dict] | None:
    """Load a cached JSON report list for a demo genome."""
    p = PROCESSED / "demo_reports" / f"{genome_id}.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


def _models_ready() -> bool:
    return (PROCESSED / "models").is_dir() and any(
        (PROCESSED / "models").glob("*.pkl")
    )


def _run_pipeline_on_fasta(fasta_path: str) -> list[dict] | None:
    """
    Single-genome inference path: featurize → predict → report.
    Returns a list of report dicts (DATA_SPEC §6) or None on error.
    """
    try:
        from genome_firewall.report import build_reports_for_genome  # type: ignore
        return build_reports_for_genome(fasta_path)
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        return None


# ─── Verdict rendering ────────────────────────────────────────────────────────

# Verdict → (icon name, label, status color, soft background) — status ramp, never color alone.
_VERDICT_STYLE = {
    "fail":   ("x-circle",     "Likely to fail", "var(--gf-fail)", "var(--gf-fail-soft)"),
    "work":   ("check-circle", "Likely to work", "var(--gf-work)", "var(--gf-work-soft)"),
    "nocall": ("minus-circle", "No-call",        "var(--gf-nocall)", "var(--gf-nocall-soft)"),
}

# Evidence category → (icon name, title, detail)
_EVIDENCE_META = {
    "i":   ("flask", "(i) Known resistance marker detected",
            "Direct catalog hit from AMRFinderPlus — a gene or point mutation with a "
            "documented resistance role."),
    "ii":  ("bar-chart", "(ii) Statistical association only",
            "Driven by a model coefficient/SHAP signal. This is a statistical pattern — "
            "NOT proven biological causation."),
    "iii": ("circle", "(iii) No known resistance signal",
            "No resistance markers found. Any 'work' verdict is governed by the target "
            "gate, never by absence alone."),
}

import html as _html  # noqa: E402


def render_report_card(report: dict) -> None:
    ab = report.get("antibiotic", "unknown")
    verdict = report.get("verdict", "nocall")
    confidence = float(report.get("confidence", 0.0) or 0.0)
    ev_cat = report.get("evidence_category", "iii")
    features = report.get("supporting_features", [])
    target_present = report.get("target_present", False)
    reasons = report.get("reasons", [])

    v_icon, label, color, soft = _VERDICT_STYLE.get(verdict, _VERDICT_STYLE["nocall"])
    ev_icon, ev_title, ev_detail = _EVIDENCE_META.get(ev_cat, _EVIDENCE_META["iii"])
    conf_pct = max(0, min(100, round(confidence * 100)))

    if features:
        chips = "".join(f'<span class="gf-chip">{_html.escape(str(f))}</span>' for f in features)
    else:
        chips = '<span class="gf-chip gf-chip--muted">none cited</span>'

    target_txt = "Yes — confirmed present" if target_present else "No / undetermined"
    target_color = "var(--gf-work)" if target_present else "var(--gf-warn)"

    reasons_html = ""
    if reasons:
        items = "".join(f"<li>{_html.escape(str(r))}</li>" for r in reasons)
        reasons_html = f'<ul class="gf-reasons">{items}</ul>'

    st.markdown(
        f'<div class="gf-card" style="border-left:4px solid {color}">'
        f'<div class="gf-card-top">'
        f'<div class="gf-card-titles">'
        f'<span class="gf-drug">{_html.escape(ab.capitalize())}</span>'
        f'<span class="gf-badge" style="background:{soft};color:{color}">{icon(v_icon, 15)} {label}</span>'
        f'</div>'
        f'<div class="gf-conf"><span class="gf-conf-num" style="color:{color}">{conf_pct}%</span>'
        f'<span class="gf-conf-lbl">confidence</span></div>'
        f'</div>'
        f'<div class="gf-meter"><div class="gf-meter-fill" style="width:{conf_pct}%;background:{color}"></div></div>'
        f'<div class="gf-evd" style="color:{color}">{icon(ev_icon, 16)}'
        f'<div style="color:var(--gf-ink-2)"><strong>{ev_title}</strong> — {ev_detail}</div></div>'
        f'<div class="gf-row"><span class="gf-row-label">Supporting genes / mutations</span>'
        f'<div class="gf-chips">{chips}</div></div>'
        f'<div class="gf-row"><span class="gf-row-label">Target gene present</span>'
        f'<span class="gf-target" style="color:{target_color}">{target_txt}</span></div>'
        f'{reasons_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── Performance panel ────────────────────────────────────────────────────────

def render_performance_panel(metrics: dict) -> None:
    st.subheader("Model performance (held-out grouped test split)")
    st.caption(
        "All metrics computed on the **held-out test split** — genomes whose genetic "
        "clusters were never seen during training or calibration."
    )

    # Per-antibiotic table
    per_drug = metrics.get("per_drug", {})
    if per_drug:
        import pandas as pd
        rows = []
        for ab, m in per_drug.items():
            rows.append({
                "Antibiotic": ab,
                "Bal. Acc.": f"{m.get('balanced_accuracy', float('nan')):.3f}",
                "Recall R": f"{m.get('recall_R', float('nan')):.3f}",
                "Recall S": f"{m.get('recall_S', float('nan')):.3f}",
                "F1": f"{m.get('f1', float('nan')):.3f}",
                "AUROC": f"{m.get('auroc', float('nan')):.3f}",
                "PR-AUC": f"{m.get('pr_auc', float('nan')):.3f}",
                "Brier": f"{m.get('brier', float('nan')):.3f}",
                "No-call %": f"{m.get('nocall_rate', float('nan')):.1%}",
                "Acc-on-called": f"{m.get('accuracy_on_called', float('nan')):.3f}",
            })
        st.dataframe(pd.DataFrame(rows).set_index("Antibiotic"), use_container_width=True)
    else:
        st.info("Per-drug metrics not yet available — run `make evaluate` first.")

    # Reliability plot
    reliability_png = REPORTS_DIR / "reliability.png"
    if reliability_png.exists():
        st.subheader("Reliability diagram (calibration curve)")
        st.image(str(reliability_png), use_container_width=True)
        st.caption(
            "A well-calibrated model tracks the diagonal. Calibration was fit on the "
            "dedicated **calibration split** and evaluated on the **test split** only."
        )
    else:
        st.info("Reliability plot not yet generated — run `make calibrate evaluate`.")

    # PR-curve
    pr_png = REPORTS_DIR / "pr_curves.png"
    if pr_png.exists():
        st.subheader("Precision–Recall curves")
        st.image(str(pr_png), use_container_width=True)

    # Per-group generalization
    per_group = metrics.get("per_group", {})
    if per_group:
        st.subheader("Per-genetic-group generalization")
        st.caption(
            "Groups marked *unseen* were held out of training entirely. "
            "Performance drop on unseen groups is expected and reported honestly."
        )
        import pandas as pd
        rows = []
        for group_key, gm in per_group.items():
            rows.append({
                "Genetic group": group_key,
                "In training": "No" if gm.get("unseen_in_training") else "Yes",
                "N test": gm.get("n_test", "?"),
                "Bal. Acc.": f"{gm.get('balanced_accuracy', float('nan')):.3f}",
                "AUROC": f"{gm.get('auroc', float('nan')):.3f}",
                "No-call %": f"{gm.get('nocall_rate', float('nan')):.1%}",
            })
        st.dataframe(pd.DataFrame(rows).set_index("Genetic group"), use_container_width=True)
    else:
        st.info("Per-group breakdown not yet available — run `make evaluate`.")

    # DL vs baseline comparison
    dl_vs_baseline = metrics.get("dl_vs_baseline", {})
    if dl_vs_baseline:
        st.subheader("ESM-2 (DL) vs. logistic regression baseline")
        st.caption("Comparison on identical splits and calibration protocol.")
        import pandas as pd
        rows = []
        for ab, d in dl_vs_baseline.items():
            rows.append({
                "Antibiotic": ab,
                "Baseline AUROC": f"{d.get('baseline_auroc', float('nan')):.3f}",
                "ESM-2 AUROC": f"{d.get('dl_auroc', float('nan')):.3f}",
                "Delta AUROC": f"{d.get('delta_auroc', float('nan')):+.3f}",
                "Baseline Brier": f"{d.get('baseline_brier', float('nan')):.3f}",
                "ESM-2 Brier": f"{d.get('dl_brier', float('nan')):.3f}",
            })
        st.dataframe(pd.DataFrame(rows).set_index("Antibiotic"), use_container_width=True)
        st.caption(
            "Honest outcome: if ESM-2 does not beat the interpretable baseline, "
            "we report it as such — that is a rigor result, not a failure."
        )


# ─── Patients & saved records (persistence) ──────────────────────────────────

def _uid() -> str:
    return st.session_state["user"]["id"]


def _patient_label(p: dict) -> str:
    return p["patient_name"] + (f' · {p["patient_id"]}' if p.get("patient_id") else "")


def _add_guest_patient(name: str, mrn: str) -> None:
    patients = st.session_state.setdefault("guest_patients", [])
    patients.append({
        "id": f"guest-{len(patients) + 1}",
        "patient_name": name,
        "patient_id": mrn or None,
    })


def render_patient_panel() -> dict | None:
    """Sidebar patient picker + 'add patient' form. Works for signed-in doctors
    (Supabase-backed) and guests (in-memory, not persisted). Returns the active
    patient dict, or None if none is selected yet."""
    st.header("Patient")
    guest = is_guest()

    if guest:
        patients = st.session_state.setdefault("guest_patients", [])
    else:
        try:
            patients = list_patients(_uid())
        except Exception as e:  # noqa: BLE001
            st.error("Couldn't load patients.")
            st.caption(f"Has `db/schema.sql` been applied to Supabase? ({e})")
            return None

    selected: dict | None = None
    if patients:
        labels = {_patient_label(p): p for p in patients}
        choice = st.selectbox("Active patient", list(labels.keys()))
        selected = labels[choice]
    else:
        msg = "No patients yet — add your first one below."
        if guest:
            msg += " (Guest patients aren't saved after you sign out.)"
        st.caption(msg)

    with st.expander("➕ Add patient", expanded=not patients):
        # Reset the form fields after a successful add (before widgets exist).
        if st.session_state.pop("_clear_new_patient", False):
            for k in ("np_name", "np_mrn"):
                st.session_state.pop(k, None)

        # Optional: autofill name + MRN from an uploaded patient-info PDF.
        pdf = st.file_uploader(
            "Autofill from a patient PDF", type=["pdf"], key="patient_pdf",
            help="Upload a referral / chart PDF — we extract the name and MRN for you to confirm.",
        )
        if pdf is not None and st.session_state.get("_pdf_done") != pdf.name:
            from app.pdf_intake import parse_patient_pdf
            res = parse_patient_pdf(pdf.getvalue())
            st.session_state["_pdf_done"] = pdf.name
            if res["ok"] and (res["name"] or res["mrn"]):
                if res["name"]:
                    st.session_state["np_name"] = res["name"]
                if res["mrn"]:
                    st.session_state["np_mrn"] = res["mrn"]
                st.session_state["_pdf_msg"] = ("ok", f"Autofilled from {pdf.name} — review below.")
            elif res["ok"]:
                st.session_state["_pdf_msg"] = ("warn", "No name/MRN found in that PDF — enter them manually.")
            else:
                st.session_state["_pdf_msg"] = ("warn", f"Couldn't read that PDF: {res['error']}")
            st.rerun()

        msg = st.session_state.get("_pdf_msg")
        if msg:
            (st.success if msg[0] == "ok" else st.warning)(msg[1])

        with st.form("new_patient_form"):
            name = st.text_input("Patient name *", key="np_name", placeholder="Jane Doe")
            mrn = st.text_input("Patient ID / MRN", key="np_mrn", placeholder="optional")
            if st.form_submit_button("Add patient", use_container_width=True):
                name_v = (name or "").strip()
                mrn_v = (mrn or "").strip()
                if not name_v:
                    st.error("Patient name is required.")
                else:
                    try:
                        if guest:
                            _add_guest_patient(name_v, mrn_v)
                        else:
                            create_patient(
                                user_id=_uid(),
                                patient_name=name_v,
                                patient_id=mrn_v or None,
                            )
                        st.session_state["_clear_new_patient"] = True
                        st.session_state.pop("_pdf_msg", None)
                        # keep _pdf_done so the same file isn't re-parsed into the cleared form
                        st.success(f"Added {name_v}.")
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not add patient: {e}")

    return selected


def _prediction_rows(items: list[dict], gene_key: str) -> list[dict]:
    """Normalize DATA_SPEC §6 reports or DB prediction rows into table rows."""
    verdict_label = {"fail": "Likely to fail", "work": "Likely to work", "nocall": "No-call"}
    return [
        {
            "Antibiotic": p.get("antibiotic", ""),
            "Verdict": verdict_label.get(p.get("verdict"), p.get("verdict", "")),
            "Confidence": f"{float(p.get('confidence', 0) or 0):.0%}",
            "Evidence": p.get("evidence_category", ""),
            "Supporting genes": ", ".join(p.get(gene_key) or []),
        }
        for p in items
    ]


def render_patient_records(patient: dict | None) -> None:
    """History tab: list the active patient's saved analyses and predictions."""
    st.subheader("Patient records")

    if not patient:
        st.info("Add or select a patient in the sidebar to view their records.")
        return

    import pandas as pd

    header_line = (
        f"**{patient['patient_name']}**"
        + (f" · MRN {patient['patient_id']}" if patient.get("patient_id") else "")
    )

    # ── Guest: in-memory records for this session only ────────────────────────
    if is_guest():
        recs = st.session_state.get("guest_records", {}).get(patient["id"], [])
        st.markdown(f"{header_line} — {len(recs)} analysis(es) this session.")
        st.caption("Guest records live only in this session and aren't saved after sign-out.")
        if not recs:
            st.caption("No analyses yet. Run a prediction and click **Save to records**.")
            return
        for r in recs:
            head = f"{r['genome_id']} · {r['created_at'][:10]} · {r['status']}"
            with st.expander(head):
                rows = _prediction_rows(r["reports"], "supporting_features")
                st.dataframe(pd.DataFrame(rows).set_index("Antibiotic"), use_container_width=True)
        return

    # ── Signed-in: Supabase-backed history ────────────────────────────────────
    try:
        analyses = [
            a for a in list_analyses(_uid()) if a.get("patient_id") == patient["id"]
        ]
    except Exception as e:  # noqa: BLE001
        st.error(f"Couldn't load records (is the schema applied?): {e}")
        return

    st.markdown(f"{header_line} — {len(analyses)} saved analysis(es).")
    if not analyses:
        st.caption("No saved analyses yet. Run a prediction and click **Save to records**.")
        return

    for a in analyses:
        created = str(a.get("created_at", ""))[:10]
        header = f"{a.get('genome_id', 'genome')} · {created} · {a.get('status', '')}"
        with st.expander(header):
            try:
                preds = get_predictions_for_analysis(a["id"])
            except Exception as e:  # noqa: BLE001
                st.caption(f"Could not load predictions: {e}")
                continue
            if not preds:
                st.caption("No predictions stored for this analysis.")
                continue
            rows = _prediction_rows(preds, "supporting_genes")
            st.dataframe(pd.DataFrame(rows).set_index("Antibiotic"), use_container_width=True)


def save_reports_to_patient(patient: dict, genome_label: str, reports: list[dict]) -> None:
    """Save a genome analysis + its predictions under the active patient.
    Guests are saved to an in-memory session store; doctors to Supabase."""
    if is_guest():
        store = st.session_state.setdefault("guest_records", {})
        store.setdefault(patient["id"], []).append({
            "genome_id": genome_label,
            "created_at": datetime.now().isoformat(),
            "status": "complete",
            "reports": reports,
        })
        return

    analysis = create_genome_analysis(
        user_id=_uid(),
        patient_id=patient["id"],
        genome_id=genome_label,
        species="Staphylococcus aureus",
    )
    if not analysis:
        raise RuntimeError("analysis row was not created")
    save_predictions(_uid(), analysis["id"], reports)
    update_analysis_status(analysis["id"], "complete")


# ─── Sidebar — input ──────────────────────────────────────────────────────────

with st.sidebar:
    current_patient = render_patient_panel()
    st.divider()
    st.header("Genome input")

    input_mode = None
    uploaded_file = None
    demo_genome_id = None

    if current_patient is None:
        st.caption("Add or select a patient above, then upload a genome for them.")
    else:
        st.caption(f"Uploading for **{current_patient['patient_name']}**.")
        input_mode = st.radio(
            "Input mode",
            ["Upload FASTA (live)", "Demo genome (precomputed)"],
            index=0,
        )
        if input_mode == "Upload FASTA (live)":
            uploaded_file = st.file_uploader(
                "FASTA file (.fna / .fa / .fasta)",
                type=["fna", "fa", "fasta", "txt"],
            )
            if not _models_ready():
                st.warning(
                    "Trained models not found — run `make all` to build the full "
                    "pipeline. Demo mode is available in the meantime."
                )
        else:
            demo_dir = PROCESSED / "demo_reports"
            demo_options: list[str] = []
            if demo_dir.exists():
                demo_options = [p.stem for p in sorted(demo_dir.glob("*.json"))]
            if demo_options:
                demo_genome_id = st.selectbox(
                    "Select demo genome",
                    demo_options,
                    help="These genomes were precomputed from real BV-BRC data.",
                )
            else:
                st.info(
                    "No precomputed demo genomes found yet. Run `make all` to build "
                    "the pipeline, or upload a FASTA above."
                )

    st.divider()
    st.markdown("**About**")
    st.markdown(
        "BioShield AI predicts and explains **existing** AMR in *S. aureus* genomes.  "
        "It never suggests changes to organisms.  "
        "Built for Hack-Nation Challenge 06."
    )

# Render user info and sign-out in sidebar
render_user_sidebar()

# ─── Main content ─────────────────────────────────────────────────────────────

tab_results, tab_records, tab_performance, tab_about = st.tabs(
    ["New prediction", "Patient records", "Model performance", "About & responsible AI"]
)

# ── Tab 1: New prediction ─────────────────────────────────────────────────────
with tab_results:

    if current_patient is None:
        st.info(
            "**Start with a patient.** Add or select a patient in the sidebar, then "
            "upload their genome FASTA to run a prediction."
        )

    reports: list[dict] | None = None

    if input_mode == "Upload FASTA (live)" and uploaded_file is not None:
        if not _models_ready():
            st.error(
                "Models are not trained yet. Run `make all` to build the full pipeline."
            )
        else:
            with st.spinner("Running annotation and prediction pipeline…"):
                with tempfile.NamedTemporaryFile(
                    suffix=".fna", delete=False
                ) as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name
                try:
                    reports = _run_pipeline_on_fasta(tmp_path)
                finally:
                    os.unlink(tmp_path)

            if reports is None:
                st.error(
                    "Pipeline failed. Check that AMRFinderPlus is installed "
                    "(`make amr-setup`) and models are trained (`make all`)."
                )

    elif input_mode == "Demo genome (precomputed)" and demo_genome_id:
        reports = _load_precomputed_reports(demo_genome_id)
        if reports is None:
            st.warning(f"Could not load precomputed reports for `{demo_genome_id}`.")

    # ── Render report cards ───────────────────────────────────────────────────
    if reports:
        # Re-emit safety banner inline with results (impossible to miss)
        st.warning(
            "**Research prototype.** Every prediction below must be confirmed with "
            "standard laboratory testing before any clinical decision is made."
        )

        genome_label = (
            uploaded_file.name if uploaded_file else demo_genome_id
        )
        st.subheader(f"AMR predictions — {genome_label}")

        # Summary row
        verdicts = [r.get("verdict", "nocall") for r in reports]
        n_fail = verdicts.count("fail")
        n_work = verdicts.count("work")
        n_nocall = verdicts.count("nocall")

        st.markdown(
            '<div class="gf-tiles">'
            f'<div class="gf-tile"><div class="gf-tile-val" style="color:var(--gf-fail)">{n_fail}</div>'
            f'<div class="gf-tile-lbl"><span style="color:var(--gf-fail)">{icon("x-circle", 15)}</span>Likely to fail</div></div>'
            f'<div class="gf-tile"><div class="gf-tile-val" style="color:var(--gf-work)">{n_work}</div>'
            f'<div class="gf-tile-lbl"><span style="color:var(--gf-work)">{icon("check-circle", 15)}</span>Likely to work</div></div>'
            f'<div class="gf-tile"><div class="gf-tile-val" style="color:var(--gf-nocall)">{n_nocall}</div>'
            f'<div class="gf-tile-lbl"><span style="color:var(--gf-nocall)">{icon("minus-circle", 15)}</span>No-call</div></div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.write("")

        for report in reports:
            render_report_card(report)

        # ── Save to patient records ───────────────────────────────────────────
        st.divider()
        if current_patient:
            if st.button(
                f"💾 Save to {current_patient['patient_name']}'s records",
                type="primary",
            ):
                try:
                    save_reports_to_patient(current_patient, genome_label, reports)
                    note = " (this session only)" if is_guest() else ""
                    st.success(
                        f"Saved {len(reports)} predictions to "
                        f"{current_patient['patient_name']}'s record{note}. "
                        "See the **Patient records** tab."
                    )
                except Exception as e:  # noqa: BLE001
                    st.error(f"Could not save records: {e}")

    elif input_mode == "Upload FASTA (live)" and uploaded_file is None:
        st.info("Upload a FASTA file in the sidebar to run a live prediction.")

    elif input_mode == "Demo genome (precomputed)" and not demo_genome_id:
        st.info(
            "No demo genomes available yet. Run the pipeline first with `make all`."
        )

    else:
        if input_mode == "Upload FASTA (live)":
            st.info("Upload a FASTA file in the sidebar to run a live prediction.")

# ── Tab 2: Patient records ────────────────────────────────────────────────────
with tab_records:
    render_patient_records(current_patient)

# ── Tab 3: Model performance ──────────────────────────────────────────────────
with tab_performance:
    metrics = _load_metrics()
    if metrics:
        render_performance_panel(metrics)
    else:
        st.info(
            "No metrics found yet. Run the full pipeline (`make all`) to generate "
            "`data/processed/metrics.json` and the reliability/PR plots."
        )
        st.markdown(
            """
            **What will appear here after running the pipeline:**
            - Per-antibiotic: balanced accuracy, recall R/S, F1, AUROC, PR-AUC, Brier score, no-call rate
            - Reliability diagram (calibration curve on held-out test split)
            - Precision–Recall curves per drug
            - Per-genetic-group generalization (incl. unseen groups)
            - ESM-2 vs. logistic regression baseline deltas
            """
        )

# ── Tab 3: About & Responsible AI ────────────────────────────────────────────
with tab_about:
    st.subheader("What this tool does")
    st.markdown(
        """
        **BioShield AI** takes a reconstructed *Staphylococcus aureus* genome (FASTA)
        and predicts, for each of several antibiotics, whether resistance is:
        - **Likely to fail** — resistance markers detected; drug probably won't work.
        - **Likely to work** — target confirmed present, no resistance markers found.
        - **No-call** — conflicting/weak evidence, OOD genome, or target gate fired; cannot make a confident call.
        """
    )

    st.subheader("Responsible AI & defensive-use statement")
    st.markdown(
        """
        **Strictly defensive.** This tool predicts and explains resistance that *already exists*
        in a sequenced genome. It never designs, modifies, optimises, or suggests changes to any
        organism. Any task that would require generating or suggesting new resistance mechanisms
        is refused by construction.

        **Calibrated confidence.** Confidence scores are probability-calibrated on a dedicated
        held-out calibration split (never on training data). Calibration is verified with a
        reliability diagram and Brier score on the hidden test split.

        **Honest no-call.** When evidence is weak, conflicting, or out-of-distribution, the tool
        returns no-call rather than forcing a verdict. No-call rate and accuracy-on-called are
        reported separately.

        **Honest evidence categories.**
        - (i) *Known resistance gene/mutation* — a direct catalog hit from AMRFinderPlus.
        - (ii) *Statistical association only* — a model coefficient or SHAP value. Explicitly
          labeled as *not proven causal*. A statistical pattern is not biological proof.
        - (iii) *No known signal* — absence of markers. A 'work' verdict from absence alone is
          blocked by the target-gate: the drug's molecular target must be confirmed present.

        **Honest generalization.** Metrics are reported broken down by genetic cluster group,
        including groups entirely unseen during training. Expected performance drops on
        unseen groups are reported, not hidden.

        **No data leakage.** Genomes are split by genetic cluster (Mash/skani), never randomly.
        Whole clusters go to exactly one of train / calibration / test. Near-identical genomes
        are de-duplicated before splitting. This is verified by assertion in the split code.

        **Human oversight.** Every result is accompanied by a mandatory lab-confirmation banner.
        The tool provides *decision support*, not decisions. A trained clinical professional
        makes the final call.
        """
    )

    st.subheader("Limitations & scope")
    st.markdown(
        """
        - **Species scope:** *Staphylococcus aureus* only (incl. MRSA). Does not cover other
          pathogens, and makes no claims about generalization outside this species.
        - **Antibiotics covered:** a subset chosen by label coverage from BV-BRC (documented in
          `DECISIONS.md`). Antibiotics not in scope return no-call by construction.
        - **Sequencing quality:** requires assembled contig FASTA from WGS; does not handle
          raw reads. Quality thresholds are documented.
        - **Novel resistance mechanisms:** resistance mediated by genes or mutations absent from
          the AMRFinderPlus S. aureus catalog will not be detected. This is a known limitation
          inherent to any catalog-based approach.
        - **Not a diagnostic device.** This is a research prototype, not a cleared or approved
          clinical diagnostic tool. It must not be used as a substitute for laboratory testing.
        """
    )

    st.subheader("Relevant documents")
    docs = [
        ("docs/MODEL_CARD.md", "Model Card — species, antibiotics, metrics, limitations"),
        ("docs/RESPONSIBLE_AI.md", "Responsible AI — how each responsibility requirement is addressed"),
        ("docs/DECISIONS.md", "Decision log — adversarial reasoning behind every non-trivial choice"),
        ("docs/RISKS.md", "Risk register — open risks and mitigations"),
        ("docs/DATA_SPEC.md", "Data contracts — schemas for every pipeline stage interface"),
    ]
    for path, desc in docs:
        full = ROOT / path
        if full.exists():
            content = full.read_text()
            with st.expander(f"{path} — {desc}"):
                st.markdown(content)
        else:
            st.caption(f"`{path}` — {desc} *(not yet generated)*")
