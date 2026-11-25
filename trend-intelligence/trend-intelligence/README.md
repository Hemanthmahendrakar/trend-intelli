# Internet Trend Intelligence System

Collects public headlines from **Hacker News, Reddit, Google Trends, TechCrunch and Product Hunt**, cleans and
de-duplicates them, groups them into topics, scores each topic with a **transparent formula**, stores everything
in **PostgreSQL**, and shows the results in a **Streamlit** dashboard backed by a **FastAPI** service.

It answers: *what is trending now, what is gaining popularity, what each platform is discussing, what is new compared
with the previous day, and which sources report it.*

```
 sources ─► collectors ─► clean + dedup ─► PostgreSQL ─► keywords ─► topics ─► scoring ─► snapshots
 (API/RSS)   (Requests)    (BeautifulSoup)   articles     (rules)    (grouping)  (formula)    │
                                                                                              ▼
                                                     Streamlit dashboard ◄── FastAPI ◄── trend_scores
```

## Quick start

Requires Python 3.10+ and (for the full system) PostgreSQL 14+ or Docker.

```bash
git clone <your-repo-url> trend-intelligence && cd trend-intelligence
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                                      # then edit it (see Configuration)
```

**1. Try it with no database** (collects live data, prints the top topics):

```bash
trendintel preview --sources hackernews,techcrunch,producthunt,google_trends
```

**2. Full system with PostgreSQL**

```bash
docker compose up -d db                 # or point DATABASE_URL at your own Postgres
trendintel init-db                      # create tables
trendintel run                          # collect + analyse once
trendintel run --every-minutes 30       # ...or keep it running
uvicorn trendintel.api.main:app --reload            # API: http://localhost:8000/docs
streamlit run src/trendintel/dashboard/app.py       # Dashboard: http://localhost:8501
```

**3. Everything in Docker:** `docker compose up --build` (worker + API + dashboard + database).

> Growth needs history. Until the collector has run for ~36 hours the dashboard shows a banner and scores exclude
> growth. This is deliberate; see *Trend scoring*.

### CLI

| Command | What it does |
|---|---|
| `trendintel init-db` | Creates/updates tables (idempotent) |
| `trendintel collect [--sources a,b]` | Fetch → clean → dedup → store |
| `trendintel analyze` | Score stored articles, save a snapshot, print the top topics |
| `trendintel run [--every-minutes N]` | `collect` + `analyze`, optionally looping |
| `trendintel preview [--top N]` | Same pipeline in memory, no database |

Source keys: `hackernews`, `reddit`, `google_trends`, `techcrunch`, `producthunt`.

## Configuration

All settings are environment variables (loaded from `.env`); see `.env.example` for the full list. Nothing secret is in
the code. The important ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg2://user:pass@localhost:5432/trendintel` |
| `USER_AGENT` | Identifies you to sources; put a contact address in it |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit official API app credentials. Without them Reddit is **skipped**, not failed |
| `REQUEST_MIN_INTERVAL` | Seconds between requests to the same host (default 1.0) |
| `TREND_WINDOW_HOURS`, `TREND_HALF_LIFE_HOURS`, `TREND_MIN_MENTIONS` | Scoring parameters |

## Components and their purpose

| File | Purpose |
|---|---|
| `config.py` | Reads all environment settings into one immutable `Settings` object |
| `logging_setup.py` | Console + optional rotating-file logging |
| `http_client.py` | Polite HTTP: User-Agent, timeouts, retries with back-off, per-host rate limiting |
| `collectors/` | One class per source (`base.py` interface, `rss.py` shared RSS/Atom parser). Return raw `Article`s only |
| `processing/cleaning.py` | Strip HTML/boilerplate, canonicalise URLs, normalise timestamps to UTC, hash for dedup |
| `processing/dedup.py` | Remove duplicates *within a source* (cross-source repeats are the signal, so they are kept) |
| `processing/keywords.py` | Rule-based unigram/bigram extraction with stop-words and light singularisation |
| `processing/topics.py` | Groups overlapping terms into topics (Jaccard + containment rules, union-find) |
| `trends/scoring.py` | The scoring formula, its config and the written methodology |
| `trends/engine.py` | Pure function: articles → topics → scores (no I/O, fully unit-tested) |
| `db/schema.sql`, `db/repository.py` | Tables and all SQL |
| `pipeline.py` | Orchestrates collection (failure-isolated per source) and analysis |
| `cli.py` | `trendintel` command |
| `api/main.py` | Read-only FastAPI service |
| `dashboard/app.py` | Streamlit UI that talks to the API |

## Data sources and compliance

