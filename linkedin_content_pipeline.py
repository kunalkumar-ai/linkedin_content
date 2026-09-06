import os
import re
from datetime import datetime
from urllib.parse import unquote

import anthropic
import pandas as pd
from dotenv import load_dotenv
from composio import Composio
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "pg-test-fdf712d1-8ffc-400a-9910-6d344d26aec9")

IDEAS_PAGE_ID = "3d3fb12a-0c4c-8053-a2a3-c8768b3e6134"  # "ideas" page
WORKSPACE_PAGE_ID = "3acfb12a-0c4c-8034-9272-face975b7765"  # "analytics of linkedin" page

ANALYTICS_XLSX = os.path.join(
    os.path.dirname(__file__),
    "AggregateAnalytics_Kunal Kumar_2026-06-09_2026-09-06.xlsx",
)

composio = Composio(api_key=COMPOSIO_API_KEY)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
llm = LLM(model="anthropic/claude-sonnet-5", api_key=ANTHROPIC_API_KEY)


def _slug_topic(url):
    if not isinstance(url, str):
        return None
    slug = url.split("kunal-kumar-ai-connect_")[-1].split("-share-")[0].split("-ugcPost-")[0]
    return unquote(slug).replace("-", " ")[:140]


def load_analytics_dataframes(path: str) -> dict:
    """Parse the LinkedIn aggregate-analytics export into clean DataFrames for charting."""
    xl = pd.ExcelFile(path)

    discovery = xl.parse("DISCOVERY", header=None)
    totals = {row[0]: row[1] for _, row in discovery.iterrows()}

    followers_raw = xl.parse("FOLLOWERS", header=None)
    total_followers = followers_raw.iloc[0, 1]
    followers = followers_raw.iloc[2:, 0:2].copy()
    followers.columns = ["date", "new_followers"]
    followers["date"] = pd.to_datetime(followers["date"], format="%m/%d/%Y", errors="coerce")
    followers["new_followers"] = pd.to_numeric(followers["new_followers"], errors="coerce")
    followers = followers.dropna(subset=["date"])
    followers["cumulative_followers"] = followers["new_followers"].cumsum()

    engagement = xl.parse("ENGAGEMENT")
    engagement.columns = ["date", "impressions", "engagements"]
    engagement["date"] = pd.to_datetime(engagement["date"], errors="coerce")
    engagement = engagement.dropna(subset=["date"])

    raw = xl.parse("TOP POSTS", header=None)
    by_engagement = raw.iloc[3:, 0:3].copy()
    by_engagement.columns = ["url", "date", "engagements"]
    by_engagement["topic"] = by_engagement["url"].apply(_slug_topic)
    by_engagement["engagements"] = pd.to_numeric(by_engagement["engagements"], errors="coerce")
    by_engagement = by_engagement.dropna(subset=["topic", "engagements"])

    by_impressions = raw.iloc[3:, 4:7].copy()
    by_impressions.columns = ["url", "date", "impressions"]
    by_impressions["topic"] = by_impressions["url"].apply(_slug_topic)
    by_impressions["impressions"] = pd.to_numeric(by_impressions["impressions"], errors="coerce")
    by_impressions = by_impressions.dropna(subset=["topic", "impressions"])

    return {
        "totals": totals,
        "total_followers": total_followers,
        "followers": followers,
        "engagement": engagement,
        "top_by_engagement": by_engagement,
        "top_by_impressions": by_impressions,
    }


def summarize_analytics_excel(path: str) -> str:
    """Parse the LinkedIn aggregate-analytics export into a compact text summary for the LLM."""
    data = load_analytics_dataframes(path)
    lines = []

    lines.append("OVERALL (last ~90 days):")
    for key, value in data["totals"].items():
        lines.append(f"  {key}: {value}")

    new_followers = int(data["followers"]["new_followers"].sum())
    lines.append(f"\nFOLLOWERS: total={data['total_followers']}, new_in_period={new_followers}")

    lines.append("\nTOP POSTS BY ENGAGEMENT (topic guess from URL slug -> engagements):")
    for _, row in data["top_by_engagement"].head(10).iterrows():
        lines.append(f"  - \"{row['topic']}\" -> {int(row['engagements'])} engagements ({row['date']})")

    lines.append("\nTOP POSTS BY IMPRESSIONS (topic guess from URL slug -> impressions):")
    for _, row in data["top_by_impressions"].head(10).iterrows():
        lines.append(f"  - \"{row['topic']}\" -> {int(row['impressions'])} impressions ({row['date']})")

    return "\n".join(lines)


