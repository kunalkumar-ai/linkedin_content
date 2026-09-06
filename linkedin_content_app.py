import os

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from linkedin_content_pipeline import (
    ANALYTICS_XLSX,
    IDEAS_PAGE_ID,
    append_notion_content,
    archive_duplicate_dashboards,
    build_crew,
    build_idea_crew,
    load_analytics_dataframes,
    summarize_analytics_excel,
)

load_dotenv()

st.set_page_config(
    page_title="LinkedIn Content Strategist",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

ACCENT = "#0A66C2"  # LinkedIn blue
GRID = "rgba(128,128,128,0.2)"


def _style_fig(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        title=title,
        margin=dict(l=10, r=10, t=40, b=10),
        height=280,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False)
    return fig


def line_chart(df, x, y, title):
    fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="lines", line=dict(color=ACCENT, width=2)))
    return _style_fig(fig, title)


def bar_chart(df, x, y, title, top_n=8):
    top = df.nlargest(top_n, y).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=top[y],
            y=[t[:60] for t in top[x]],
            orientation="h",
            marker_color=ACCENT,
        )
    )
    fig.update_layout(height=280 + top_n * 6)
    return _style_fig(fig, title)


st.sidebar.header("⚙️ Configuration")
st.sidebar.markdown(
    f"**Claude key:** {'✅ found' if os.getenv('ANTHROPIC_API_KEY') else '❌ missing'}"
)
st.sidebar.markdown(
    f"**Composio key:** {'✅ found' if os.getenv('COMPOSIO_API_KEY') else '❌ missing'}"
)
st.sidebar.markdown(
    f"**Analytics file:** {'✅ found' if os.path.exists(ANALYTICS_XLSX) else '❌ missing'}"
)

st.sidebar.markdown("---")
st.sidebar.markdown("### How it works")
st.sidebar.info(
    "1. Analyst reads your local LinkedIn analytics export and publishes a "
    "dashboard page to Notion (replacing any previous one).\n\n"
    "2. Strategist reads your ideas page from Notion, web-searches each "
    "candidate topic with Claude, and ranks them against your dashboard "
    "insights, ending in one top-priority recommendation."
)

st.title("📈 LinkedIn Content Strategist")
st.caption("CrewAI + Claude, tools wired directly through Composio.")

if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None

keys_ready = bool(os.getenv("ANTHROPIC_API_KEY")) and bool(os.getenv("COMPOSIO_API_KEY"))
file_ready = os.path.exists(ANALYTICS_XLSX)

if not keys_ready:
    st.warning("⚠️ Missing ANTHROPIC_API_KEY or COMPOSIO_API_KEY in your .env file.")
elif not file_ready:
    st.warning(f"⚠️ Analytics file not found at: {ANALYTICS_XLSX}")
else:
    dfs = load_analytics_dataframes(ANALYTICS_XLSX)

    st.header("Analytics")
    m1, m2, m3 = st.columns(3)
    m1.metric("Impressions", f"{int(dfs['totals'].get('Impressions', 0)):,}")
    m2.metric("Members reached", f"{int(dfs['totals'].get('Members reached', 0)):,}")
    m3.metric("Total followers", f"{int(dfs['total_followers']):,}")

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            line_chart(dfs["engagement"], "date", "impressions", "Daily Impressions"),
            width="stretch",
        )
        st.plotly_chart(
            bar_chart(dfs["top_by_engagement"], "topic", "engagements", "Top Posts by Engagement"),
            width="stretch",
        )
    with c2:
        st.plotly_chart(
            line_chart(dfs["engagement"], "date", "engagements", "Daily Engagements"),
            width="stretch",
        )
        st.plotly_chart(
            bar_chart(dfs["top_by_impressions"], "topic", "impressions", "Top Posts by Impressions"),
            width="stretch",
        )

    st.plotly_chart(
        line_chart(dfs["followers"], "date", "cumulative_followers", "Follower Growth (cumulative)"),
        width="stretch",
    )

    st.markdown("---")

    if st.button("Run Content Strategy Pipeline", key="run_pipeline"):
        with st.spinner("📊 Archiving old dashboard and running the crew (this can take a minute)..."):
            analytics_summary = summarize_analytics_excel(ANALYTICS_XLSX)
            archive_duplicate_dashboards()
            crew = build_crew(analytics_summary)
            result = crew.kickoff()
            task_outputs = [t.raw for t in result.tasks_output]
            if len(task_outputs) > 1:
                append_notion_content(IDEAS_PAGE_ID, "Strategist Analysis", task_outputs[1])
            st.session_state.pipeline_result = {
                "analytics_summary": analytics_summary,
                "task_outputs": task_outputs,
                "final": result.raw,
            }

    if st.session_state.pipeline_result:
        data = st.session_state.pipeline_result

        with st.expander("📄 Analytics summary (input to the Analyst)", expanded=False):
            st.text(data["analytics_summary"])

        if len(data["task_outputs"]) > 0:
            st.header("1. Analyst: Dashboard Insights")
            st.markdown(data["task_outputs"][0])

        if len(data["task_outputs"]) > 1:
            st.header("2. Strategist: Ranked Ideas & Recommendation")
            st.markdown(data["task_outputs"][1])

            if st.button("Generate 5 Post Ideas for Top Topic", key="generate_post_ideas"):
                with st.spinner("💡 Researching the top topic and drafting 5 post angles..."):
                    idea_crew = build_idea_crew(data["task_outputs"][1])
                    idea_result = idea_crew.kickoff()
                    append_notion_content(IDEAS_PAGE_ID, "Top 5 Post Ideas", idea_result.raw)
                    st.session_state.post_ideas = idea_result.raw

    if st.session_state.get("post_ideas"):
        st.header("3. Post Idea Generator: 5 Angles to Write")
        st.markdown(st.session_state.post_ideas)
