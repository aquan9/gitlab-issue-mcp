# gitlab-issue-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes GitLab issues to
AI agents and provides an **AI-powered question-answering** service backed by
[Microsoft AutoGen](https://github.com/microsoft/autogen).

A separate AI (e.g. Claude Desktop, an AutoGen orchestrator, or any MCP-compatible
client) can connect to this server and:

- **Fetch & filter** GitLab issues by state, assignee, label, milestone, or free-text search.
- **Inspect** individual issues and user profiles.
- **Ask natural-language questions** ("What bugs are blocking the v2 release?") and receive
  AI-generated answers that reason over the live issue data.

---

## Features

| MCP Tool | Description |
|---|---|
| `list_issues` | List issues with optional filters (state, assignee, label, milestone, search) |
| `get_issue` | Get a single issue by its project-scoped IID |
| `get_user_issues` | All issues assigned to a specific GitLab user |
| `get_user_profile` | Public GitLab profile for a user |
| `get_project_info` | Metadata for a GitLab project |
| `ask_about_issues` | Natural-language Q&A powered by AutoGen + your LLM |

---

## Requirements

- Python 3.10+
- A GitLab instance (gitlab.com or self-hosted)
- An OpenAI-compatible LLM endpoint — [LiteLLM](https://litellm.ai), OpenAI,
  Azure OpenAI, Ollama, etc.

---

## Installation

```bash
# Clone and install in a virtual environment
git clone https://github.com/aquan9/gitlab-issue-mcp.git
cd gitlab-issue-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Configuration

Copy the example config and fill in your values:

```bash
cp config.example.yaml config.yaml
$EDITOR config.yaml
```

`config.yaml` (never commit this file — it is git-ignored):

```yaml
# GitLab
gitlab_url: "https://gitlab.com"
gitlab_api_key: "glpat-xxxxxxxxxxxxxxxxxxxx"
gitlab_project_id: 12345678   # optional default project

# LLM provider (any OpenAI-compatible endpoint)
llm_base_url: "http://localhost:4000"   # LiteLLM, Ollama, OpenAI, …
llm_model: "gpt-4o"
llm_api_key: "sk-…"                     # use "NA" for keyless local setups
```

### Environment variable overrides

Any config value can be overridden at runtime:

| Variable | Config key |
|---|---|
| `GITLAB_MCP_CONFIG` | path to config file |
| `GITLAB_URL` | `gitlab_url` |
| `GITLAB_API_KEY` | `gitlab_api_key` |
| `LLM_BASE_URL` | `llm_base_url` |
| `LLM_MODEL` | `llm_model` |
| `LLM_API_KEY` | `llm_api_key` |

### Config file search order

1. Path passed to `load_config()` explicitly.
2. `GITLAB_MCP_CONFIG` environment variable.
3. `./config.yaml` (current working directory).
4. `~/.config/gitlab-issue-mcp/config.yaml`.

---

## Running the server

```bash
# With the installed script
gitlab-issue-mcp

# Or directly with Python
python -m gitlab_issue_mcp
```

The server communicates over **stdio** (standard MCP transport), making it
compatible with Claude Desktop and any MCP-aware host.

### Claude Desktop integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gitlab-issue-mcp": {
      "command": "gitlab-issue-mcp",
      "env": {
        "GITLAB_MCP_CONFIG": "/absolute/path/to/config.yaml"
      }
    }
  }
}
```

---

## Using a local LiteLLM proxy

[LiteLLM](https://litellm.ai) lets you run a local OpenAI-compatible proxy in
front of any model:

```bash
pip install litellm
litellm --model ollama/llama3 --port 4000
```

Then in `config.yaml`:

```yaml
llm_base_url: "http://localhost:4000"
llm_model: "ollama/llama3"
llm_api_key: "NA"
```

---

## Development

```bash
# Run tests
pytest

# Run a specific test file
pytest tests/test_config.py -v
```

---

## Project structure

```
gitlab-issue-mcp/
├── config.example.yaml          # Template configuration
├── pyproject.toml
└── src/
    └── gitlab_issue_mcp/
        ├── __init__.py
        ├── __main__.py          # CLI entry point
        ├── config.py            # YAML + env-var configuration loader
        ├── gitlab_client.py     # python-gitlab wrapper
        ├── agent.py             # Microsoft AutoGen Q&A agent
        └── server.py            # FastMCP server & tool definitions
```