| Source | Access method | Notes |
|---|---|---|
| Hacker News | HN Search (Algolia) public JSON API, one request | Front page only |
| Reddit | Official OAuth API (client credentials) | Needs your own registered app; review Reddit's Data API Terms, especially for commercial use |
| Google Trends | Public "Trending now" RSS feed | Not a documented API; format may change; a failure is handled like any other |
| TechCrunch | Public RSS feed | Only headline, excerpt and link are stored; the dashboard links back to the original |
| Product Hunt | Public Atom feed | If you obtain API access later, add a collector; check their terms for commercial use |

No page scraping is used, and **Playwright is not needed** for these sources (it is an optional extra,
`pip install -e ".[browser]"`, reserved for a future source that truly requires JavaScript rendering). Request
volume is tiny: about 5-6 requests per run, spaced per host. I have not verified each site's current terms for you, so
read them before publishing or commercialising results. Keep `USER_AGENT` honest.

## Database design

| Table | Role |
|---|---|
| `sources` | One row per source |
| `collection_runs` | One row per source per collection attempt: start/finish timestamps, status (`success`/`failed`/`skipped`), counts, error text |
| `articles` | Cleaned content; unique per `(source, url_hash)` and `(source, content_hash)` |
| `topics` | Stable topic slug + label, first/last seen |
| `article_topics` | Many-to-many article ↔ topic |
| `trend_scores` | One row per topic per analysis run (all four components, total, mentions, sources, flags). This is what the history chart reads |

## Trend scoring

For each topic, with window `W` (default 24 h; current = last `W`, previous = the `W` before that):

| Component | Definition |
|---|---|
| Frequency `F` | `ln(1+M) / ln(1+M_max)`, where `M` = distinct articles in the current window |
| Recency `R` | `Σ 0.5^(age_h/half_life)` over those articles (half-life 6 h), divided by the maximum across topics |
| Growth `G` | `clip(log2((M+1)/(M_prev+1)), 0, 3) / 3` |
| Diversity `S` | distinct sources mentioning the topic ÷ distinct sources active in the window |

**Score = 100 × (0.30·F + 0.25·R + 0.25·G + 0.20·S)**. A topic is **emerging** when it had no mentions in the previous
window and has at least 3 now (only once history exists).

Worked example (from the unit tests): topic A has 4 mentions across 3 sources vs 1 before → F 1.00, R 1.00, G 0.44,
S 1.00 → **86.0**. Topic C has 3 mentions across 2 sources vs 0 before → F 0.86, R 0.79, G 0.67, S 0.67 → **75.6**, flagged
emerging. Topic B has 2 mentions from one source vs 2 before → **35.9**.

### Limitations (also shown in the dashboard's Methodology tab)

- Scores are **relative within a run**, not absolute popularity; they are not comparable across days.
- The system measures attention **within a sample of five sources with limited item counts**, not "the whole internet".
- A Reddit post linking a TechCrunch article counts as two sources. Intended, but not proof of independent reporting.
- Topics come from keyword matching: homonyms merge, and paraphrased headlines about one event can split.
- Google Trends items are search terms; a long-running term is stored once, so it can look flat.
- Weights and half-life are judgement calls, not fitted to data. Tune them in `ScoringConfig`.
- Tiny counts (2-3 mentions) are noisy. Collection gaps look like declines.
- Topic identity across runs is the label's slug: if a topic's best label changes, its history splits.
- With under ~36 h of history, growth is dropped (weights rescaled) and nothing is flagged emerging.

## Testing

```bash
pytest -q
```

Tests cover cleaning, dedup, keywords, topic grouping, scoring, the end-to-end engine, every collector (with fake HTTP and
sample payloads), the HTTP client's throttling/error wrapping, pipeline failure isolation, and the API (with a fake repository).
**Not covered by automated tests:** the live sources and the PostgreSQL repository (it needs a real database); verify those
with `trendintel preview` and `trendintel run` on your machine.

## Development phases → code

1. **Setup:** `pyproject.toml`, `.env.example`, `config.py`, `logging_setup.py`
2. **Collection:** `http_client.py`, `collectors/` (all five sources)
3. **Cleaning/dedup:** `processing/cleaning.py`, `dedup.py`, `prepare.py`
4. **Trend detection:** `keywords.py`, `topics.py`, `trends/`
5. **Database:** `db/`, `pipeline.py`
6. **Dashboard:** `api/main.py`, `dashboard/app.py`
7. **Testing/docs/deploy:** `tests/`, this README, `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`

## Deployment notes

- `docker compose up --build` runs the whole stack. Use a strong `POSTGRES_PASSWORD` (URL-encode special characters in
  `DATABASE_URL`) and do not expose port 5432 publicly (remove the `ports:` entry for `db` in production).
- The API has no authentication and is read-only; put it behind your reverse proxy/auth if exposed.
- Run `trendintel run --every-minutes 30` as a worker, or call `trendintel run` from cron.

## Roadmap

Add sources by subclassing `BaseCollector`; store keyword embeddings for better topic grouping; sentiment; alerts when a topic
becomes emerging; per-topic alias table so labels can change without splitting history.