DASHBOARD_TITLE = "LinkedIn Analytics Dashboard"


def archive_duplicate_dashboards() -> None:
    """Archive any existing dashboard pages under the workspace page before creating a new one."""
    result = composio.tools.execute(
        slug="NOTION_SEARCH_NOTION_PAGE",
        arguments={"query": DASHBOARD_TITLE},
        user_id=COMPOSIO_USER_ID,
        dangerously_skip_version_check=True,
    )
    for page in result.get("data", {}).get("results", []):
        title_parts = page.get("properties", {}).get("title", {}).get("title", [])
        title = "".join(t.get("plain_text", "") for t in title_parts)
        parent = page.get("parent", {})
        if title == DASHBOARD_TITLE and parent.get("page_id") == WORKSPACE_PAGE_ID:
            composio.tools.execute(
                slug="NOTION_ARCHIVE_NOTION_PAGE",
                arguments={"page_id": page["id"], "archive": True},
                user_id=COMPOSIO_USER_ID,
                dangerously_skip_version_check=True,
            )


def _text_block(block_type: str, content: str) -> dict:
    return {
        "type": block_type,
        block_type: {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]},
    }


def markdown_to_notion_blocks(markdown_text: str) -> list:
    """Convert plain-ish Markdown into a flat list of simple Notion block objects."""
    blocks = []
    for line in markdown_text.splitlines():
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line.strip())  # drop bold markers, keep text
        if not line:
            continue
        if line.startswith("### "):
            blocks.append(_text_block("heading_3", line[4:]))
        elif line.startswith("## "):
            blocks.append(_text_block("heading_2", line[3:]))
        elif line.startswith("# "):
            blocks.append(_text_block("heading_1", line[2:]))
        elif line.startswith(("- ", "* ")):
            blocks.append(_text_block("bulleted_list_item", line[2:]))
        elif re.match(r"^\d+\.\s", line):
            blocks.append(_text_block("numbered_list_item", re.sub(r"^\d+\.\s", "", line)))
        elif set(line) <= {"-", "—"}:
            continue  # skip markdown horizontal rules
        else:
            blocks.append(_text_block("paragraph", line))
    return blocks


def append_notion_content(page_id: str, heading: str, markdown_text: str) -> None:
    """Append a labeled section of Markdown-derived content to an existing Notion page."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    blocks = [_text_block("heading_2", f"{heading} — {timestamp}")]
    blocks.extend(markdown_to_notion_blocks(markdown_text))

    for i in range(0, len(blocks), 90):  # Notion caps children per request; chunk defensively
        composio.tools.execute(
            slug="NOTION_APPEND_TEXT_BLOCKS",
            arguments={"block_id": page_id, "children": blocks[i : i + 90]},
            user_id=COMPOSIO_USER_ID,
            dangerously_skip_version_check=True,
        )


@tool("Read Notion Page")
def read_notion_page(page_id: str) -> str:
    """Read a Notion page's full content as Markdown, given its page ID."""
    result = composio.tools.execute(
        slug="NOTION_GET_PAGE_MARKDOWN",
        arguments={"page_id": page_id},
        user_id=COMPOSIO_USER_ID,
        dangerously_skip_version_check=True,
    )
    return str(result.get("data", {}).get("markdown") or result.get("data"))


@tool("Create Notion Page")
def create_notion_page(parent_page_id: str, title: str, markdown_content: str) -> str:
    """Create a new Notion page under a parent page, with the given title and Markdown content."""
    result = composio.tools.execute(
        slug="NOTION_CREATE_NOTION_PAGE",
        arguments={"parent_id": parent_page_id, "title": title, "markdown": markdown_content},
        user_id=COMPOSIO_USER_ID,
        dangerously_skip_version_check=True,
    )
    data = result.get("data", {})
    return f"Created Notion page: {data.get('url', data)}"


@tool("Web Search")
def web_search(query: str) -> str:
    """Search the live web for current information about a query using Claude's native web search."""
    resp = claude.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": f"Search the web and summarize current, concrete findings about: {query}"}],
    )
    return "\n".join(block.text for block in resp.content if block.type == "text")


