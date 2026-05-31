# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`mv2title` is a library that infers a **song title** from a noisy music-video title (e.g. YouTube titles full of artist names, `feat.`, brackets, "Official Music Video", etc.). Inference is done by a **local, OpenAI-compatible LLM** (developed against gemma served via LM Studio / llama.cpp), and the library additionally **validates** the LLM output before returning it.

The git repo root is the `mv2title/` package itself. Consumer scripts that *use* the library live one directory up (`../File_rename.py`, `../GetFile_name.py`) and in `../file_rename/` (`rename.py`, `download.py`) — these are outside the repo and reach the package via `sys.path` manipulation.

## Setup & commands

- Python **>= 3.12** is required (`utils.chunk_list` uses PEP 695 generic syntax).
- Dependencies are managed with **uv**: `uv sync` to install, `uv lock` after editing `pyproject.toml`.
- An LLM must be hosted with an OpenAI-compatible endpoint. Copy `.env.example` to `.env` and set `BASE_URL` (the server), `API_KEY` (anything for local servers), `SYSTEM_PROMPT`, and optionally `MODEL` (default `gemma-4-e2b-it`).
- Run the built-in demos (each module has a `__main__` block with sample titles): `python main_json.py` or `python main_list.py`.
- There is currently **no test suite or linter configured** — do not assume `pytest`/`ruff` commands exist.

## Architecture

The pipeline is the same in both entry modules: `text -> utils.edit_title -> send_batches -> res_check -> result`.

1. **`utils.edit_title`** prepends 1-based numbering (`"1.<title>"`) so the LLM can align outputs to inputs; **`utils.chunk_list`** splits into `batch_size` chunks (one LLM call per chunk).
2. **`connect.py`** is a thin wrapper over the `openai` client with **module-level singletons** (`client`, `_system_prompt`). `connect.init()` **must be called before** any `send_message()` (otherwise `RuntimeError`). `init()` reads defaults from env at import time. `send_message` defaults to `temperature=0.0` for deterministic extraction.
3. **`res_check` / `res_check_json`** validate the result: (a) output count equals input count, (b) each input/output pair is substring-related (`a in b or b in a`). `bypass_check=True` skips this.

### Two parallel implementations — prefer the JSON one

`main_list.py` and `main_json.py` expose the **same `main(text, batch_size=10, bypass_check=False, debug_mode=False)` signature** but differ in the LLM output contract:

- **`main_json.py` (canonical/preferred)** — LLM returns a JSON array of objects `{index, original, title}`. `send_batches_json` parses (with fallbacks: brace-substring extraction → `ast.literal_eval` → comma split), normalizes loose keys (`new_title`/`name`/`video_title` → `title`), and assigns a **global sequential `index` across batches**. `res_check_json` matches input to output **by `index`** (not array position) and returns `(all_ok, validated_list_of_dicts)` where each dict gets a `valid` flag. `main()` returns `list[dict]` and **raises `ValueError`** on validation failure.
- **`main_list.py` (legacy)** — LLM returns a plain list of strings (`ast.literal_eval`, fallback comma split). Validation is positional. `main()` returns `list[str]` and raises `ValueError` on failure.

When changing behavior, **keep the two `main()` APIs aligned** (error handling, init responsibility). Neither `main()` calls `connect.init()` — **the caller is responsible** for calling it first.

### Conventions to match

- Both entry modules use a dual-import shim (`try: from . import connect / except ImportError: import connect`) so they work both as a package and as standalone scripts. Preserve it.
- **Indentation is inconsistent across files**: `main_json.py` uses **tabs**, while `connect.py`/`main_list.py`/`utils.py` use spaces. Match the existing style of whichever file you edit.
- `main_json.py` logs via the `logging` module (`debug=`/`debug_mode=` toggles `logger.debug`); `main_list.py` still uses `print`.

## Consumer scripts (`../file_rename/`)

`rename.py` reads audio files from `file_rename/files/`, infers titles via `main_json.main(..., bypass_check=True)`, and writes them to metadata with **mutagen** (`TIT2` for mp3/wav, `\xa9nam` for m4a). `download.py` wraps **yt-dlp**: it downloads audio for a URL (or a batch file via `-a`), supports playlists, then reuses `rename.py`'s `write_title` + the mv2title pipeline to tag the downloaded files. `download.py`'s mp3/wav conversion needs **ffmpeg on PATH**. Note these scripts depend on `mutagen`/`yt-dlp`, which are **not** declared in this package's `pyproject.toml`.
