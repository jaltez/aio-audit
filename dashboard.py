import html
import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="AI SEO Auditor",
    page_icon="\U0001f50d",
    layout="wide",
    initial_sidebar_state="expanded",
)

DIMENSIONS: list[tuple[str, str]] = [
    ("onpage_seo_score", "On-Page SEO"),
    ("schema_score", "Schema"),
    ("content_score", "Content"),
    ("link_score", "Links"),
    ("performance_score", "Performance"),
    ("readability_score", "Readability"),
    ("security_score", "Security"),
    ("accessibility_score", "Accessibility"),
]

ISSUE_SECTIONS = [
    "onpage_seo",
    "content_analysis",
    "link_analysis",
    "readability",
    "accessibility",
    "security",
]

COLOR_MAP = {
    "complete": "#10b981",
    "partial": "#f59e0b",
    "failed": "#ef4444",
}


def grade_from_score(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def score_color(score: float) -> str:
    if score >= 90:
        return "#10b981"
    if score >= 50:
        return "#f59e0b"
    return "#ef4444"


def compact_url(url: str, max_len: int = 55) -> str:
    if len(url) <= max_len:
        return url
    return f"{url[:max_len - 1]}..."


def style_plotly(fig: go.Figure, *, height: int, margin: Optional[dict[str, int]] = None) -> None:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d4e2f0", family="Space Grotesk, sans-serif"),
        height=height,
        margin=margin or dict(l=10, r=10, t=10, b=10),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.1)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.1)")


