# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
python -m streamlit run app.py
```

Runs on port 8502 (configured in `.streamlit/config.toml`).

For the full production behavior, the app is launched via `launch.py` (what the
`.bat`/`.sh` launchers call). `launch.py` is a supervisor: it reads the saved
`app_theme`, passes a matching light/dark `--theme.base` to Streamlit so the
canvas data tables (`st.dataframe`/`st.data_editor`, which can't be re-themed via
CSS at runtime) match the theme, and relaunches Streamlit when the app requests a
restart. The restart is requested from Settings → Theme when the user crosses the
light/dark line: app.py writes a `.restart_requested` sentinel and calls
`os._exit(0)`; the supervisor sees the sentinel and relaunches; the browser tab
reloads itself. Running `streamlit run app.py` directly still works for dev — you
just lose the launch-time table theming and the auto-restart (it falls back to a
"applies on next launch" message).

## Architecture

Two-file app: `db.py` handles all persistence, `app.py` is the entire UI.

**`db.py`**
- Defines the SQLite schema inline as a `SCHEMA` string — `CREATE TABLE IF NOT EXISTS` so it's idempotent.
- `MIGRATIONS` list handles columns added after initial release. `init_db()` runs both the schema and migrations on every startup.
- `get_connection()` is a context manager: commits on success, rolls back on exception, always closes. Use it for every DB operation.
- Database file: `tradelog.db` next to the source files.

**`app.py`**
- Single-file Streamlit app. Execution flows top-to-bottom on every user interaction (Streamlit's model).
- Sidebar: tag management (add/delete tags used to categorize trades).
- Main area: Add Trade form → trade table → Edit Trade expander → Delete Trade expander.
- `euro_dates` toggle in sidebar controls date display format (MM/DD/YYYY vs DD/MM/YYYY) for the whole page via `fmt_date()`.
- Trade table is read-only (`st.dataframe`); editing is done via the separate Edit Trade expander with a selectbox to pick a trade by ticker + date + ID.
- Stop loss has two values: `opening_stop` (set at entry, never edited) and `current_stop` (editable, defaults to opening stop).
- Ctrl+Enter form submission is implemented via injected JS (`components.html(height=0)`), which intercepts keydown events on the parent document.

## Schema

```
trades: id, entry_date(TEXT ISO), ticker, quantity, entry_price, exit_date, exit_price, notes, stop_enabled, opening_stop, current_stop
tags: id, name(UNIQUE), description
trade_tags: trade_id → trades, tag_id → tags  (cascade delete)
```

Dates stored as ISO 8601 strings (`YYYY-MM-DD`). All price/quantity values stored as REAL.

## Adding schema changes

Add new columns to the `MIGRATIONS` list in `db.py` — never alter `SCHEMA` for existing columns. The migration runner checks `PRAGMA table_info` before each `ALTER TABLE`, so it's safe to run repeatedly.

## Releasing a version

Users get updates when `VERSION` changes on `main` (the in-app updater compares it with GitHub). Every push that bumps `VERSION` must, **in the same commit**, add a section to the top of `CHANGELOG.md`:

```
## 2026-09-24.1
- One bullet per user-visible change, written for the trader, not the code
```

CI (`python updater.py check-changelog`) fails the build when `VERSION` has no section with at least one bullet. The update prompt in the sidebar shows every section between the installed and the new version, and the GitHub release page shows the new version's bullets.

A new module must go in `SOURCE_FILES` in `updater.py` and in both build scripts, or existing installs won't receive it.
