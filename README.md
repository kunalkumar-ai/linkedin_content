# LinkedIn Content Strategist

A multi-agent pipeline that turns your LinkedIn analytics and a running list of
post ideas into a ranked, research-backed recommendation of what to write next
— and drafts 5 concrete post angles for the winning topic.

Built with **CrewAI** (agent orchestration), **Claude** (reasoning + native
web search), and **Composio** (Notion read/write).

## How it works

1. **Performance Analyst** reads a local LinkedIn analytics export (Excel)
   and identifies which topics/formats have driven engagement and impressions.
   It publishes its findings as a new page in your Notion workspace.
2. **Content Strategist** reads your Notion "ideas" page, runs a live Claude
   web search on each candidate topic, and combines that with the Analyst's
   findings to produce a ranked list — ending in one clear top-priority
   recommendation. This is appended back to the ideas page automatically.
3. **Post Idea Generator** (triggered by a second button once you have a top
   recommendation) searches the chosen topic further and drafts 5 distinct,
   specific post angles with short reasons — also saved to the ideas page.

Every dashboard page is auto-archived before a new one is created, so re-runs
don't pile up duplicates. The Notion ideas page accumulates a dated history of
every analysis and idea batch.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with:

```
ANTHROPIC_API_KEY=your_claude_key
COMPOSIO_API_KEY=your_composio_key
```

You'll also need, in Composio:
- A **Notion** connection with access to your ideas page and a parent page
  under which the dashboard page can be created.
- The page IDs configured at the top of `linkedin_content_pipeline.py`
  (`IDEAS_PAGE_ID`, `WORKSPACE_PAGE_ID`) and your Composio user ID
  (`COMPOSIO_USER_ID`).

Drop your LinkedIn "Aggregate Analytics" export (Excel, downloaded from your
LinkedIn analytics dashboard) into the project root — the filename is set via
`ANALYTICS_XLSX` in `linkedin_content_pipeline.py`.

## Run

As a Streamlit app (recommended — includes analytics charts):

```bash
streamlit run linkedin_content_app.py
```

Or as a standalone script:

```bash
python linkedin_content_pipeline.py
```

## Tech

- **CrewAI** — sequential multi-agent orchestration (`Agent`, `Task`, `Crew`)
- **Claude** (`claude-sonnet-5`) — the model behind every agent, plus native
  web search for research
- **Composio** — Notion tool execution (read ideas, create/append pages)
- **Streamlit + Plotly** — UI and analytics charts
- **pandas** — parsing the local analytics export
