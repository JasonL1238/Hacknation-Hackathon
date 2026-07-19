"""
BioShield AI — Design system.

A single, cohesive set of design tokens (color, type, space, radius, shadow,
motion) exposed as CSS variables, plus the global stylesheet that turns a stock
Streamlit page into a premium clinical-intelligence application shell.

Design direction (see the product brief):
  - Deep navy / near-black navigation surface; clean, light content plane.
  - Refined blue → cyan primary accent, kept distinct from the green
    "favorable outcome" status so the two never blur.
  - Green = favorable · Red = resistance/failure · Amber = uncertainty/no-call.
  - High-contrast type, tabular numerals for data, mono for identifiers only.
  - Very subtle depth, thin precise borders, controlled radii, quiet motion.

Nothing here is decorative for its own sake: color carries clinical meaning and
status is *never* communicated by color alone (always icon + label + text).
"""

from __future__ import annotations

import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Design tokens.  Kept in one place; referenced everywhere via var(--gf-*).
# ─────────────────────────────────────────────────────────────────────────────
TOKENS = """
:root {
  /* ── Content plane (light) ─────────────────────────────────────────── */
  --gf-bg:            #f4f6fa;   /* app background behind content            */
  --gf-surface:       #ffffff;   /* cards, panels                           */
  --gf-surface-2:     #f8fafc;   /* inset / muted surface                   */
  --gf-elevated:      #ffffff;   /* menus, popovers                         */

  /* ── Navigation plane (deep navy) ──────────────────────────────────── */
  --gf-nav:           #0b1220;   /* sidebar base                            */
  --gf-nav-2:         #0f172a;   /* sidebar raised                          */
  --gf-nav-line:      #1e293b;   /* sidebar hairline                        */
  --gf-nav-ink:       #e2e8f0;   /* sidebar primary text                    */
  --gf-nav-muted:     #7c8aa5;   /* sidebar secondary text                  */
  --gf-nav-active:    #14233d;   /* active nav item background              */

  /* ── Borders ───────────────────────────────────────────────────────── */
  --gf-border:        #e5e9f0;
  --gf-border-strong: #d3dbe6;
  --gf-border-focus:  #2563eb;

  /* ── Text ──────────────────────────────────────────────────────────── */
  --gf-ink:           #0f1b2d;   /* primary                                 */
  --gf-ink-2:         #3f4d63;   /* secondary                               */
  --gf-muted:         #64748b;   /* tertiary / captions                     */
  --gf-faint:         #94a3b8;   /* placeholder / disabled                  */

  /* ── Brand accent (blue → cyan) ────────────────────────────────────── */
  --gf-brand:         #1d4ed8;
  --gf-brand-2:       #2563eb;
  --gf-brand-3:       #0891b2;   /* cyan edge for gradients/details         */
  --gf-brand-soft:    #eef4ff;
  --gf-brand-border:  #cfe0fd;
  --gf-brand-ink:     #1e40af;

  /* ── Clinical status ramp (paired with icon + label, never alone) ──── */
  --gf-work:          #15803d;   --gf-work-2:   #16a34a;
  --gf-work-soft:     #e9f7ef;   --gf-work-border:#bfe6cd;
  --gf-fail:          #b91c1c;   --gf-fail-2:   #dc2626;
  --gf-fail-soft:     #fdecec;   --gf-fail-border:#f4c6c6;
  --gf-nocall:        #b45309;   --gf-nocall-2: #d97706;
  --gf-nocall-soft:   #fdf3e3;   --gf-nocall-border:#f3ddb4;
  --gf-info:          #0e7490;   --gf-info-soft:#e6f6fb;   --gf-info-border:#bfe6f0;
  --gf-neutral:       #475569;   --gf-neutral-soft:#eef1f6;

  /* ── Type ──────────────────────────────────────────────────────────── */
  --gf-sans: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  --gf-mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace;

  /* ── Space (4pt grid) ──────────────────────────────────────────────── */
  --gf-1: 4px;  --gf-2: 8px;  --gf-3: 12px; --gf-4: 16px;
  --gf-5: 20px; --gf-6: 24px; --gf-8: 32px; --gf-10: 40px; --gf-12: 48px;

  /* ── Radius ────────────────────────────────────────────────────────── */
  --gf-r-sm: 6px; --gf-r: 10px; --gf-r-lg: 14px; --gf-r-xl: 18px; --gf-r-pill: 999px;

  /* ── Elevation (subtle) ────────────────────────────────────────────── */
  --gf-sh-1: 0 1px 2px rgba(15,27,45,.05), 0 1px 3px rgba(15,27,45,.05);
  --gf-sh-2: 0 1px 2px rgba(15,27,45,.04), 0 8px 24px rgba(15,27,45,.07);
  --gf-sh-3: 0 12px 40px rgba(15,27,45,.14);
  --gf-ring: 0 0 0 3px rgba(37,99,235,.20);

  /* ── Motion ────────────────────────────────────────────────────────── */
  --gf-fast: .12s cubic-bezier(.2,.6,.2,1);
  --gf-mid:  .2s  cubic-bezier(.2,.6,.2,1);

  /* ── Layout ────────────────────────────────────────────────────────── */
  --gf-content-max: 1180px;
}
"""


