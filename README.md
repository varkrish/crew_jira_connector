# Crew Jira Connector

Bridges Jira issues to [Crew Studio](https://github.com/varun-krishnamurthy/crew-coding-bots) so that moving an issue to a trigger status (e.g. **Ready for Dev**) automatically creates a build, refactor, or migration job and syncs status back to Jira.

## Features

- **Webhook** — `POST /webhooks/jira` for Jira issue created/updated events
- **AI classifier** — Detects mode (build / refactor / migration), repo URLs, and Gherkin from issue text
- **Validation** — Content length, URL allowlist, SSRF protection, optional repo accessibility check
- **Gherkin** — Extracts `.feature` blocks from descriptions and uploads them with the job
- **Pluggable Jira backends** — REST, Atlassian MCP, or self-hosted MCP (e.g. cfdude/mcp-jira)
- **Status sync** — Background poller posts comments and transitions (e.g. Done / Failed) when jobs complete

## Requirements

- Python 3.10+
- A running Crew Studio instance
- Jira (Cloud or Server) with webhooks enabled

## Quick start

```bash
# Clone and install
git clone https://github.com/varun-krishnamurthy/crew-jira-connector.git
cd crew-jira-connector
pip install -e .

# Configure via env (or .env)
export CREW_STUDIO_URL=http://localhost:8081
export JIRA_BASE_URL=https://your-site.atlassian.net
export JIRA_EMAIL=you@example.com
export JIRA_API_TOKEN=your-api-token

# Run
uvicorn crew_jira_connector.app:app --host 0.0.0.0 --port 8080
```

Then in Jira: create a webhook pointing to `http://<this-server>:8080/webhooks/jira` for issue created/updated events.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CREW_STUDIO_URL` | Crew Studio API base URL | `http://localhost:8081` |
| `JIRA_BACKEND` | `rest`, `atlassian_mcp`, or `local_mcp` | `rest` |
| `JIRA_BASE_URL` | Jira instance URL (e.g. `https://site.atlassian.net`) | — |
| `JIRA_EMAIL` | Jira user email (REST / Atlassian MCP) | — |
| `JIRA_API_TOKEN` | Jira API token | — |
| `JIRA_USERNAME` / `JIRA_PASSWORD` | Basic auth (e.g. for Jira Server) | — |
| `JIRA_PROJECT_KEYS` | Comma-separated project keys to accept | (all) |
| `JIRA_TRIGGER_STATUS` | Only process issues in this status | `Ready for Dev` |
| `JIRA_WEBHOOK_SECRET` | Optional HMAC secret for webhook verification | — |
| `LLM_API_BASE_URL` / `LLM_API_KEY` | LLM for classifier (or use `~/.crew-ai/config.yaml`) | — |
| `LLM_MODEL` | Model name | `gpt-4o-mini` |
| `JIRA_TRANSITION_DONE` / `JIRA_TRANSITION_FAILED` | Transition names when job completes/fails | `Done` / `Failed` |
| `POLL_INTERVAL_SECONDS` | How often to poll job status | `15` |
| `DB_PATH` | SQLite path for issue–job mapping | `./data/connector.db` |

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Podman Compose / Docker Compose

From the repo root:

```bash
# Copy .env.example to .env and set CREW_STUDIO_URL, JIRA_* and LLM_* vars
cp .env.example .env

# Build and start
podman compose up -d --build
# or: docker compose up -d --build

# Logs
podman compose logs -f
```

Default port is 8080 (override with `CONNECTOR_PORT`). The connector uses a named volume `connector-data` for the SQLite DB.

## Docker (single container)

Build and run without compose:

```bash
podman build -t crew-jira-connector .
# or: docker build -t crew-jira-connector .

podman run -p 8080:8080 \
  -e CREW_STUDIO_URL=http://host.containers.internal:8081 \
  -e JIRA_BASE_URL=https://your-site.atlassian.net \
  -e JIRA_EMAIL=you@example.com \
  -e JIRA_API_TOKEN=your-token \
  -v crew-jira-data:/app/data \
  crew-jira-connector
```

## License

See repository license file.