def render_hero_gauge(
    *,
    score: float,
    grade: str,
    session_name: str,
    page_count: int,
    failed_count: int,
    high_issues: int,
) -> None:
    ring_color = score_color(score)
    pct = max(0, min(100, score))
    st.markdown(
        f"""
<div class="hero-shell" style="overflow:visible;">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;">
    <div style="flex:1 1 420px;min-width:280px;">
      <div style="font-family:'Sora',sans-serif;font-weight:800;font-size:1.25rem;line-height:1.25;color:#e6f3ff;word-break:break-word;">Session {html.escape(session_name)}</div>
      <div style="margin-top:4px;color:#90a8c0;font-size:.92rem;">Visual command layer for performance, risk, and remediation priority.</div>
      <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:14px;">
        <div style="border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:8px;background:rgba(10,20,31,.62);">
          <div style="font-size:.68rem;letter-spacing:.06em;color:#90a8c0;text-transform:uppercase;">Pages</div>
          <div style="font-family:'Sora',sans-serif;font-size:1.1rem;font-weight:700;color:#e4f2ff;">{page_count}</div>
        </div>
        <div style="border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:8px;background:rgba(10,20,31,.62);">
          <div style="font-size:.68rem;letter-spacing:.06em;color:#90a8c0;text-transform:uppercase;">Failed</div>
          <div style="font-family:'Sora',sans-serif;font-size:1.1rem;font-weight:700;color:#f54f66;">{failed_count}</div>
        </div>
        <div style="border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:8px;background:rgba(10,20,31,.62);">
          <div style="font-size:.68rem;letter-spacing:.06em;color:#90a8c0;text-transform:uppercase;">High Issues</div>
          <div style="font-family:'Sora',sans-serif;font-size:1.1rem;font-weight:700;color:#ffb020;">{high_issues}</div>
        </div>
      </div>
    </div>
    <div style="flex:0 0 auto;width:176px;height:176px;display:grid;place-items:center;">
      <div style="width:176px;height:176px;border-radius:999px;display:grid;place-items:center;background:conic-gradient({ring_color} {pct:.1f}%, rgba(255,255,255,.12) 0);">
        <div style="width:148px;height:148px;border-radius:999px;background:linear-gradient(145deg,#0a1622,#122031);display:grid;place-items:center;text-align:center;">
          <div>
            <div style="font-family:'Sora',sans-serif;font-weight:800;font-size:1.7rem;color:#ecf5ff;">{grade}</div>
            <div style="font-size:.86rem;color:#9bb2c9;">{score:.1f}/100</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_dimension_strip(dimension_means: dict[str, float]) -> None:
    cards: list[str] = []
    for name, value in dimension_means.items():
        width = int(max(0, min(100, round(value))))
        cards.append(
            f"""
<div class="kpi-card">
  <div class="kpi-label">{html.escape(name)}</div>
  <div class="kpi-value" style="color:{score_color(value)}">{value:.1f}</div>
  <div style="height:7px;border-radius:999px;background:rgba(255,255,255,.08);margin-top:8px;overflow:hidden;">
    <div style="height:7px;width:{width}%;border-radius:999px;background:linear-gradient(90deg,#1fb6ff,#00d2a8);"></div>
  </div>
</div>
"""
        )
    st.markdown(
        f"""
<div class="dimension-grid">
  {''.join(cards)}
</div>
""",
        unsafe_allow_html=True,
    )


st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Space+Grotesk:wght@400;500;700&display=swap');
:root {
    --bg-0: #071019;
    --bg-1: #0b1724;
    --bg-2: #122031;
    --accent-a: #1fb6ff;
    --accent-b: #00d2a8;
    --warn: #ffb020;
    --ok: #17c964;
    --bad: #f54f66;
    --ink: #d4e2f0;
    --muted: #8aa0b8;
}
html, body, [data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 8% 10%, rgba(31, 182, 255, 0.16), transparent 25%),
        radial-gradient(circle at 95% 6%, rgba(0, 210, 168, 0.14), transparent 25%),
        radial-gradient(circle at 70% 88%, rgba(255, 176, 32, 0.1), transparent 28%),
        linear-gradient(160deg, var(--bg-0), var(--bg-1) 40%, var(--bg-2));
}
[data-testid="stHeader"] {
    background: rgba(5, 12, 18, 0.25);
}
[data-testid="stAppViewContainer"] * {
    font-family: "Space Grotesk", sans-serif;
}
h1, h2, h3, .hero-title, .signal-value, .kpi-value {
    font-family: "Sora", sans-serif !important;
    letter-spacing: 0.01em;
}
[data-testid="stSidebar"] > div {
    background: linear-gradient(180deg, rgba(7, 16, 25, 0.95), rgba(11, 23, 36, 0.98));
    border-right: 1px solid rgba(255, 255, 255, 0.08);
}
[data-testid="stSidebar"] * {
    color: #d6e6f5;
}
.page-title {
    font-size: 2rem;
    font-weight: 800;
    margin-bottom: 0.2rem;
}
.page-subtitle {
    color: var(--muted);
    margin-bottom: 0.7rem;
}
.hero-shell {
    border: 1px solid rgba(31, 182, 255, 0.32);
    border-radius: 20px;
    background:
        radial-gradient(circle at 8% 12%, rgba(31, 182, 255, 0.26), transparent 32%),
        radial-gradient(circle at 92% 86%, rgba(0, 210, 168, 0.2), transparent 35%),
        linear-gradient(145deg, #0a1622, #122031);
    padding: 18px 20px;
    margin-bottom: 12px;
    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
}
.hero-title {
    font-size: 1.3rem;
    font-weight: 800;
    letter-spacing: 0.02em;
}
.hero-sub {
    color: var(--muted);
    font-size: 0.9rem;
}
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
    margin-top: 12px;
}
.kpi-card {
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 10px 12px;
    background: rgba(10, 20, 31, 0.68);
    backdrop-filter: blur(8px);
    transition: all .25s ease;
}
.kpi-card:hover {
    transform: translateY(-2px);
    border-color: rgba(31, 182, 255, 0.35);
}
.kpi-label {
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    opacity: 0.65;
}
.kpi-value {
    font-size: 1.25rem;
    font-weight: 700;
    margin-top: 2px;
}
.signal-card {
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 12px;
    background: rgba(10, 20, 31, 0.58);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    min-height: 132px;
    height: 100%;
}
.signal-label {
    font-size: 0.78rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.signal-value {
    font-size: 1.45rem;
    font-weight: 800;
}
.issue-line {
    border-left: 3px solid var(--warn);
    padding: 8px 10px;
    margin-bottom: 8px;
    background: rgba(255, 176, 32, 0.08);
    border-radius: 8px;
}
.issue-high { border-left-color: var(--bad); background: rgba(245, 79, 102, 0.12); }
.issue-medium { border-left-color: var(--warn); }
.issue-low { border-left-color: var(--accent-a); background: rgba(31, 182, 255, 0.1); }
.page-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
}
.section-title {
    margin-top: .5rem;
    margin-bottom: .25rem;
    font-size: 1.25rem;
    font-weight: 800;
}
.section-sub {
    color: var(--muted);
    margin-bottom: .5rem;
}
.dimension-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
    margin-top: 14px;
    margin-bottom: 16px;
}
.lane-card {
    border: 1px solid rgba(255,255,255,.1);
    border-radius: 14px;
    background: rgba(11, 22, 34, .7);
    padding: 10px 12px;
    margin-bottom: 8px;
}
.lane-url {
    font-weight: 700;
    font-size: .9rem;
    margin-bottom: 6px;
    color: #d9e8f7;
}
.lane-row {
    display: flex;
    justify-content: space-between;
    font-size: .8rem;
    color: var(--muted);
}
[data-testid="stMetricValue"] {
    color: #d9e8f7;
}
[data-testid="stDataFrame"] {
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 12px;
    overflow: hidden;
}
@media (max-width: 900px) {
    .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .dimension-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
""",
    unsafe_allow_html=True,
)