def build_crew(analytics_summary: str) -> Crew:
    analyst = Agent(
        role="LinkedIn Performance Analyst",
        goal="Turn raw LinkedIn analytics into a clear picture of which post topics and styles perform best.",
        backstory=(
            "You study engagement and impression data to find patterns in what content resonates, "
            "then publish your findings as a dashboard page in Notion."
        ),
        llm=llm,
        tools=[create_notion_page],
        verbose=True,
    )

    strategist = Agent(
        role="Content Strategist",
        goal="Rank candidate post ideas by real-world relevance and fit with what has worked before, and recommend the single best one to write next.",
        backstory=(
            "You read a list of candidate LinkedIn post ideas, research each one's current relevance "
            "on the live web, weigh that against what the analyst found about past performance, and "
            "make a clear, justified recommendation of which idea is worth writing about next."
        ),
        llm=llm,
        tools=[read_notion_page, web_search],
        verbose=True,
    )

    analyze_task = Task(
        description=(
            f"Here is a summary of the account's LinkedIn analytics for the last ~90 days:\n\n"
            f"{analytics_summary}\n\n"
            "Analyze it: identify which topics, hooks, or formats drove the most engagement and "
            "impressions, and any clear patterns (e.g. technical deep-dives vs. narrative posts, "
            "AI/LLM topics vs. others). Then call the Create Notion Page tool with "
            f"parent_page_id='{WORKSPACE_PAGE_ID}', a title like 'LinkedIn Analytics Dashboard', "
            "and your findings written as clear Markdown (headings, bullet points)."
        ),
        expected_output=(
            "A short confirmation that the dashboard page was created, plus the key performance "
            "insights in a few bullet points."
        ),
        agent=analyst,
    )

    rank_task = Task(
        description=(
            f"Call the Read Notion Page tool with page_id='{IDEAS_PAGE_ID}' to get the list of "
            "candidate post ideas/topics. Extract each distinct idea. For each one (or the most "
            "promising handful if there are many), call the Web Search tool to check how relevant, "
            "current, or discussed that topic is right now. Combine that with the performance "
            "insights from the previous task. Then produce a ranked list of the ideas from most to "
            "least worth writing about next, and clearly call out the single top-priority idea with "
            "a concrete explanation of why it is worth writing about now."
        ),
        expected_output=(
            "A ranked list of the candidate ideas with brief justifications, ending with a clearly "
            "labeled top recommendation: the one topic worth writing about next and why."
        ),
        agent=strategist,
        context=[analyze_task],
    )

    return Crew(
        agents=[analyst, strategist],
        tasks=[analyze_task, rank_task],
        process=Process.sequential,
        verbose=True,
    )


def build_idea_crew(strategist_output: str) -> Crew:
    idea_generator = Agent(
        role="Post Idea Generator",
        goal="Turn a single chosen topic into 5 concrete, distinct LinkedIn post angles worth writing.",
        backstory=(
            "You take a topic that has already been chosen as the top priority, research it "
            "further on the live web, and pitch 5 specific, distinct post angles a writer could "
            "run with immediately."
        ),
        llm=llm,
        tools=[web_search],
        verbose=True,
    )

    idea_task = Task(
        description=(
            f"Here is the content strategist's ranked recommendation:\n\n{strategist_output}\n\n"
            "Identify the single top-priority topic from this. Call the Web Search tool at least "
            "once to gather current, concrete angles, data points, or debates around this topic. "
            "Then produce exactly 5 distinct LinkedIn post ideas on this topic. Each idea needs a "
            "specific hook/angle (not just the topic name) and a one-sentence reason it's worth "
            "writing. Keep every reason to one short sentence — no long justifications."
        ),
        expected_output=(
            "A numbered list of exactly 5 post ideas, each with a specific hook and a one-sentence "
            "reason, nothing else."
        ),
        agent=idea_generator,
    )

    return Crew(
        agents=[idea_generator],
        tasks=[idea_task],
        process=Process.sequential,
        verbose=True,
    )


def main():
    print("Reading local analytics file...")
    analytics_summary = summarize_analytics_excel(ANALYTICS_XLSX)
    print(analytics_summary)

    print("Archiving any duplicate dashboard pages...")
    archive_duplicate_dashboards()

    print("\nRunning crew...\n")
    crew = build_crew(analytics_summary)
    result = crew.kickoff()
    task_outputs = [t.raw for t in result.tasks_output]

    if len(task_outputs) > 1:
        print("\nAppending strategist analysis to the ideas page...")
        append_notion_content(IDEAS_PAGE_ID, "Strategist Analysis", task_outputs[1])

    print("\n\n=== FINAL RECOMMENDATION ===\n")
    print(result.raw)


if __name__ == "__main__":
    main()
