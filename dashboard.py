import streamlit as st
import pandas as pd
import json
import plotly.express as px
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Page config & title
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI SEO Auditor Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("📊 AI SEO Auditor Dashboard")

# ---------------------------------------------------------------------------
# Sidebar — report selection
# ---------------------------------------------------------------------------
st.sidebar.header("Select Audit Report")

reports_dir = Path("ai_seo_auditor/reports")
if not reports_dir.exists():
    st.error("No 'reports' directory found. Run the crawler first!")
    st.stop()

report_folders = sorted(
    [f for f in reports_dir.iterdir() if f.is_dir()],
    key=lambda x: x.stat().st_mtime,
    reverse=True
)

if not report_folders:
    st.warning("No reports found in the 'reports' directory.")
    st.stop()

selected_folder_name = st.sidebar.selectbox(
    "Choose a session:",
    [f.name for f in report_folders]
)

selected_folder_path = reports_dir / selected_folder_name

# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"url", "semantic_analysis", "schema_analysis", "content_analysis"}


@st.cache_data(ttl=300)
def load_data(folder_path: str) -> pd.DataFrame:
    data: list[dict[str, Any]] = []
    for file_path in Path(folder_path).glob("*.json"):
        if file_path.name.startswith("_"):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                report: dict = json.load(f)

            # Validate minimal expected keys
            missing = _REQUIRED_KEYS - report.keys()
            if missing:
                st.warning(f"⚠️ {file_path.name} is missing keys: {missing}")

            row = {
                "url": report.get("url", file_path.stem),
                "semantic_score": report.get("semantic_analysis", {}).get("score", 0),
                "schema_score": report.get("schema_analysis", {}).get("score", 0),
                "content_score": report.get("content_analysis", {}).get("score", 0),
                "has_direct_answer": report.get("content_analysis", {}).get("has_direct_answer", False),
                "issues_count": len(report.get("semantic_analysis", {}).get("issues", [])),
                "detected_types": len(report.get("schema_analysis", {}).get("detected_types", [])),
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
# Overview Metrics — prefer site summary if available, else compute from df
# ---------------------------------------------------------------------------
st.header("📈 Overview")
c1, c2, c3, c4 = st.columns(4)

if site_summary:
    total_pages = site_summary.get("pages_audited", len(df))
    avg_semantic = site_summary.get("avg_semantic_score", df["semantic_score"].mean())
    avg_schema = site_summary.get("avg_schema_score", df["schema_score"].mean())
    avg_content = site_summary.get("avg_content_score", df["content_score"].mean())
else:
    total_pages = len(df)
    avg_semantic = df["semantic_score"].mean()
    avg_schema = df["schema_score"].mean()
    avg_content = df["content_score"].mean()

c1.metric("Pages Audited", total_pages)
c2.metric("Avg Semantic Score", f"{avg_semantic:.1f}")
c3.metric("Avg Schema Score", f"{avg_schema:.1f}")
c4.metric("Avg Content Score", f"{avg_content:.1f}")

# ---------------------------------------------------------------------------
# Visuals
# ---------------------------------------------------------------------------
st.subheader("Score Distributions")
col1, col2 = st.columns(2)

with col1:
    fig_hist = px.histogram(
        df,
        x=["semantic_score", "schema_score", "content_score"],
        barmode='group',
        title="Score Distribution across Pages",
        labels={"value": "Score", "variable": "Metric"}
    )
    st.plotly_chart(fig_hist, use_container_width=True)

with col2:
    # Offset so schema_score=0 still renders a visible point
    df["_schema_size"] = df["schema_score"] + 5
    fig_scatter = px.scatter(
        df,
        x="semantic_score",
        y="content_score",
        size="_schema_size",
        hover_data=["url"],
        title="Semantic vs Content Score (Size = Schema Score)",
        color="issues_count"
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

# ---------------------------------------------------------------------------
# Detailed Table
# ---------------------------------------------------------------------------
st.header("📄 Detailed Page Analysis")
display_cols = ["url", "semantic_score", "schema_score", "content_score", "issues_count", "has_direct_answer"]
st.dataframe(
    df[display_cols].style.background_gradient(subset=["semantic_score", "schema_score", "content_score"], cmap="RdYlGn"),
    use_container_width=True
)

# ---------------------------------------------------------------------------
# Drill-down
# ---------------------------------------------------------------------------
st.header("🔍 Page Drill-down")
selected_url = st.selectbox("Select a page to inspect:", df["url"].unique())

if selected_url:
    page_data: dict = df[df["url"] == selected_url].iloc[0]["raw_data"]

    tab1, tab2, tab3, tab4 = st.tabs(["Semantic & Issues", "Schema Analysis", "Content Analysis", "Meta & Images"])

    with tab1:
        st.subheader("Semantic Analysis")
        sem_score = page_data.get("semantic_analysis", {}).get("score", 0) or 0
        st.progress(max(0.0, min(1.0, sem_score / 100)))

        issues = page_data.get("semantic_analysis", {}).get("issues", [])
        if issues:
            for issue in issues:
                sev = issue.get('severity', 'unknown').upper()
                desc = issue.get('description', 'Issue')
                with st.expander(f"{sev}: {desc}"):
                    st.write(f"**Description:** {desc}")
                    st.write(f"**Suggested Fix:** {issue.get('suggested_fix', 'N/A')}")
        else:
            st.success("No semantic issues found!")

    with tab2:
        st.subheader("Schema Analysis")
        sch_score = page_data.get("schema_analysis", {}).get("score", 0) or 0
        st.progress(max(0.0, min(1.0, sch_score / 100)))

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.write("**Detected Types:**")
            types = page_data.get("schema_analysis", {}).get("detected_types", [])
            if types:
                for t in types:
                    st.code(t, language="text")
            else:
                st.info("No schema types detected.")

        with col_s2:
            st.write("**Missing Fields:**")
            missing = page_data.get("schema_analysis", {}).get("missing_fields", [])
            if missing:
                for m in missing:
                    st.warning(f"Missing: {m}")
            else:
                st.success("No missing fields detected in found schemas.")

    with tab3:
        st.subheader("Content Analysis")
        cnt_score = page_data.get("content_analysis", {}).get("score", 0) or 0
        st.progress(max(0.0, min(1.0, cnt_score / 100)))

        if page_data.get("content_analysis", {}).get("has_direct_answer"):
            st.success("This page provides a direct answer!")
            st.info(f"**Snippet:** {page_data.get('content_analysis', {}).get('answer_snippet', 'N/A')}")
        else:
            st.warning("No direct answer structure detected.")

    with tab4:
        st.subheader("Meta Tags")
        meta = page_data.get("meta_tags", {})
        meta_items = {
            "Title": meta.get("title"),
            "Description": meta.get("description"),
            "Canonical": meta.get("canonical"),
            "OG Title": meta.get("og_title"),
            "OG Description": meta.get("og_description"),
            "OG Image": meta.get("og_image"),
            "Robots": meta.get("robots"),
            "Viewport": meta.get("viewport"),
            "Twitter Card": meta.get("twitter_card"),
        }
        for label, value in meta_items.items():
            if value:
                st.write(f"**{label}:** {value}")
            else:
                st.caption(f"**{label}:** _not set_")

        st.subheader("Image Stats")
        img = page_data.get("image_stats", {})
        ic1, ic2, ic3 = st.columns(3)
        ic1.metric("Total Images", img.get("total_images", 0))
        ic2.metric("Missing alt", img.get("missing_alt", 0))
        ic3.metric("Empty alt", img.get("empty_alt", 0))