project_root = Path(__file__).resolve().parent
reports_dir = project_root / "reports"
legacy_reports_dir = project_root / "ai_seo_auditor" / "reports"
if not reports_dir.exists() and legacy_reports_dir.exists():
    reports_dir = legacy_reports_dir

if not reports_dir.exists():
    st.error("No 'reports' directory found. Run the crawler first.")
    st.stop()


@st.cache_data(ttl=300)
def load_data(folder_path: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for file_path in Path(folder_path).glob("*.json"):
        if file_path.name.startswith("_"):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                report: dict[str, Any] = json.load(f)

            if "semantic_analysis" in report and "onpage_seo" not in report:
                report["onpage_seo"] = report.pop("semantic_analysis")

            perf = report.get("performance", {})
            if "response_time_ms" in perf and "ttfb_ms" not in perf:
                perf["ttfb_ms"] = perf["response_time_ms"]
                perf.setdefault("fcp_ms", None)
                perf.setdefault("dom_content_loaded_ms", None)

            report.setdefault("audit_status", "complete")

            row = {
                "url": report.get("url", file_path.stem),
                "audit_status": report.get("audit_status", "complete"),
                "onpage_seo_score": report.get("onpage_seo", {}).get("score", 0),
                "schema_score": report.get("schema_analysis", {}).get("score", 0),
                "content_score": report.get("content_analysis", {}).get("score", 0),
                "link_score": report.get("link_analysis", {}).get("score", 0),
                "performance_score": report.get("performance", {}).get("score", 0),
                "readability_score": report.get("readability", {}).get("score", 0),
                "security_score": report.get("security", {}).get("score", 0),
                "accessibility_score": report.get("accessibility", {}).get("score", 0),
                "canonical_score": report.get("canonical_analysis", {}).get("score", 0),
                "overall_score": report.get("overall_score", 0),
                "letter_grade": report.get("letter_grade", "F"),
                "issues_count": sum(
                    len(report.get(section, {}).get("issues", []))
                    for section in ISSUE_SECTIONS
                ),
                "raw_data": report,
            }
            rows.append(row)
        except Exception as exc:
            st.warning(f"Failed to parse {file_path.name}: {exc}")

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["risk_index"] = (
        ((100 - df["overall_score"]).clip(0, 100) * 0.65)
        + (df["issues_count"].clip(0, 20) * 5 * 0.35)
    ).round(1)
    return df


@st.cache_data(ttl=300)
def load_site_summary(folder_path: str) -> Optional[dict[str, Any]]:
    path = Path(folder_path) / "_site_summary.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def collect_issues(df: pd.DataFrame) -> pd.DataFrame:
    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        page = row["raw_data"]
        for section in ISSUE_SECTIONS:
            for issue in page.get(section, {}).get("issues", []):
                items.append(
                    {
                        "url": row["url"],
                        "section": section,
                        "severity": issue.get("severity", "medium").lower(),
                        "description": issue.get("description", ""),
                        "suggested_fix": issue.get("suggested_fix", ""),
                    }
                )
    return pd.DataFrame(items)


report_folders = sorted(
    [f for f in reports_dir.iterdir() if f.is_dir()],
    key=lambda x: x.stat().st_mtime,
    reverse=True,
)
report_folders = [f for f in report_folders if any(not p.name.startswith("_") for p in f.glob("*.json"))]

if not report_folders:
    st.warning("No report sessions found in reports/.")
    st.stop()

st.sidebar.header("Session")
selected_folder_name = st.sidebar.selectbox("Report", [f.name for f in report_folders])
selected_folder_path = reports_dir / selected_folder_name

all_df = load_data(str(selected_folder_path))
site_summary = load_site_summary(str(selected_folder_path))
if all_df.empty:
    st.info("No page reports were found in this session.")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.header("Filters")
url_query = st.sidebar.text_input("URL contains", "")
score_range = st.sidebar.slider("Overall score", 0, 100, (0, 100))
statuses = sorted(all_df["audit_status"].unique().tolist())
status_filter = st.sidebar.multiselect("Audit status", statuses, default=statuses)
max_issues = int(all_df["issues_count"].max()) if not all_df.empty else 0
min_issues = st.sidebar.slider("Minimum issues", 0, max_issues, 0)

filtered_df = all_df.copy()
if url_query:
    filtered_df = filtered_df[filtered_df["url"].str.contains(url_query, case=False, na=False)]
filtered_df = filtered_df[
    (filtered_df["overall_score"] >= score_range[0])
    & (filtered_df["overall_score"] <= score_range[1])
    & (filtered_df["audit_status"].isin(status_filter))
    & (filtered_df["issues_count"] >= min_issues)
]

if filtered_df.empty:
    st.warning("No pages match the active filters.")
    st.stop()

scored_df = filtered_df[filtered_df["audit_status"] != "failed"]
if scored_df.empty:
    scored_df = filtered_df

st.sidebar.markdown("---")
st.sidebar.header("Export")
export_cols = [
    "url",
    "audit_status",
    "overall_score",
    "letter_grade",
    "risk_index",
    "issues_count",
] + [k for k, _ in DIMENSIONS]
csv_data = filtered_df[export_cols].to_csv(index=False)
st.sidebar.download_button(
    "Download CSV",
    data=csv_data,
    file_name=f"seo_audit_{selected_folder_name}.csv",
    mime="text/csv",
)
st.sidebar.download_button(
    "Download Full JSON",
    data=json.dumps([r["raw_data"] for _, r in filtered_df.iterrows()], indent=2, default=str),
    file_name=f"seo_audit_{selected_folder_name}.json",
    mime="application/json",
)

score = round(float(scored_df["overall_score"].mean()), 1)
grade = grade_from_score(score)
page_count = len(filtered_df)
failed_count = int((filtered_df["audit_status"] == "failed").sum())
partial_count = int((filtered_df["audit_status"] == "partial").sum())

dimension_means = {label: round(float(scored_df[key].mean()), 1) for key, label in DIMENSIONS}
strongest_dim = max(dimension_means.items(), key=lambda x: x[1])
weakest_dim = min(dimension_means.items(), key=lambda x: x[1])

issue_df = collect_issues(filtered_df)
high_issues = int((issue_df["severity"] == "high").sum()) if not issue_df.empty else 0

st.markdown('<div class="page-title">AI SEO Audit Command Center</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="page-subtitle">A visual operations board for diagnosing page quality and fixing impact first.</div>',
    unsafe_allow_html=True,
)
render_hero_gauge(
    score=score,
    grade=grade,
    session_name=selected_folder_name,
    page_count=page_count,
    failed_count=failed_count,
    high_issues=high_issues,
)

render_dimension_strip(dimension_means)
st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

sig1, sig2, sig3 = st.columns(3)
with sig1:
    st.markdown(
        f'<div class="signal-card"><div class="signal-label">Strongest Dimension</div>'
        f'<div class="signal-value" style="color:{score_color(strongest_dim[1])}">{strongest_dim[0]}</div>'
        f'<div style="font-size:.95rem;color:#dbe9f7;">{strongest_dim[1]:.1f}</div></div>',
        unsafe_allow_html=True,
    )
with sig2:
    st.markdown(
        f'<div class="signal-card"><div class="signal-label">Weakest Dimension</div>'
        f'<div class="signal-value" style="color:{score_color(weakest_dim[1])}">{weakest_dim[0]}</div>'
        f'<div style="font-size:.95rem;color:#dbe9f7;">{weakest_dim[1]:.1f}</div></div>',
        unsafe_allow_html=True,
    )
with sig3:
    median_score = round(float(scored_df["overall_score"].median()), 1)
    st.markdown(
        f'<div class="signal-card"><div class="signal-label">Median Overall Score</div>'
        f'<div class="signal-value" style="color:{score_color(median_score)}">{median_score}</div>'
        f'<div style="opacity:.72;font-size:.8rem;">{partial_count} partial audits</div></div>',
        unsafe_allow_html=True,
    )

left, right = st.columns([1.2, 1])
with left:
    st.markdown('<div class="section-title">Risk Map</div><div class="section-sub">Bubble size indicates computed risk index; prioritize bottom-left to upper-right drift.</div>', unsafe_allow_html=True)
    fig_risk = px.scatter(
        filtered_df,
        x="overall_score",
        y="issues_count",
        size=filtered_df["risk_index"].clip(lower=8),
        color="audit_status",
        color_discrete_map=COLOR_MAP,
        hover_name="url",
        hover_data={
            "overall_score": ":.1f",
            "risk_index": True,
            "issues_count": True,
            "audit_status": True,
        },
    )
    fig_risk.add_vline(x=70, line_dash="dot", line_color="#94a3b8")
    fig_risk.add_hline(y=5, line_dash="dot", line_color="#94a3b8")
    style_plotly(fig_risk, height=420, margin=dict(l=12, r=12, t=16, b=10))
    fig_risk.update_layout(legend_title=None, xaxis_title="Overall score", yaxis_title="Issue count")
    st.plotly_chart(fig_risk, use_container_width=True)

with right:
    st.markdown('<div class="section-title">Dimension Heatmap</div><div class="section-sub">Rows are highest-risk pages; colors show score strength by dimension.</div>', unsafe_allow_html=True)
    heat = filtered_df.sort_values("risk_index", ascending=False).copy()
    heat = heat.head(12) if len(heat) > 12 else heat
    page_ids = [f"P{i+1:02d}" for i in range(len(heat))]
    heat_mat = heat[[k for k, _ in DIMENSIONS]].copy()
    dim_short_labels = ["On-Page", "Schema", "Content", "Links", "Perf", "Read", "Sec", "A11y"]

    fig_heat = go.Figure(
        data=go.Heatmap(
            z=heat_mat.to_numpy(),
            x=dim_short_labels,
            y=page_ids,
            customdata=heat["url"].to_numpy().reshape(-1, 1),
            colorscale=[(0.0, "#7f1d1d"), (0.5, "#f59e0b"), (1.0, "#17c964")],
            zmin=0,
            zmax=100,
            xgap=2,
            ygap=2,
            colorbar=dict(title="Score", len=0.82),
            hovertemplate="<b>%{y}</b> %{customdata[0]}<br>%{x}: %{z:.0f}<extra></extra>",
        )
    )
    fig_heat.update_traces(text=heat_mat.round(0).to_numpy(), texttemplate="%{text:.0f}", textfont=dict(size=10))
    style_plotly(fig_heat, height=500)
    fig_heat.update_layout(
        xaxis_title=None,
        yaxis_title=None,
        xaxis=dict(side="top", tickangle=0),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_heat, use_container_width=True)
    with st.expander("Page ID Legend"):
        legend_df = pd.DataFrame({"Page ID": page_ids, "URL": [compact_url(u, 90) for u in heat["url"]]})
        st.dataframe(legend_df, use_container_width=True, hide_index=True)

st.markdown('<div class="section-title">Score Skyline</div><div class="section-sub">Compressed cityscape view of page quality distribution and risk.</div>', unsafe_allow_html=True)
sky_df = filtered_df.sort_values("overall_score", ascending=True).head(50)
sky_records = [
    {
        "url": compact_url(r.url, 56),
        "score": float(r.overall_score),
        "risk": float(r.risk_index),
    }
    for r in sky_df.itertuples(index=False)
]
skyline_height = 300 if len(sky_records) > 20 else 270
components.html(
    f"""
<div id="skyline-root" style="width:100%;height:{skyline_height - 10}px;background:linear-gradient(160deg,#0a1622,#122031);border:1px solid rgba(255,255,255,.12);border-radius:14px;position:relative;overflow:hidden;"></div>
<script>
const data = {json.dumps(sky_records)};
const root = document.getElementById("skyline-root");
const w = root.clientWidth;
const h = root.clientHeight;
const max = 100;
const pad = 18;
const bw = Math.max(6, (w - pad * 2) / Math.max(data.length, 1) - 3);
const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
svg.setAttribute("width", w);
svg.setAttribute("height", h);
svg.setAttribute("viewBox", `0 0 ${{w}} ${{h}}`);
svg.innerHTML = `<defs><filter id="glow"><feGaussianBlur stdDeviation="2.2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`;

for (let g = 0; g < 4; g++) {{
  const yy = 24 + g * ((h - 46) / 4);
  const gl = document.createElementNS("http://www.w3.org/2000/svg", "line");
  gl.setAttribute("x1", pad);
  gl.setAttribute("x2", w - pad);
  gl.setAttribute("y1", yy);
  gl.setAttribute("y2", yy);
  gl.setAttribute("stroke", "rgba(255,255,255,.08)");
  gl.setAttribute("stroke-dasharray", "3 4");
  svg.appendChild(gl);
}}

for (let i = 0; i < data.length; i++) {{
  const d = data[i];
  const x = pad + i * (bw + 3);
  const bh = ((h - 44) * d.score) / max;
  const y = h - 20 - bh;
  const c = d.score >= 90 ? "#10b981" : d.score >= 50 ? "#f59e0b" : "#ef4444";

  const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  bar.setAttribute("x", x);
  bar.setAttribute("y", y);
  bar.setAttribute("width", bw);
  bar.setAttribute("height", bh);
  bar.setAttribute("rx", 2);
  bar.setAttribute("fill", c);
  bar.setAttribute("opacity", "0.92");
  bar.setAttribute("filter", "url(#glow)");
  bar.style.transition = "all .18s ease";
  bar.setAttribute("data-tip", `${{d.url}} | score ${{d.score.toFixed(1)}} | risk ${{d.risk.toFixed(1)}}`);
  svg.appendChild(bar);
}}

const axis = document.createElementNS("http://www.w3.org/2000/svg", "line");
axis.setAttribute("x1", pad);
axis.setAttribute("x2", w - pad);
axis.setAttribute("y1", h - 19);
axis.setAttribute("y2", h - 19);
axis.setAttribute("stroke", "rgba(255,255,255,.35)");
svg.appendChild(axis);

root.appendChild(svg);

const tip = document.createElement("div");
tip.style.position = "absolute";
tip.style.pointerEvents = "none";
tip.style.padding = "6px 8px";
tip.style.fontSize = "12px";
tip.style.background = "rgba(2,6,23,.92)";
tip.style.border = "1px solid rgba(255,255,255,.2)";
tip.style.borderRadius = "8px";
tip.style.display = "none";
root.appendChild(tip);

root.addEventListener("mousemove", (e) => {{
  const t = e.target;
  const msg = t && t.getAttribute && t.getAttribute("data-tip");
  for (const el of svg.querySelectorAll("rect[data-tip]")) {{
    el.setAttribute("opacity", "0.35");
  }}
  if (!msg) {{ tip.style.display = "none"; return; }}
  t.setAttribute("opacity", "1");
  tip.style.display = "block";
  tip.textContent = msg;
  const tw = tip.offsetWidth || 180;
  const th = tip.offsetHeight || 28;
  let x = e.offsetX + 10;
  let y = e.offsetY + 8;
  if (x + tw > w - 8) x = e.offsetX - tw - 10;
  if (y + th > h - 8) y = e.offsetY - th - 10;
  x = Math.max(6, Math.min(x, w - tw - 6));
  y = Math.max(6, Math.min(y, h - th - 6));
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}});
root.addEventListener("mouseleave", () => {{
  tip.style.display = "none";
  for (const el of svg.querySelectorAll("rect[data-tip]")) {{
    el.setAttribute("opacity", "0.92");
  }}
}});
</script>
""",
    height=skyline_height,
)

st.markdown('<div class="section-title">Issue Pressure Matrix</div><div class="section-sub">Section-level issue density split by severity.</div>', unsafe_allow_html=True)
if issue_df.empty:
    st.info("No issues in filtered pages.")
else:
    section_names = {
        "onpage_seo": "On-Page SEO",
        "content_analysis": "Content",
        "link_analysis": "Links",
        "readability": "Readability",
        "accessibility": "Accessibility",
        "security": "Security",
    }
    agg = (
        issue_df.groupby(["section", "severity"]).size().reset_index(name="count")
    )
    agg["section"] = agg["section"].map(section_names)
    agg["severity"] = pd.Categorical(agg["severity"], categories=["high", "medium", "low"], ordered=True)
    agg = agg.sort_values(["section", "severity"])

    fig_issues = px.bar(
        agg,
        x="count",
        y="section",
        color="severity",
        orientation="h",
        barmode="stack",
        category_orders={"severity": ["high", "medium", "low"]},
        color_discrete_map={"high": "#ef4444", "medium": "#f59e0b", "low": "#06b6d4"},
    )
    style_plotly(fig_issues, height=320, margin=dict(l=10, r=10, t=12, b=8))
    fig_issues.update_layout(legend_title=None, xaxis_title="Issue count", yaxis_title=None)
    st.plotly_chart(fig_issues, use_container_width=True)

st.markdown('<div class="section-title">Action Queue</div><div class="section-sub">Start with these pages first based on highest risk index.</div>', unsafe_allow_html=True)
queue_df = filtered_df.sort_values(["risk_index", "issues_count"], ascending=[False, False]).head(6)
q1, q2, q3 = st.columns(3)
queue_cols = [q1, q2, q3]
for i, row in enumerate(queue_df.itertuples(index=False)):
    with queue_cols[i % 3]:
        st.markdown(
            f"""
<div class="lane-card">
  <div class="lane-url">{html.escape(compact_url(str(row.url), 62))}</div>
  <div class="lane-row"><span>Risk Index</span><strong style="color:{score_color(100 - float(row.risk_index))};">{float(row.risk_index):.1f}</strong></div>
  <div class="lane-row"><span>Overall Score</span><strong style="color:{score_color(float(row.overall_score))};">{float(row.overall_score):.1f}</strong></div>
  <div class="lane-row"><span>Issues</span><strong>{int(row.issues_count)}</strong></div>
  <div class="lane-row"><span>Status</span><strong style="color:{COLOR_MAP.get(str(row.audit_status), '#94a3b8')};">{str(row.audit_status).upper()}</strong></div>
</div>
""",
            unsafe_allow_html=True,
        )

st.markdown("---")
st.markdown('<div class="section-title">Page Cockpit</div><div class="section-sub">Single-page diagnostic panel with prioritized fixes and core signals.</div>', unsafe_allow_html=True)
selected_url = st.selectbox("Focus page", filtered_df.sort_values("risk_index", ascending=False)["url"])
selected_row = filtered_df[filtered_df["url"] == selected_url].iloc[0]
page = selected_row["raw_data"]

cockpit_left, cockpit_right = st.columns([1.2, 1])
with cockpit_left:
    page_scores = {
        "On-Page SEO": page.get("onpage_seo", {}).get("score", 0),
        "Schema": page.get("schema_analysis", {}).get("score", 0),
        "Content": page.get("content_analysis", {}).get("score", 0),
        "Links": page.get("link_analysis", {}).get("score", 0),
        "Performance": page.get("performance", {}).get("score", 0),
        "Readability": page.get("readability", {}).get("score", 0),
        "Security": page.get("security", {}).get("score", 0),
        "Accessibility": page.get("accessibility", {}).get("score", 0),
    }
    fig_page = go.Figure(
        go.Barpolar(
            r=list(page_scores.values()),
            theta=list(page_scores.keys()),
            marker_color=[score_color(v) for v in page_scores.values()],
            marker_line_color="#0b1220",
            marker_line_width=1,
            opacity=0.95,
        )
    )
    fig_page.update_layout(
        margin=dict(l=14, r=14, t=20, b=14),
        polar=dict(radialaxis=dict(range=[0, 100], showticklabels=True, ticks="")),
        showlegend=False,
    )
    style_plotly(fig_page, height=420, margin=dict(l=14, r=14, t=20, b=14))
    st.plotly_chart(fig_page, use_container_width=True)

with cockpit_right:
    page_grade = page.get("letter_grade", grade_from_score(float(selected_row["overall_score"])))
    page_status = page.get("audit_status", "complete")
    st.markdown(
        f"""
<div class="signal-card">
  <div class="signal-label">Current Page</div>
  <div style="font-weight:700;font-size:1.05rem;margin-bottom:8px;">{html.escape(compact_url(selected_url, 70))}</div>
  <div class="kpi-grid" style="grid-template-columns:repeat(2,minmax(0,1fr));margin-top:0;">
    <div class="kpi-card"><div class="kpi-label">Grade</div><div class="kpi-value" style="color:{score_color(float(selected_row['overall_score']))}">{page_grade}</div></div>
    <div class="kpi-card"><div class="kpi-label">Overall</div><div class="kpi-value">{float(selected_row['overall_score']):.1f}</div></div>
    <div class="kpi-card"><div class="kpi-label">Risk Index</div><div class="kpi-value">{float(selected_row['risk_index']):.1f}</div></div>
    <div class="kpi-card"><div class="kpi-label">Status</div><div class="kpi-value" style="color:{COLOR_MAP.get(page_status, '#94a3b8')}">{str(page_status).upper()}</div></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

page_tabs = st.tabs(["Priority Fixes", "Core Signals", "Raw JSON"])

with page_tabs[0]:
    page_issue_rows: list[dict[str, str]] = []
    for section in ISSUE_SECTIONS:
        for issue in page.get(section, {}).get("issues", []):
            sev = issue.get("severity", "medium").lower()
            page_issue_rows.append(
                {
                    "severity": sev,
                    "description": issue.get("description", ""),
                    "fix": issue.get("suggested_fix", ""),
                    "section": section,
                }
            )

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    page_issue_rows.sort(key=lambda x: severity_rank.get(x["severity"], 3))

    if not page_issue_rows:
        st.success("No issues found for this page.")
    else:
        for issue in page_issue_rows[:12]:
            sev = issue["severity"]
            safe_section = html.escape(issue["section"])
            safe_description = html.escape(issue["description"])
            safe_fix = html.escape(issue["fix"])
            st.markdown(
                f"""
<div class="issue-line issue-{sev}">
  <div><span class="page-pill" style="background:{'#7f1d1d' if sev == 'high' else '#78350f' if sev == 'medium' else '#164e63'};color:#fff;">{sev.upper()}</span>
  <span style="opacity:.72;font-size:.8rem;"> {safe_section}</span></div>
  <div style="margin-top:4px;font-weight:600;">{safe_description}</div>
  <div style="margin-top:2px;opacity:.82;">{safe_fix}</div>
</div>
""",
                unsafe_allow_html=True,
            )

with page_tabs[1]:
    perf = page.get("performance", {})
    read = page.get("readability", {})
    links = page.get("link_analysis", {})
    a11y = page.get("accessibility", {})

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("TTFB", f"{perf.get('ttfb_ms', 0)} ms")
    fcp = perf.get("fcp_ms")
    c2.metric("FCP", "N/A" if fcp is None else f"{fcp} ms")
    c3.metric("Word Count", read.get("word_count", 0))
    c4.metric("Internal Links", links.get("internal_links", 0))
    c5.metric("External Links", links.get("external_links", 0))
    c6.metric("ARIA Landmarks", a11y.get("aria_landmark_count", 0))

    st.caption("Dimension scores")
    for label, value in page_scores.items():
        st.write(f"{label}")
        st.progress(max(0.0, min(1.0, value / 100.0)))

with page_tabs[2]:
    st.json(page)

st.markdown("---")
st.markdown('<div class="section-title">Filtered Pages</div><div class="section-sub">Sortable raw table for precise triage and export.</div>', unsafe_allow_html=True)
view_cols = [
    "url",
    "audit_status",
    "overall_score",
    "letter_grade",
    "risk_index",
    "issues_count",
] + [k for k, _ in DIMENSIONS]
st.dataframe(
    filtered_df.sort_values(["risk_index", "overall_score"], ascending=[False, True])[view_cols],
    use_container_width=True,
    hide_index=True,
)

if site_summary:
    st.caption(
        f"Site summary file loaded ({site_summary.get('pages_audited', 'n/a')} pages, grade {site_summary.get('overall_grade', 'n/a')})."
    )
