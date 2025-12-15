import streamlit as st
import pandas as pd
import json
import plotly.express as px
from pathlib import Path

# Set page configuration
st.set_page_config(
    page_title="AI SEO Auditor Dashboard",
    page_icon="📊",
    layout="wide"
)

# Title
st.title("📊 AI SEO Auditor Dashboard")

# Sidebar for Report Selection
st.sidebar.header("Select Audit Report")

# Get list of report directories
reports_dir = Path("ai_seo_auditor/reports")
if not reports_dir.exists():
    st.error("No 'reports' directory found. Run the crawler first!")
    st.stop()

# List subdirectories in reports/, sorted by creation time (newest first)
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

# Load Data
@st.cache_data
def load_data(folder_path):
    data = []
    for file_path in folder_path.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                report = json.load(f)

                # Flatten structure for DataFrame
                row = {
                    "url": report.get("url"),
                    "semantic_score": report.get("semantic_analysis", {}).get("score", 0),
                    "schema_score": report.get("schema_analysis", {}).get("score", 0),
                    "content_score": report.get("content_analysis", {}).get("score", 0),
                    "has_direct_answer": report.get("content_analysis", {}).get("has_direct_answer", False),
                    "issues_count": len(report.get("semantic_analysis", {}).get("issues", [])),
                    "detected_types": len(report.get("schema_analysis", {}).get("detected_types", [])),
                    "raw_data": report # Keep raw data for details view
                }
                data.append(row)
        except Exception as e:
            st.error(f"Error reading {file_path.name}: {e}")
            continue

    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)

df = load_data(selected_folder_path)

if df.empty:
    st.info("No JSON reports found in this folder.")
    st.stop()

# Overview Metrics
st.header("📈 Overview")
c1, c2, c3, c4 = st.columns(4)

avg_semantic = df["semantic_score"].mean()
avg_schema = df["schema_score"].mean()
avg_content = df["content_score"].mean()
total_pages = len(df)

c1.metric("Pages Audited", total_pages)
c2.metric("Avg Semantic Score", f"{avg_semantic:.1f}")
c3.metric("Avg Schema Score", f"{avg_schema:.1f}")
c4.metric("Avg Content Score", f"{avg_content:.1f}")

# Visuals
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
    fig_scatter = px.scatter(
        df,
        x="semantic_score",
        y="content_score",
        size="schema_score",
        hover_data=["url"],
        title="Semantic vs Content Score (Size = Schema Score)",
        color="issues_count"
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

# Detailed Table
st.header("📄 Detailed Page Analysis")
display_cols = ["url", "semantic_score", "schema_score", "content_score", "issues_count", "has_direct_answer"]
st.dataframe(
    df[display_cols].style.background_gradient(subset=["semantic_score", "schema_score", "content_score"], cmap="RdYlGn"),
    use_container_width=True
)

# Drill-down
st.header("🔍 Page Drill-down")
selected_url = st.selectbox("Select a page to inspect:", df["url"].unique())

if selected_url:
    page_data = df[df["url"] == selected_url].iloc[0]["raw_data"]

    tab1, tab2, tab3 = st.tabs(["Semantic & Issues", "Schema Analysis", "Content Analysis"])

    with tab1:
        st.subheader("Semantic Analysis")
        st.progress(page_data["semantic_analysis"]["score"] / 100)

        issues = page_data["semantic_analysis"].get("issues", [])
        if issues:
            for i, issue in enumerate(issues):
                with st.expander(f"{issue['severity'].upper()}: {issue.get('description', 'Issue')}"):
                    st.write(f"**Description:** {issue.get('description')}")
                    st.write(f"**Suggested Fix:** {issue.get('suggested_fix')}")
        else:
            st.success("No semantic issues found!")

    with tab2:
        st.subheader("Schema Analysis")
        st.progress(page_data["schema_analysis"]["score"] / 100)

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.write("**Detected Types:**")
            types = page_data["schema_analysis"].get("detected_types", [])
            if types:
                for t in types:
                    st.code(t, language="text")
            else:
                st.info("No schema types detected.")

        with col_s2:
            st.write("**Missing Fields:**")
            missing = page_data["schema_analysis"].get("missing_fields", [])
            if missing:
                for m in missing:
                    st.warning(f"Missing: {m}")
            else:
                st.success("No missing fields detected in found schemas.")

    with tab3:
        st.subheader("Content Analysis")
        st.progress(page_data["content_analysis"]["score"] / 100)

        if page_data["content_analysis"].get("has_direct_answer"):
            st.success("This page provides a direct answer!")
            st.info(f"**Snippet:** {page_data['content_analysis'].get('answer_snippet')}")
        else:
            st.warning("No direct answer structure detected.")
