import json
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI SEO Auditor",
    page_icon="\U0001f50d",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Colour constants (Python-side, for Plotly + inline HTML only).
# All native Streamlit widgets are themed by .streamlit/config.toml.
# ---------------------------------------------------------------------------
C_ACCENT       = "#3b82f6"
C_ACCENT_FILL  = "rgba(59,130,246,0.15)"
C_GREEN_FILL   = "rgba(34,197,94,0.15)"
C_GOOD         = "#22c55e"
C_OK           = "#eab308"
C_BAD          = "#ef4444"

# ---------------------------------------------------------------------------
# Minimal CSS -- custom HTML components only (grade badge, score cards,
# severity pills, checklist).  Do NOT override native widgets here;
# .streamlit/config.toml handles that.
# ---------------------------------------------------------------------------
st.markdown("""
<style>
.grade-badge {
    display: inline-flex; align-items: center; justify-content: center;
    width: 120px; height: 120px; border-radius: 50%;
    font-size: 3.2rem; font-weight: 800; color: #fff;
    box-shadow: 0 0 30px rgba(0,0,0,0.4);
    margin: 0 auto;
}
.grade-A { background: linear-gradient(135deg, #22c55e, #16a34a); }
.grade-B { background: linear-gradient(135deg, #3b82f6, #2563eb); }
.grade-C { background: linear-gradient(135deg, #eab308, #ca8a04); }
.grade-D { background: linear-gradient(135deg, #f97316, #ea580c); }
.grade-F { background: linear-gradient(135deg, #ef4444, #dc2626); }

.score-card {
    background: var(--secondary-background-color);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 16px 12px; text-align: center; margin-bottom: 8px;
}
.score-card .label {
    font-size: 0.75rem; opacity: 0.55;
    text-transform: uppercase; letter-spacing: 0.05em;
}
.score-card .value { font-size: 1.6rem; font-weight: 700; margin-top: 4px; }
.score-good { color: #22c55e; }
.score-ok   { color: #eab308; }
.score-bad  { color: #ef4444; }

.sev-high   { background: #dc2626; color: #fff; padding: 2px 10px; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }
.sev-medium { background: #ca8a04; color: #fff; padding: 2px 10px; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }
.sev-low    { background: #2563eb; color: #fff; padding: 2px 10px; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }

.check-pass { color: #22c55e; font-weight: 600; }
.check-fail { color: #ef4444; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------
st.markdown("# \U0001f50d AI SEO Auditor")

# ---------------------------------------------------------------------------
# Sidebar -- report selection & filters
# ---------------------------------------------------------------------------
st.sidebar.header("Report")

project_root = Path(__file__).resolve().parent
reports_dir = project_root / "reports"
legacy_reports_dir = project_root / "ai_seo_auditor" / "reports"

if not reports_dir.exists() and legacy_reports_dir.exists():
    reports_dir = legacy_reports_dir

if not reports_dir.exists():
    st.error("No 'reports' directory found. Run the crawler first!")
    st.stop()

report_folders = sorted(
    [f for f in reports_dir.iterdir() if f.is_dir()],
    key=lambda x: x.stat().st_mtime,
    reverse=True,
)


def _page_report_count(folder: Path) -> int:
    return sum(1 for p in folder.glob("*.json") if not p.name.startswith("_"))


non_empty_report_folders = [f for f in report_folders if _page_report_count(f) > 0]

if non_empty_report_folders:
    report_folders = non_empty_report_folders

if not report_folders:
    st.warning("No reports found in the **reports** directory.")
    st.stop()

selected_folder_name = st.sidebar.selectbox(
    "Session:", [f.name for f in report_folders]
)
selected_folder_path = reports_dir / selected_folder_name

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_DIMENSIONS = [
    "onpage_seo_score", "schema_score", "content_score",
    "link_score", "performance_score", "readability_score",
    "security_score", "accessibility_score",
]
DIM_LABELS = {
    "onpage_seo_score": "On-Page SEO",
    "schema_score": "Schema",
    "content_score": "Content",
    "link_score": "Links",
    "performance_score": "Performance",
    "readability_score": "Readability",
    "security_score": "Security",
    "accessibility_score": "Accessibility",
}


def _score_color_class(v: float) -> str:
    """Lighthouse-aligned thresholds: ≥90 green, 50-89 orange, <50 red."""
    if v >= 90:
        return "score-good"
    if v >= 50:
        return "score-ok"
    return "score-bad"


def _score_color(v: float) -> str:
    """Lighthouse-aligned thresholds for Plotly colors."""
    if v >= 90:
        return C_GOOD
    if v >= 50:
        return C_OK
    return C_BAD


def _sev_pill(sev: str) -> str:
    return f'<span class="sev-{sev}">{sev.upper()}</span>'


def _plotly_layout(**overrides) -> dict:
    """Common Plotly layout kwargs -- transparent bg + plotly_dark template."""
    base = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    base.update(overrides)
    return base


_REQUIRED_KEYS = {"url", "onpage_seo", "schema_analysis", "content_analysis"}


@st.cache_data(ttl=300)
def load_data(folder_path: str) -> pd.DataFrame:
    data: list[dict[str, Any]] = []
    for file_path in Path(folder_path).glob("*.json"):
        if file_path.name.startswith("_"):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                report: dict = json.load(f)

            # --- Backward-compat: migrate old-format reports ------
            if "semantic_analysis" in report and "onpage_seo" not in report:
                report["onpage_seo"] = report.pop("semantic_analysis")
            perf = report.get("performance", {})
            if "response_time_ms" in perf and "ttfb_ms" not in perf:
                perf["ttfb_ms"] = perf["response_time_ms"]
                perf.setdefault("fcp_ms", None)
                perf.setdefault("dom_content_loaded_ms", None)
            report.setdefault("audit_status", "complete")
            # -------------------------------------------------------

            missing = _REQUIRED_KEYS - report.keys()
            if missing:
                st.warning(f"\u26a0\ufe0f {file_path.name} is missing keys: {missing}")

            row: dict[str, Any] = {
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
                "answers_user_intent": report.get("content_analysis", {}).get("answers_user_intent", False),
                "issues_count": sum(
                    len(report.get(k, {}).get("issues", []))
                    for k in ("onpage_seo", "content_analysis", "link_analysis", "readability", "accessibility")
                ),
                "raw_data": report,
            }
            data.append(row)
        except Exception as e:
            st.error(f"Error reading {file_path.name}: {e}")

    return pd.DataFrame(data) if data else pd.DataFrame()


@st.cache_data(ttl=300)
def load_site_summary(folder_path: str) -> Optional[dict]:
    summary_path = Path(folder_path) / "_site_summary.json"
    if summary_path.exists():
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


df = load_data(str(selected_folder_path))
site_summary = load_site_summary(str(selected_folder_path))

if df.empty:
    st.info("No JSON reports found in this folder.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar -- filters
# ---------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.header("Filters")

url_search = st.sidebar.text_input("\U0001f50e Search URL", "")
score_range = st.sidebar.slider("Overall Score Range", 0, 100, (0, 100))
severity_filter = st.sidebar.multiselect(
    "Issue Severity",
    ["high", "medium", "low"],
    default=["high", "medium", "low"],
)

# Apply filters
filtered_df = df.copy()
if url_search:
    filtered_df = filtered_df[filtered_df["url"].str.contains(url_search, case=False, na=False)]
filtered_df = filtered_df[
    (filtered_df["overall_score"] >= score_range[0])
    & (filtered_df["overall_score"] <= score_range[1])
]

# ---------------------------------------------------------------------------
# Sidebar -- CSV export
# ---------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.header("Export")

export_cols = ["url", "overall_score", "letter_grade"] + ALL_DIMENSIONS + ["canonical_score", "issues_count"]
csv_data = filtered_df[[c for c in export_cols if c in filtered_df.columns]].to_csv(index=False)
st.sidebar.download_button(
    label="\U0001f4e5 Download CSV",
    data=csv_data,
    file_name=f"seo_audit_{selected_folder_name}.csv",
    mime="text/csv",
)

# Full JSON export
all_reports = [row["raw_data"] for _, row in filtered_df.iterrows()]
json_export = json.dumps(all_reports, indent=2, default=str)
st.sidebar.download_button(
    label="\U0001f4e5 Download Full JSON",
    data=json_export,
    file_name=f"seo_audit_{selected_folder_name}.json",
    mime="application/json",
)

# =========================================================================
# SECTION 1 -- HERO: Overall Site Grade
# =========================================================================

if site_summary:
    overall_grade = site_summary.get("overall_grade", "F")
    overall_score_val = site_summary.get("overall_score", 0)
    dim_avgs = site_summary.get("dimension_averages", {})
else:
    overall_score_val = round(filtered_df["overall_score"].mean(), 1) if len(filtered_df) else 0
    overall_grade = (
        "A" if overall_score_val >= 90 else
        "B" if overall_score_val >= 80 else
        "C" if overall_score_val >= 70 else
        "D" if overall_score_val >= 60 else "F"
    )
    dim_avgs = {
        DIM_LABELS.get(c, c): round(filtered_df[c].mean(), 1)
        for c in ALL_DIMENSIONS if c in filtered_df.columns
    }

# Grade badge + overall score
hero_left, hero_right = st.columns([1, 3])
with hero_left:
    st.markdown(
        f'<div style="text-align:center; padding-top:10px;">'
        f'<div class="grade-badge grade-{overall_grade}">{overall_grade}</div>'
        f'<p style="opacity:0.55; margin-top:8px;">Overall Score: <b>{overall_score_val}</b>/100</p>'
        f'<p style="opacity:0.55;">{len(filtered_df)} pages audited</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

with hero_right:
    # Radar chart -- site-wide dimension averages
    dim_names_ordered = ["On-Page SEO", "Schema", "Content", "Links", "Performance", "Readability", "Security", "Accessibility"]
    dim_map = {
        "On-Page SEO": "onpage_seo", "Schema": "schema_analysis",
        "Content": "content_analysis", "Links": "link_analysis",
        "Performance": "performance", "Readability": "readability",
        "Security": "security", "Accessibility": "accessibility",
    }
    radar_values = [dim_avgs.get(n, dim_avgs.get(dim_map.get(n, ""), 0)) for n in dim_names_ordered]
    radar_values_closed = radar_values + [radar_values[0]]
    theta = dim_names_ordered + [dim_names_ordered[0]]

    fig_radar = go.Figure(data=go.Scatterpolar(
        r=radar_values_closed,
        theta=theta,
        fill="toself",
        fillcolor=C_ACCENT_FILL,
        line=dict(color=C_ACCENT, width=2),
        marker=dict(size=6, color=C_ACCENT),
    ))
    fig_radar.update_layout(
        **_plotly_layout(),
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=True, range=[0, 100]),
            angularaxis=dict(),
        ),
        showlegend=False,
        margin=dict(l=60, r=60, t=30, b=30),
        height=320,
    )
    st.plotly_chart(fig_radar, use_container_width=True)

# Dimension score cards row
dim_cols = st.columns(len(dim_names_ordered))
for i, name in enumerate(dim_names_ordered):
    val = radar_values[i]
    cc = _score_color_class(val)
    dim_cols[i].markdown(
        f'<div class="score-card"><div class="label">{name}</div>'
        f'<div class="value {cc}">{val:.0f}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("---")

# =========================================================================
# SECTION 2 -- Score Distributions
# =========================================================================
st.header("\U0001f4ca Score Distributions")
col_box, col_scatter = st.columns(2)

with col_box:
    melt_df = filtered_df[ALL_DIMENSIONS].melt(var_name="Dimension", value_name="Score")
    melt_df["Dimension"] = melt_df["Dimension"].map(DIM_LABELS)
    fig_box = px.box(
        melt_df, x="Dimension", y="Score",
        color="Dimension",
        color_discrete_sequence=px.colors.qualitative.Set2,
        title="Score Spread by Dimension",
    )
    fig_box.update_layout(**_plotly_layout(
        showlegend=False,
        yaxis=dict(range=[0, 105]),
    ))
    st.plotly_chart(fig_box, use_container_width=True)

with col_scatter:
    x_dim = st.selectbox("X-axis", list(DIM_LABELS.values()), index=0, key="scatter_x")
    y_dim = st.selectbox("Y-axis", list(DIM_LABELS.values()), index=2, key="scatter_y")
    inv_labels = {v: k for k, v in DIM_LABELS.items()}
    x_col, y_col = inv_labels[x_dim], inv_labels[y_dim]

    fig_scatter = px.scatter(
        filtered_df, x=x_col, y=y_col,
        size=filtered_df["overall_score"].clip(lower=5),
        color="issues_count",
        hover_data=["url"],
        title=f"{x_dim} vs {y_dim}",
        color_continuous_scale="RdYlGn_r",
        labels={x_col: x_dim, y_col: y_dim},
    )
    fig_scatter.update_layout(**_plotly_layout())
    st.plotly_chart(fig_scatter, use_container_width=True)

st.markdown("---")

# =========================================================================
# SECTION 3 -- Issue Aggregation (site-wide)
# =========================================================================
st.header("\u26a0\ufe0f Top Issues Across All Pages")

if site_summary and site_summary.get("top_issues"):
    top_issues = site_summary["top_issues"]
    issue_rows = []
    for iss in top_issues[:15]:
        issue_rows.append({
            "Severity": iss.get("severity", "medium").upper(),
            "Description": iss.get("description", ""),
            "Count": iss.get("count", 1),
            "Affected Pages": len(iss.get("affected_pages", [])),
        })
    if issue_rows:
        issue_df = pd.DataFrame(issue_rows)

        def style_severity(val: str) -> str:
            colors = {"HIGH": "#dc2626", "MEDIUM": "#ca8a04", "LOW": "#2563eb"}
            bg = colors.get(val, "#333")
            return f"background-color: {bg}; color: white; border-radius: 6px; padding: 2px 8px;"

        st.dataframe(
            issue_df.style.map(style_severity, subset=["Severity"]),
            use_container_width=True,
            hide_index=True,
        )
    # Severity distribution bar
    sev_dist = site_summary.get("severity_distribution", {})
    if any(sev_dist.values()):
        sev_df = pd.DataFrame([
            {"Severity": "High", "Count": sev_dist.get("high", 0)},
            {"Severity": "Medium", "Count": sev_dist.get("medium", 0)},
            {"Severity": "Low", "Count": sev_dist.get("low", 0)},
        ])
        fig_sev = px.bar(
            sev_df, x="Severity", y="Count",
            color="Severity",
            color_discrete_map={"High": "#dc2626", "Medium": "#ca8a04", "Low": "#2563eb"},
            title="Issue Severity Distribution",
        )
        fig_sev.update_layout(**_plotly_layout(showlegend=False, height=280))
        st.plotly_chart(fig_sev, use_container_width=True)
else:
    # Fall back to computing from raw data
    all_issues_list: list[dict] = []
    for _, row in filtered_df.iterrows():
        rd = row["raw_data"]
        for section in ("onpage_seo", "content_analysis", "link_analysis", "readability", "accessibility"):
            for issue in rd.get(section, {}).get("issues", []):
                all_issues_list.append({
                    "Severity": issue.get("severity", "medium").upper(),
                    "Description": issue.get("description", ""),
                    "Page": row["url"],
                })
    if all_issues_list:
        agg = pd.DataFrame(all_issues_list)
        agg_grouped = agg.groupby(["Description", "Severity"]).agg(
            Count=("Page", "count"),
            Pages=("Page", lambda x: x.nunique()),
        ).reset_index().sort_values("Count", ascending=False).head(15)
        st.dataframe(agg_grouped, use_container_width=True, hide_index=True)
    else:
        st.success("No issues found across all pages!")

st.markdown("---")

# =========================================================================
# SECTION 4 -- Detailed Page Table
# =========================================================================
st.header("\U0001f4c4 Page Results")

display_cols = [
    "url", "audit_status", "letter_grade", "overall_score",
    "onpage_seo_score", "schema_score", "content_score",
    "link_score", "performance_score", "readability_score",
    "security_score", "accessibility_score",
    "issues_count",
]

available_display = [c for c in display_cols if c in filtered_df.columns]
styled_df = filtered_df[available_display].copy()

score_cols = [c for c in available_display if c.endswith("_score")]


def color_scores(val: Any) -> str:
    try:
        v = float(val)
    except (ValueError, TypeError):
        return ""
    if v >= 90:
        return f"background-color: rgba(34,197,94,0.2); color: {C_GOOD};"
    if v >= 50:
        return f"background-color: rgba(234,179,8,0.2); color: {C_OK};"
    return f"background-color: rgba(239,68,68,0.2); color: {C_BAD};"


st.dataframe(
    styled_df.style.map(color_scores, subset=score_cols),
    use_container_width=True,
    hide_index=True,
    height=400,
)

st.markdown("---")

# =========================================================================
# SECTION 5 -- Page Drill-down
# =========================================================================
st.header("\U0001f50d Page Drill-down")
selected_url = st.selectbox("Select a page:", filtered_df["url"].unique())

if selected_url:
    page_data: dict = filtered_df[filtered_df["url"] == selected_url].iloc[0]["raw_data"]
    page_overall = page_data.get("overall_score", 0)
    page_grade = page_data.get("letter_grade", "F")

    tabs = st.tabs([
        "Overview",
        "On-Page SEO",
        "Schema",
        "Content & Readability",
        "Links",
        "Performance",
        "Security",
        "Accessibility & Canonical",
    ])

    # ---- Tab 0: Overview ----
    with tabs[0]:
        # Audit status badge
        status = page_data.get("audit_status", "complete")
        status_colors = {"complete": C_GOOD, "partial": C_OK, "failed": C_BAD}
        status_icon = {"complete": "\u2705", "partial": "\u26a0\ufe0f", "failed": "\u274c"}
        st.markdown(
            f'<span style="color:{status_colors.get(status, C_OK)}; font-weight:600;">'
            f'{status_icon.get(status, "")} Audit Status: {status.upper()}</span>',
            unsafe_allow_html=True,
        )

        ov_left, ov_right = st.columns([1, 2])
        with ov_left:
            st.markdown(
                f'<div style="text-align:center; padding:20px 0;">'
                f'<div class="grade-badge grade-{page_grade}">{page_grade}</div>'
                f'<p style="opacity:0.55; margin-top:8px;">Score: <b>{page_overall}</b>/100</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with ov_right:
            page_scores = {
                "On-Page SEO": page_data.get("onpage_seo", {}).get("score", 0),
                "Schema": page_data.get("schema_analysis", {}).get("score", 0),
                "Content": page_data.get("content_analysis", {}).get("score", 0),
                "Links": page_data.get("link_analysis", {}).get("score", 0),
                "Performance": page_data.get("performance", {}).get("score", 0),
                "Readability": page_data.get("readability", {}).get("score", 0),
                "Security": page_data.get("security", {}).get("score", 0),
                "Accessibility": page_data.get("accessibility", {}).get("score", 0),
            }
            r_vals = list(page_scores.values()) + [list(page_scores.values())[0]]
            r_theta = list(page_scores.keys()) + [list(page_scores.keys())[0]]
            fig_pr = go.Figure(data=go.Scatterpolar(
                r=r_vals, theta=r_theta, fill="toself",
                fillcolor=C_GREEN_FILL,
                line=dict(color=C_GOOD, width=2),
            ))
            fig_pr.update_layout(
                **_plotly_layout(),
                polar=dict(
                    bgcolor="rgba(0,0,0,0)",
                    radialaxis=dict(visible=True, range=[0, 100]),
                    angularaxis=dict(),
                ),
                showlegend=False,
                margin=dict(l=60, r=60, t=20, b=20),
                height=300,
            )
            st.plotly_chart(fig_pr, use_container_width=True)

        # Score cards
        ov_dim_cols = st.columns(len(page_scores))
        for i, (name, val) in enumerate(page_scores.items()):
            cc = _score_color_class(val)
            ov_dim_cols[i].markdown(
                f'<div class="score-card"><div class="label">{name}</div>'
                f'<div class="value {cc}">{val}</div></div>',
                unsafe_allow_html=True,
            )

        # Meta tags summary
        st.subheader("Meta Tags")
        meta = page_data.get("meta_tags", {})
        meta_items = {
            "Title": meta.get("title"), "Description": meta.get("description"),
            "Canonical": meta.get("canonical"), "Robots": meta.get("robots"),
            "OG Title": meta.get("og_title"), "OG Description": meta.get("og_description"),
            "OG Image": meta.get("og_image"), "Viewport": meta.get("viewport"),
            "Twitter Card": meta.get("twitter_card"),
        }
        mc1, mc2 = st.columns(2)
        items_list = list(meta_items.items())
        for label, value in items_list[:5]:
            mc1.markdown(f"**{label}:** {value or '_not set_'}")
        for label, value in items_list[5:]:
            mc2.markdown(f"**{label}:** {value or '_not set_'}")

        # Image stats
        st.subheader("Image Stats")
        img = page_data.get("image_stats", {})
        ic1, ic2, ic3 = st.columns(3)
        ic1.metric("Total Images", img.get("total_images", 0))
        ic2.metric("Missing Alt", img.get("missing_alt", 0))
        ic3.metric("Empty Alt", img.get("empty_alt", 0))

    # ---- Tab 1: On-Page SEO Checklist ----
    with tabs[1]:
        ops = page_data.get("onpage_seo", {})
        ops_score = ops.get("score", 0)
        st.subheader(f"On-Page SEO -- {ops_score}/100")
        st.progress(max(0.0, min(1.0, ops_score / 100)))

        st.caption("Deterministic checklist — fully spider-computed, no LLM involved.")

        # Checklist items
        checks_seo = [
            ("Title Tag Present", ops.get("has_title", False), "10 pts"),
            (f"Title Length OK (30-60 chars, actual: {ops.get('title_length', 0)})", ops.get("title_length_ok", False), "10 pts"),
            ("Meta Description Present", ops.get("has_meta_description", False), "10 pts"),
            (f"Description Length OK (70-160 chars, actual: {ops.get('description_length', 0)})", ops.get("description_length_ok", False), "5 pts"),
            (f"Single H1 (count: {ops.get('h1_count', 0)})", ops.get("single_h1", False), "10 pts"),
            ("Viewport Meta Tag", ops.get("has_viewport_meta", False), "5 pts"),
            ("Lang Attribute on <html>", ops.get("has_lang_attribute", False), "10 pts"),
            ("Open Graph Tags", ops.get("has_og_tags", False), "5 pts"),
            ("Robots Allows Indexing", ops.get("robots_allows_indexing", True), "10 pts"),
            (f"Image Alt Coverage ({ops.get('image_alt_coverage_pct', 100):.0f}%)", ops.get("image_alt_coverage_pct", 100) >= 90, "15 pts (proportional)"),
            ("Canonical URL Present", ops.get("has_canonical", False), "10 pts"),
        ]
        for label, passed, weight in checks_seo:
            icon = "\u2705" if passed else "\u274c"
            cls = "check-pass" if passed else "check-fail"
            st.markdown(
                f'<span class="{cls}">{icon} {label}</span> <span style="opacity:0.55;">({weight})</span>',
                unsafe_allow_html=True,
            )

        # Header structure
        hdrs = page_data.get("headers", {})
        with st.expander("Header Structure", expanded=False):
            hc1, hc2, hc3, hc4 = st.columns(4)
            hc1.metric("H1", len(hdrs.get("h1", [])))
            hc2.metric("H2", len(hdrs.get("h2", [])))
            hc3.metric("H3", len(hdrs.get("h3", [])))
            hc4.metric("H4-H6", hdrs.get("h4_h6_count", 0))
            for tag in ("h1", "h2", "h3"):
                vals = hdrs.get(tag, [])
                if vals:
                    st.caption(f"**{tag.upper()}:** {', '.join(vals)}")

        issues = ops.get("issues", [])
        if issues:
            st.subheader("Issues")
            for issue in issues:
                sev = issue.get("severity", "unknown")
                desc = issue.get("description", "")
                sev_html = _sev_pill(sev)
                with st.expander(f"{sev.upper()}: {desc}"):
                    st.markdown(f"**Severity:** {sev_html}", unsafe_allow_html=True)
                    st.write(f"**Description:** {desc}")
                    st.write(f"**Suggested Fix:** {issue.get('suggested_fix', 'N/A')}")
        else:
            st.success("No on-page SEO issues found!")

    # ---- Tab 2: Schema ----
    with tabs[2]:
        sch = page_data.get("schema_analysis", {})
        sch_score = sch.get("score", 0)
        st.subheader(f"Schema Analysis -- {sch_score}/100")
        st.progress(max(0.0, min(1.0, sch_score / 100)))

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.write("**Detected Types:**")
            types = sch.get("detected_types", [])
            if types:
                for t in types:
                    st.code(t, language="text")
            else:
                st.info("No schema types detected.")
        with col_s2:
            st.write("**Missing Fields:**")
            missing_f = sch.get("missing_fields", [])
            if missing_f:
                for m in missing_f:
                    st.warning(f"Missing: {m}")
            else:
                st.success("No missing fields.")

    # ---- Tab 3: Content & Readability ----
    with tabs[3]:
        cnt = page_data.get("content_analysis", {})
        cnt_score = cnt.get("score", 0)
        st.subheader(f"Content Analysis -- {cnt_score}/100")
        st.progress(max(0.0, min(1.0, cnt_score / 100)))

        if cnt.get("answers_user_intent"):
            st.success("\u2705 Page provides content aligned with user intent.")
        else:
            st.warning("\u26a0\ufe0f Content may not adequately answer user queries.")

        snippet = cnt.get("answer_snippet")
        if snippet:
            st.info(f"**Best Snippet:** {snippet}")

        uniqueness = cnt.get("content_uniqueness_note")
        if uniqueness:
            st.caption(f"**Content Assessment:** {uniqueness}")

        cnt_issues = cnt.get("issues", [])
        if cnt_issues:
            for issue in cnt_issues:
                sev = issue.get("severity", "medium")
                with st.expander(f"{sev.upper()}: {issue.get('description', '')}"):
                    st.write(f"**Fix:** {issue.get('suggested_fix', 'N/A')}")

        st.markdown("---")
        rda = page_data.get("readability", {})
        rda_score = rda.get("score", 0)
        st.subheader(f"Readability -- {rda_score}/100")
        st.progress(max(0.0, min(1.0, rda_score / 100)))
        st.caption("Deterministic — computed using Flesch-Kincaid formula, no LLM involved.")

        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric("Word Count", rda.get("word_count", 0))
        rc2.metric("Reading Level", rda.get("reading_level") or "N/A")
        fre = rda.get("flesch_reading_ease", 0)
        rc3.metric("Flesch Reading Ease", f"{fre:.1f}")
        fkg = rda.get("flesch_kincaid_grade", 0)
        rc4.metric("FK Grade Level", f"{fkg:.1f}")

        rc5, rc6, rc7 = st.columns(3)
        rc5.metric("Sentences", rda.get("sentence_count", 0))
        rc6.metric("Avg Sentence Length", f"{rda.get('avg_sentence_length', 0):.1f} words")
        thin = rda.get("thin_content", False)
        rc7.metric("Thin Content", "\u26a0\ufe0f Yes" if thin else "\u2705 No")

        # FK interpretation guide
        with st.expander("Flesch Reading Ease Interpretation"):
            st.markdown("""
| FRE Score | Difficulty | Audience |
|-----------|-----------|----------|
| 90-100 | Very Easy | 5th grade |
| 80-89 | Easy | 6th grade |
| 70-79 | Fairly Easy | 7th grade |
| 60-69 | Standard | 8th-9th grade |
| 50-59 | Fairly Difficult | 10th-12th grade |
| 30-49 | Difficult | College |
| 0-29 | Very Difficult | Graduate |
            """)

        rda_issues = rda.get("issues", [])
        if rda_issues:
            for issue in rda_issues:
                sev = issue.get("severity", "medium")
                with st.expander(f"{sev.upper()}: {issue.get('description', '')}"):
                    st.write(f"**Fix:** {issue.get('suggested_fix', 'N/A')}")

    # ---- Tab 4: Links ----
    with tabs[4]:
        la = page_data.get("link_analysis", {})
        la_score = la.get("score", 0)
        st.subheader(f"Link Analysis -- {la_score}/100")
        st.progress(max(0.0, min(1.0, la_score / 100)))

        lc1, lc2, lc3 = st.columns(3)
        lc1.metric("Internal Links", la.get("internal_links", 0))
        lc2.metric("External Links", la.get("external_links", 0))
        lc3.metric("Nofollow", la.get("nofollow_count", 0))

        link_data = pd.DataFrame([
            {"Type": "Internal", "Count": la.get("internal_links", 0)},
            {"Type": "External", "Count": la.get("external_links", 0)},
            {"Type": "Nofollow", "Count": la.get("nofollow_count", 0)},
        ])
        fig_links = px.bar(
            link_data, x="Type", y="Count", color="Type",
            color_discrete_map={"Internal": C_ACCENT, "External": C_GOOD, "Nofollow": C_OK},
        )
        fig_links.update_layout(**_plotly_layout(showlegend=False, height=250))
        st.plotly_chart(fig_links, use_container_width=True)

        broken = la.get("broken_links", [])
        if broken:
            st.error(f"**{len(broken)} broken links found:**")
            for bl in broken:
                st.code(bl, language="text")

        la_issues = la.get("issues", [])
        if la_issues:
            for issue in la_issues:
                sev = issue.get("severity", "medium")
                with st.expander(f"{sev.upper()}: {issue.get('description', '')}"):
                    st.write(f"**Fix:** {issue.get('suggested_fix', 'N/A')}")
        elif not broken:
            st.success("No link issues found!")

    # ---- Tab 5: Performance ----
    with tabs[5]:
        perf = page_data.get("performance", {})
        perf_score = perf.get("score", 0)
        st.subheader(f"Performance -- {perf_score}/100")
        st.progress(max(0.0, min(1.0, perf_score / 100)))
        st.caption("Deterministic — computed from Playwright timing and page metrics, no LLM involved.")

        pc1, pc2, pc3, pc4, pc5 = st.columns(5)
        ttfb = perf.get("ttfb_ms", 0)
        fcp = perf.get("fcp_ms")
        dcl = perf.get("dom_content_loaded_ms", 0)
        ps_bytes = perf.get("page_size_bytes", 0)
        res_count = perf.get("resource_count", 0)

        pc1.metric("TTFB", f"{ttfb} ms")
        pc2.metric("FCP", f"{fcp} ms" if fcp is not None else "N/A")
        pc3.metric("DOM Loaded", f"{dcl} ms")
        pc4.metric("Page Size", f"{ps_bytes / 1024:.1f} KB")
        pc5.metric("Resources", res_count)

        # Web Vitals thresholds reference
        with st.expander("Web Vitals Thresholds"):
            st.markdown("""
| Metric | Good | Needs Work | Poor |
|--------|------|------------|------|
| TTFB | ≤800ms | ≤1800ms | >1800ms |
| FCP | ≤1800ms | ≤3000ms | >3000ms |
| Page Size | ≤500KB | ≤1MB | >2MB |
| Resources | ≤30 | ≤60 | >100 |
            """)

        # TTFB gauge chart
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=ttfb,
            number=dict(suffix=" ms"),
            gauge=dict(
                axis=dict(range=[0, 3000]),
                bar=dict(color=_score_color(100 if ttfb <= 800 else (50 if ttfb <= 1800 else 0))),
                bgcolor="#21262d",
                steps=[
                    dict(range=[0, 800], color="rgba(34,197,94,0.15)"),
                    dict(range=[800, 1800], color="rgba(234,179,8,0.15)"),
                    dict(range=[1800, 3000], color="rgba(239,68,68,0.15)"),
                ],
            ),
            title=dict(text="Time to First Byte"),
        ))
        fig_gauge.update_layout(
            **_plotly_layout(),
            height=250,
            margin=dict(l=30, r=30, t=50, b=20),
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

    # ---- Tab 6: Security ----
    with tabs[6]:
        sec = page_data.get("security", {})
        sec_score = sec.get("score", 0)
        st.subheader(f"Security -- {sec_score}/100")
        st.progress(max(0.0, min(1.0, sec_score / 100)))

        checks = [
            ("HTTPS", sec.get("is_https", False), "40 pts"),
            ("HSTS Header", sec.get("has_hsts", False), "20 pts"),
            ("Content-Security-Policy", sec.get("has_csp", False), "20 pts"),
            ("X-Content-Type-Options", sec.get("has_x_content_type", False), "10 pts"),
            ("No Mixed Content", not sec.get("mixed_content_urls", []), "10 pts"),
        ]
        for label, passed, weight in checks:
            icon = "\u2705" if passed else "\u274c"
            cls = "check-pass" if passed else "check-fail"
            st.markdown(
                f'<span class="{cls}">{icon} {label}</span> <span style="opacity:0.55;">({weight})</span>',
                unsafe_allow_html=True,
            )

        mixed_urls = sec.get("mixed_content_urls", [])
        if mixed_urls:
            with st.expander(f"\u26a0\ufe0f {len(mixed_urls)} Mixed Content URLs"):
                for mu in mixed_urls:
                    st.code(mu, language="text")

    # ---- Tab 7: Accessibility & Canonical ----
    with tabs[7]:
        a11y = page_data.get("accessibility", {})
        a11y_score = a11y.get("score", 0)
        llm_score = a11y.get("llm_score")
        st.subheader(f"Accessibility -- {a11y_score}/100")
        st.progress(max(0.0, min(1.0, a11y_score / 100)))
        st.caption("Blended score: 50% deterministic checklist + 50% LLM qualitative assessment.")

        if llm_score is not None:
            st.markdown(f"**LLM Qualitative Score:** {llm_score}/100")

        # Deterministic checklist
        a11y_checks = [
            ("Skip Navigation Link", a11y.get("has_skip_nav", False), "15 pts"),
            ("Lang Attribute on <html>", a11y.get("has_lang_attribute", False), "15 pts"),
            ("Document Title", a11y.get("has_document_title", False), "10 pts"),
            ("Heading Structure", a11y.get("has_heading_structure", False), "10 pts"),
            (f"Image Alt Coverage ({a11y.get('image_alt_coverage_pct', 100):.0f}%)", a11y.get("image_alt_coverage_pct", 100) >= 90, "20 pts (proportional)"),
            (f"Form Labels (missing: {a11y.get('form_labels_missing', 0)})", a11y.get("form_labels_missing", 0) == 0, "10 pts"),
            (f"No Generic Link Text (found: {a11y.get('generic_link_text_count', 0)})", a11y.get("generic_link_text_count", 0) == 0, "10 pts"),
            (f"No Tabindex Misuse (found: {a11y.get('tabindex_misuse_count', 0)})", a11y.get("tabindex_misuse_count", 0) == 0, "10 pts"),
        ]
        for label, passed, weight in a11y_checks:
            icon = "\u2705" if passed else "\u274c"
            cls = "check-pass" if passed else "check-fail"
            st.markdown(
                f'<span class="{cls}">{icon} {label}</span> <span style="opacity:0.55;">({weight})</span>',
                unsafe_allow_html=True,
            )

        ac2, ac3 = st.columns(2)
        ac2.metric("ARIA Landmarks", a11y.get("aria_landmark_count", 0))
        ac3.metric("Missing Form Labels", a11y.get("form_labels_missing", 0))

        a11y_issues = a11y.get("issues", [])
        if a11y_issues:
            st.subheader("LLM-Identified Issues")
            for issue in a11y_issues:
                sev = issue.get("severity", "medium")
                with st.expander(f"{sev.upper()}: {issue.get('description', '')}"):
                    st.write(f"**Fix:** {issue.get('suggested_fix', 'N/A')}")
        else:
            st.success("No accessibility issues found!")

        st.markdown("---")
        can = page_data.get("canonical_analysis", {})
        can_score = can.get("score", 0)
        st.subheader(f"Canonical & Redirects -- {can_score}/100")
        st.progress(max(0.0, min(1.0, can_score / 100)))

        can_url = can.get("canonical_url")
        matches = can.get("matches_actual_url", True)
        chain = can.get("redirect_chain", [])
        has_hl = can.get("has_hreflang", False)

        cc1, cc2 = st.columns(2)
        cc1.markdown(f"**Canonical URL:** {can_url or '_not set_'}")
        cc1.markdown(f"**Matches Actual:** {'\u2705 Yes' if matches else '\u274c No'}")
        cc2.markdown(f"**Hreflang:** {'\u2705 Present' if has_hl else '\u274c Not found'}")
        cc2.markdown(f"**Redirect Chain:** {len(chain)} hop(s)")

        if chain:
            with st.expander("Redirect Chain"):
                for i, hop in enumerate(chain):
                    st.write(f"{i+1}. {hop}")
