# Ask PPS — Statement of Work (v1 shipped decisions)

**Feature:** Internal knowledge assistant in the PPS Hub  
**Owner:** Thomas Ellison · **Curators:** Thomas Ellison, Tony Cumella, Trey Hollmeyer

## Product

Closed-book Q&A from documented knowledge only. Gaps log to curator inbox; answers published once become retrievable. Team suggestions stay pending until a curator approves.

**Compounding loop:** ask → gap → curator answers once → knowledge grows.

## v1 scope (implemented)

- Flask module: `ask_pps.py` + routes registered from `app.py`
- Postgres FTS (`search_tsv` + GIN) — no vector DB
- Claude via hub `CLAUDE_API_KEY` / `claude-sonnet-4-6`, JSON answer contract, fence strip + retry
- Dashboard widget above lanes → `/ask-pps`
- Curator admin: `/admin/ask-pps` (`@require_ask_pps_curator` — Thomas, Tony, Trey only)
- Daily digest line: questions yesterday + open gaps

## Knowledge sources (seed — idempotent, skip duplicate titles)

| Source | Category |
|--------|----------|
| `knowledge_sources/pps_proposal_voice.txt` | `voice_language` |
| `psc_training_data.py` (chunked) | `training_core_values`, `sales_process`, `production_process`, `trades`, `company_operations` |
| PPS field process bullets | `production_process` |
| `USERS` + routing blurbs | `team_directory` |
| Hub estimator pricing defaults + nuance entry | `pricing` |

**Excluded v1:** `warranty_terms` seed, business-intel/financials, cross-repo proposal builder imports.

**Future:** `knowledge_sources/team_operations_voice.txt` (internal voice — separate from proposal voice).

## Out of scope v1

Multi-turn memory, client DB lookups, role-scoped answers, vector search, auto-publish without curator, Slack/SMS, live PSC training UI integration.

## After deploy

1. Curator visits `/admin/ask-pps` → **Run seed**
2. Ask a documented question → cited answer
3. Ask undocumented question → gap + routing
4. Resolve gap → re-ask works

*Updated July 2026 from Thomas/Tony review session.*