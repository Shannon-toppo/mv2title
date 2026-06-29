# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`mv2title` is a library that infers a **song title** from a noisy music-video title (e.g. YouTube titles full of artist names, `feat.`, brackets, "Official Music Video", etc.). Inference is done by a **local, OpenAI-compatible LLM** (developed against gemma served via LM Studio / llama.cpp), and the library additionally **validates** the LLM output before returning it.

The git repo root is the `mv2title/` package itself. Consumer scripts that *use* the library live one directory up (`../File_rename.py`, `../GetFile_name.py`) and in `../file_rename/` (`rename.py`, `download.py`) — these are outside the repo and reach the package via `sys.path` manipulation.

## Setup & commands

- Python **>= 3.12** is required (`utils.chunk_list` uses PEP 695 generic syntax).
- Dependencies are managed with **uv**: `uv sync` to install, `uv lock` after editing `pyproject.toml`.
- An LLM must be hosted with an OpenAI-compatible endpoint. Create a `.env` at the repo root with `BASE_URL` (required, e.g. `http://127.0.0.1:1234/v1/`), `API_KEY` (anything for local servers), `SYSTEM_PROMPT`, and optionally `MODEL` (default `gemma-4-e2b-it`). There is no checked-in template — `.env` is gitignored.
- Run the built-in demos (each module reads sample titles from gitignored `test.txt`, one per line): `python main_json.py`, or use the CLI: `uv run mv2title "title..."` (see `cli.py`).
- Tests: `uv run pytest`. The suite is fully offline — `tests/conftest.py` provides a `fake_send` fixture that replaces `connect.send_message`.
- Lint/format: `uv run ruff check .` and `uv run ruff format .` (config in `[tool.ruff]`). CI (`.github/workflows/ci.yml`) runs ruff + pytest on push to master and on PRs.

## Architecture

Pipeline (in `main_json.main`): `text -> utils.clean_title (preprocess=True) -> utils.edit_title -> send_batches_json -> res_check_json -> partial retry of invalid items -> result`.

1. **`utils.clean_title`** (on by default, `preprocess=False` to disable) strips boilerplate noise before the LLM call: bracket groups containing noise keywords (`(Official Music Video)`, `【MV】`, …), `feat./ft.` clauses, and dangling separators. Falls back to the raw title if everything would be removed. `「」`/`『』` are deliberately untouched (they often wrap the actual title).
2. **`utils.edit_title`** prepends 1-based numbering (`"1.<title>"`) so the LLM can align outputs to inputs; **`utils.chunk_list`** splits into `batch_size` chunks (one LLM call per chunk).
3. **`connect.py`** is a thin wrapper over the `openai` client with **module-level singletons** (`client`, `_system_prompt`). `connect.init()` **must be called before** any `send_message()` (otherwise `RuntimeError`). `init()` reads defaults from env at import time and configures `timeout` (default 120 s) and `max_retries` (default 2 — the openai SDK retries transient errors with exponential backoff). `send_message` defaults to `temperature=0.0` for deterministic extraction and accepts optional `max_tokens`.
4. **`res_check_json`** validates by comparing each output's **`title`** against the input title (and the preprocessed title via the `cleaned=` arg) — substring relation after **NFKC + casefold + whitespace-collapse** normalization (`utils.is_title_match`; empty titles are invalid). Do NOT compare `original` against the input: `original` is overwritten with the input itself, so that comparison is vacuous (this was a real bug once — see `test_res_check_validates_title_not_original_echo`).
5. **Partial retry**: when validation fails and `bypass_check=False`, `main()` re-queries **only the invalid items** up to `retry_invalid` times (default 1) at `_RETRY_TEMPERATURE` (0.4, so a deterministic failure isn't replayed verbatim) before raising `ValueError`.

### main_json is canonical; main_list is deprecated

- **`main_json.py`** — LLM returns a JSON array of objects `{index, original, title}` (structured output via `json_schema` when `use_schema=True`, with automatic fallback to a plain prompt if the server rejects it). `send_batches_json` parses with fallbacks (brace-substring extraction → `ast.literal_eval` → comma split), normalizes loose keys (`new_title`/`name`/`video_title` → `title`), and assigns a **global sequential `index` across batches**. `res_check_json` matches input to output **by `index`** and returns `(all_ok, validated)` where `validated` has **exactly one entry per input, in input order** (missing outputs get an empty-title placeholder, duplicate indices are first-wins, extras are dropped; `original` is reset to the caller's raw title). `main()` returns that `list[dict]` and raises `ValueError` on validation failure.
- **`main_list.py` (deprecated)** — legacy plain-list-of-strings contract; `main()` emits a `DeprecationWarning` and the module is slated for removal. Bug fixes only; do not add features or port new behavior to it.

Neither `main()` calls `connect.init()` — **the caller is responsible** for calling it first.

### Conventions to match

- Both entry modules use a dual-import shim (`try: from . import connect / except ImportError: import connect`) so they work both as a package and as standalone scripts. Preserve it.
- **Indentation: all `.py` files use tabs.** `ruff format` enforces this (`[tool.ruff.format] indent-style = "tab"`).
- `main_json.py` logs via the `logging` module (`debug=`/`debug_mode=` toggles `logger.debug`); `main_list.py` still uses `print`.

## Consumer scripts (`../file_rename/`)

`rename.py` reads audio files from `file_rename/files/`, infers titles via `main_json.main(..., bypass_check=True)`, and writes them to metadata with **mutagen** (`TIT2` for mp3/wav, `\xa9nam` for m4a). `download.py` wraps **yt-dlp**: it downloads audio for a URL (or a batch file via `-a`), supports playlists, then reuses `rename.py`'s `write_title` + the mv2title pipeline to tag the downloaded files. `download.py`'s mp3/wav conversion needs **ffmpeg on PATH**. Note these scripts depend on `mutagen`/`yt-dlp`, which are **not** declared in this package's `pyproject.toml`.
