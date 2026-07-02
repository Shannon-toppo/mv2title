# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`mv2title` is a library that infers a **song title** from a noisy music-video title (e.g. YouTube titles full of artist names, `feat.`, brackets, "Official Music Video", etc.). Inference is done by a **local, OpenAI-compatible LLM** (developed against gemma served via LM Studio / llama.cpp), and the library additionally **validates** the LLM output before returning it.

The package uses a standard **src layout** (`src/mv2title/`) and is built with `uv_build`; `uv sync` installs it editable into `.venv`, which is what makes `from mv2title import ...`, `uv run mv2title`, and `python -m mv2title` work. Consumer scripts that *use* the library live in `../file_rename/` (its own git repo) and declare mv2title as an **editable path dependency** in their own `pyproject.toml`.

A phased refactoring plan (with per-task model-delegation notes) lives in `docs/refactoring-plan.md`; consult it before structural changes.

## Setup & commands

- Python **>= 3.12** is required (`utils.chunk_list` uses PEP 695 generic syntax).
- Dependencies are managed with **uv**: `uv sync` to install, `uv lock` after editing `pyproject.toml`.
- An LLM must be hosted with an OpenAI-compatible endpoint. Create a `.env` at the repo root with `BASE_URL` (required, e.g. `http://127.0.0.1:1234/v1/`), `API_KEY` (anything for local servers), `SYSTEM_PROMPT`, and optionally `MODEL` (default `gemma-4-e2b-it`). There is no checked-in template — `.env` is gitignored.
- Try it via the CLI: `uv run mv2title "title..."`, `uv run mv2title -f titles.txt`, or `uv run mv2title --input-json titles.json` (see `cli.py`). The former per-module `__main__` demo blocks were removed in 0.2.0.
- Tests: `uv run pytest`. The suite is fully offline — `tests/conftest.py` provides `fake_client`, a fake `LLMClient` to inject into `pipeline.extract_titles`.
- Lint/format: `uv run ruff check .` and `uv run ruff format .` (config in `[tool.ruff]`; RUF001-003 are ignored because full-width Japanese text is intentional). Type check: `uv run pyright` (`[tool.pyright]`, standard mode). CI (`.github/workflows/ci.yml`) runs ruff + pyright + pytest(+coverage) on push to master and on PRs.

## Architecture

Pipeline (in `pipeline.extract_titles`): `titles (str | TitleInput) -> preprocess.clean_title (preprocess=True) -> prompt.number_titles -> pipeline.send_batches (channel ヒントをプロンプトに付与) -> parsing -> validation.check_results -> partial retry of invalid items -> list[TitleResult]`.

1. **`models.py`** — `TitleInput(title, channel=None)` (channel is an artist-name hint, replaces the old parallel `channels` list) and `TitleResult(index, original, title, valid)` with `to_dict()` for the legacy dict contract.
2. **`preprocess.py`** — `clean_title` (on by default, `preprocess=False` to disable) strips boilerplate noise before the LLM call: bracket groups containing noise keywords (`(Official Music Video)`, `【MV】`, …), `feat./ft.` clauses, and dangling separators. Falls back to the raw title if everything would be removed. `「」`/`『』` are deliberately untouched (they often wrap the actual title). Current behavior (warts included) is pinned by `tests/test_clean_title_golden.py` — change expectations in the same commit as intentional behavior changes.
3. **`prompt.py`** — `number_titles` prepends 1-based numbering (`"1.<title>"`) so the LLM can align outputs to inputs; `make_json_prompt` adds `[チャンネル名]` prefixes as artist hints; `RESPONSE_SCHEMA` is the OpenAI-compatible `json_schema` (structured output when `use_schema=True`).
4. **`parsing.py`** — the untrusted-LLM-output boundary (keep `Any` confined here). `parse_json_response` parses with fallbacks (brace-substring extraction → `ast.literal_eval` → comma split; the last two are legacy deletion candidates that log a `warning` when they fire, see refactoring plan phase 3). `normalize_batch_items` normalizes loose keys (`new_title`/`name`/`video_title` → `title`), converts batch-local indices to a **global sequential `index` across batches**, and overwrites `original` with the denumbered input (the LLM echo is never trusted).
5. **`validation.py`** — `check_results` matches input to output **by `index`** and returns `(all_ok, list[TitleResult])` with **exactly one entry per input, in input order** (missing outputs get an empty-title placeholder, duplicate indices are first-wins, extras are dropped; `original` is reset to the caller's raw title). Each output's **`title`** is validated against the input title and the preprocessed title (`cleaned=` arg) — substring relation after **NFKC + casefold + whitespace-collapse** (`is_title_match`; empty titles are invalid). Do NOT compare `original` against the input: `original` is overwritten with the input itself, so that comparison is vacuous (this was a real bug once — see `test_check_results_validates_title_not_original_echo`).
6. **`pipeline.py`** — `extract_titles(titles, client, ...)` orchestrates the above. The `LLMClient` is **injected explicitly**; there is no init-first global in the new API. `send_batches` chunks into `batch_size` (`utils.chunk_list`, one LLM call per chunk) and falls back to a plain prompt for the rest of the run when the server rejects structured output. Partial retry: when validation fails and `bypass_check=False`, only the invalid items are re-queried up to `retry_invalid` times (default 1) at `_RETRY_TEMPERATURE` (0.4, so a deterministic failure isn't replayed verbatim) before raising `ValueError`.
7. **`connect.py`** — `Config` (frozen dataclass; `Config.from_env()` reads `.env`/env vars **lazily**, so importing the module has no side effects) + `LLMClient` (wraps the `openai` client; passes a placeholder when `api_key` is unset because local servers don't validate keys). Defaults: `timeout` 120 s, `max_retries` 2 (SDK exponential backoff), `temperature=0.0` for deterministic extraction; optional `max_tokens`. `python -m mv2title.connect` runs an offline-endpoint selftest.

The public API is re-exported from `__init__.py`: `extract_titles`, `TitleInput`, `TitleResult`, `LLMClient`, `Config`, `__version__` (keep the latter in sync with `pyproject.toml`). The legacy `main_list.py` was removed in 0.2.0; the `main_json.py` compat shim and module-level `connect.init()`/`send_message()` were removed in 0.3.0.

### Conventions to match

- Imports are **package-relative** (`from . import connect`); the dual-import shims were removed in 0.3.0 along with the `sys.path` hacks (the package is installed editable everywhere it's used).
- **Indentation: all `.py` files use tabs.** `ruff format` enforces this (`[tool.ruff.format] indent-style = "tab"`).
- Logging via the `logging` module (`debug=`/`debug_mode=` toggles `logger.debug`); parse-fallback firings log at `warning` as deletion-candidate telemetry.

## Consumer scripts (`../file_rename/`)

`rename.py` reads audio files from `file_rename/files/`, infers titles via `extract_titles(..., bypass_check=True)`, and writes them to metadata with **mutagen** (`TIT2` for mp3/wav, `\xa9nam` for m4a). `download.py` wraps **yt-dlp**: it downloads audio for a URL (or a batch file via `-a`), supports playlists, then reuses `rename.py`'s `write_title` + the mv2title pipeline to tag the downloaded files. `download.py`'s mp3/wav conversion needs **ffmpeg on PATH**. The folder has its own `pyproject.toml` declaring `mutagen`/`yt-dlp` and mv2title as an editable path dependency — see `../file_rename/CLAUDE.md`.