def _global_css() -> str:
    return (
        "<style>"
        "@import url('https://fonts.googleapis.com/css2?"
        "family=Inter:wght@400;450;500;600;700;800&"
        "family=IBM+Plex+Mono:wght@400;500;600&display=swap');"
        + TOKENS
        + r"""
/* ── Reset Streamlit chrome ─────────────────────────────────────────── */
[data-testid="stToolbar"], [data-testid="stDecoration"],
#MainMenu, footer, [data-testid="stStatusWidget"] { display:none !important; }
[data-testid="stHeader"] { background:transparent; height:0; overflow:visible; }

html { font-size:16px; }
html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {
  font-family:var(--gf-sans);
  -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
}
.stApp { background:var(--gf-bg); color:var(--gf-ink); }

/* Content column: comfortable measure, generous rhythm */
[data-testid="stAppViewContainer"] .main .block-container {
  max-width:var(--gf-content-max);
  padding:28px 40px 88px;
}
[data-testid="stAppViewBlockContainer"] { padding-top:28px; }

/* Typography scale */
h1,h2,h3,h4 { color:var(--gf-ink); font-family:var(--gf-sans);
  letter-spacing:-.02em; font-weight:700; margin:0; }
h1 { font-size:1.85rem; line-height:1.12; letter-spacing:-.025em; }
h2 { font-size:1.3rem;  line-height:1.2;  }
h3 { font-size:1.06rem; line-height:1.25; font-weight:650; }
p, li, label, .stMarkdown, span, div { color:var(--gf-ink); }
p, li { color:var(--gf-ink-2); font-size:.94rem; line-height:1.55; }
a { color:var(--gf-brand-2); text-decoration:none; }
a:hover { text-decoration:underline; }
code, kbd { font-family:var(--gf-mono); font-size:.86em; }
.gf-tnum { font-variant-numeric:tabular-nums; }

/* Reduce Streamlit's default vertical gaps for a denser product feel */
[data-testid="stVerticalBlock"] { gap:.85rem; }
[data-testid="stHorizontalBlock"] { gap:.85rem; }
hr { margin:.4rem 0; border-color:var(--gf-border); }

/* ── Sidebar → deep navy nav rail (always on — collapsing is disabled) ─ */
[data-testid="stSidebar"] {
  background:var(--gf-nav);
  border-right:1px solid var(--gf-nav-line);
  width:270px !important;
  min-width:270px !important;
  margin-left:0 !important;
  transform:none !important;
  visibility:visible !important;
}
/* Hide the native collapse control so the sidebar can't be dismissed. */
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"] { display:none !important; }
[data-testid="stSidebar"] > div { background:var(--gf-nav); }
[data-testid="stSidebar"] .block-container { padding:18px 14px 14px; }
[data-testid="stSidebar"] * { color:var(--gf-nav-ink); }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:var(--gf-nav-muted); }
[data-testid="stSidebar"] hr { border-color:var(--gf-nav-line); }

/* Nav buttons (rendered as Streamlit buttons in the sidebar) */
[data-testid="stSidebar"] .stButton > button {
  width:100%; justify-content:flex-start; text-align:left;
  background:transparent; border:1px solid transparent; color:var(--gf-nav-ink);
  border-radius:var(--gf-r); padding:8px 11px; font-weight:500; font-size:.92rem;
  box-shadow:none; transition:background var(--gf-fast), color var(--gf-fast);
  margin:1px 0; min-height:0; line-height:1.2;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background:var(--gf-nav-2); color:#fff; border-color:transparent;
}
[data-testid="stSidebar"] .stButton > button:focus-visible {
  outline:none; box-shadow:0 0 0 2px rgba(96,165,250,.55);
}
/* Active nav item: primary-typed button */
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > button[data-testid$="-primary"] {
  background:var(--gf-nav-active); color:#fff; border:1px solid #24375c;
  box-shadow:inset 3px 0 0 var(--gf-brand-2);
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
[data-testid="stSidebar"] .stButton > button[data-testid$="-primary"]:hover {
  background:var(--gf-nav-active); filter:brightness(1.08);
}

/* ── Buttons (content area) ─────────────────────────────────────────── */
.stButton > button, .stDownloadButton > button, .stLinkButton > a {
  border-radius:var(--gf-r); font-weight:550; font-size:.9rem;
  border:1px solid var(--gf-border-strong); color:var(--gf-ink);
  background:var(--gf-surface); box-shadow:var(--gf-sh-1);
  transition:background var(--gf-fast), border-color var(--gf-fast),
             color var(--gf-fast), box-shadow var(--gf-fast), transform var(--gf-fast);
  padding:7px 14px; white-space:nowrap;
}
.stButton > button p { white-space:nowrap; }
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color:var(--gf-brand-2); color:var(--gf-brand); background:var(--gf-brand-soft);
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"],
.stButton > button[data-testid$="-primary"], .stDownloadButton > button[data-testid$="-primary"] {
  background:linear-gradient(180deg,var(--gf-brand-2),var(--gf-brand));
  border:1px solid var(--gf-brand); color:#fff !important; box-shadow:var(--gf-sh-1);
}
.stButton > button[kind="primary"] *, .stButton > button[data-testid$="-primary"] * { color:#fff !important; }
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid$="-primary"]:hover { filter:brightness(1.07); transform:translateY(-1px); }
.stButton > button:active { transform:translateY(0); }
.stButton > button:disabled { opacity:.5; cursor:not-allowed; }

/* Focus rings everywhere */
.stButton>button:focus-visible, .stDownloadButton>button:focus-visible,
input:focus-visible, textarea:focus-visible, [data-baseweb="select"] div:focus-visible {
  outline:none !important; box-shadow:var(--gf-ring) !important;
}

/* ── Inputs ─────────────────────────────────────────────────────────── */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div,
.stTextInput input, .stNumberInput input, .stDateInput input {
  border-radius:var(--gf-r) !important;
  border-color:var(--gf-border-strong) !important;
  background:var(--gf-surface) !important;
}
.stTextInput input, .stNumberInput input, .stDateInput input, textarea {
  font-size:.92rem !important; color:var(--gf-ink) !important;
}
.stTextInput input::placeholder, textarea::placeholder { color:var(--gf-faint) !important; }
[data-testid="stWidgetLabel"] label, .stTextInput label, .stSelectbox label,
.stTextArea label, .stDateInput label, .stRadio label {
  font-size:.82rem !important; font-weight:600 !important; color:var(--gf-ink-2) !important;
}
[data-testid="stWidgetLabel"] p { color:var(--gf-ink-2) !important; font-weight:600; }

/* ── Tabs → segmented underline ─────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] { gap:22px; border-bottom:1px solid var(--gf-border); }
.stTabs [data-baseweb="tab"] {
  font-weight:600; color:var(--gf-muted); padding:10px 2px; font-size:.92rem; background:transparent;
}
.stTabs [aria-selected="true"] { color:var(--gf-brand); }
.stTabs [data-baseweb="tab-highlight"] { background:var(--gf-brand-2)!important; height:2px; }

/* ── Dataframes ─────────────────────────────────────────────────────── */
[data-testid="stDataFrame"], [data-testid="stTable"] {
  border:1px solid var(--gf-border); border-radius:var(--gf-r-lg); overflow:hidden;
}

/* ── Expanders ──────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
  border:1px solid var(--gf-border) !important; border-radius:var(--gf-r-lg) !important;
  background:var(--gf-surface); box-shadow:var(--gf-sh-1); overflow:hidden;
}
[data-testid="stExpander"] summary { font-weight:600; color:var(--gf-ink); }
[data-testid="stExpander"] summary:hover { color:var(--gf-brand); }

/* ── Progress ───────────────────────────────────────────────────────── */
.stProgress > div > div > div { background:linear-gradient(90deg,var(--gf-brand-2),var(--gf-brand-3)); }
.stProgress > div > div { background:var(--gf-surface-2); border-radius:var(--gf-r-pill); }

/* ── Alerts (soften Streamlit defaults to match the system) ─────────── */
[data-testid="stAlert"] { border-radius:var(--gf-r-lg); border:1px solid var(--gf-border); }

/* ── File uploader ──────────────────────────────────────────────────── */
[data-testid="stFileUploader"] section {
  border:1.5px dashed var(--gf-border-strong); border-radius:var(--gf-r-lg);
  background:var(--gf-surface-2); transition:border-color var(--gf-fast), background var(--gf-fast);
}
[data-testid="stFileUploader"] section:hover { border-color:var(--gf-brand-2); background:var(--gf-brand-soft); }

/* ── Radio group as pill segmented control (used for view toggles) ──── */
[data-testid="stRadio"] [role="radiogroup"] { gap:6px; }

/* ── Scrollbars ─────────────────────────────────────────────────────── */
::-webkit-scrollbar { width:11px; height:11px; }
::-webkit-scrollbar-thumb { background:#c7d0dd; border-radius:99px; border:3px solid var(--gf-bg); }
::-webkit-scrollbar-thumb:hover { background:#aeb9ca; }

/* ── Motion utilities ───────────────────────────────────────────────── */
@keyframes gf-fade { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }
@keyframes gf-shimmer { 0% { background-position:-400px 0; } 100% { background-position:400px 0; } }
@keyframes gf-pulse { 0%,100% { opacity:1; } 50% { opacity:.35; } }
@keyframes gf-spin { to { transform:rotate(360deg); } }
.gf-fade { animation:gf-fade var(--gf-mid) both; }

@media (prefers-reduced-motion:reduce) {
  *, *::before, *::after { animation-duration:.001ms !important; transition-duration:.001ms !important; }
}
</style>"""
    )


# Component-scoped CSS lives with the components module to keep this file focused
# on tokens + the global shell. Imported lazily to avoid a cycle at import time.
def inject() -> None:
    """Inject the full stylesheet (tokens + global + components). Call once/rerun."""
    from app.ui.components import COMPONENT_CSS  # local import avoids cycle

    st.markdown(_global_css(), unsafe_allow_html=True)
    st.markdown(f"<style>{COMPONENT_CSS}</style>", unsafe_allow_html=True)
