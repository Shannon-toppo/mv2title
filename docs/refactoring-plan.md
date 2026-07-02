# mv2title リファクタリング計画

作成日: 2026-07-02 / 対象バージョン: 0.1.0 → 0.3.0

## 背景と現状評価

コードベース自体は小規模(src 約 900 行 + テスト約 800 行)で、CI・オフラインテストも整備済み。
ただし以下の 4 カテゴリの負債が蓄積している。

1. **レガシー経路の残存** — 非推奨の `main_list.py` と、その時代の名残であるパースフォールバック(カンマ分割等)。
2. **グローバル状態と import 時副作用** — `connect.py` は import 時に `load_dotenv()` と環境変数読みが走り、`client` / `_system_prompt` / `model` がモジュール変数。CLI は `connect.model = args.model` と直接書き換えている。
3. **main_json.py への責務集中** — プロンプト生成・送信・フォールバック・3 段パース・正規化・検証・リトライが 1 ファイルに同居。データ契約が `list[dict[str, Any]]` で、`channels` が並行リストとして 5 関数を貫通。
4. **パッケージとしての未整備** — `__init__.py` が空で公開 API が未定義。4 ファイルに dual-import shim が重複。デモコードが `__main__` ブロックに分散(CLI と機能重複)。

## 進め方の原則

- 各フェーズは **独立した 1 PR サイズ**。常にテストグリーンを維持する。
- 破壊的変更は deprecation シム(`DeprecationWarning`)を挟んで 2 段階で行う。
- 既存規約を維持: タブインデント、日本語コメント、`uv run pytest` / `uv run ruff check .` / `uv run ruff format .`。
- `res_check_json` の「`original` ではなく `title` を検証する」不変条件と、バッチ index のカスケード防止ロジックは、移設時にコメント・テストごと運ぶ。

## 委譲可否の凡例

各タスクにモデル委譲の可否を付記する。

| 記号 | 意味 |
|---|---|
| 【S】 | **Sonnet に委譲可** — 機械的・仕様が明確・既存テストが安全網になる |
| 【O】 | **Opus に委譲可** — 局所的な設計判断を含むが、本書の指示とテストで完結する |
| 【F】 | **Fable(メインセッション)で実施** — 横断的な設計判断・不変条件の移設・ユーザー判断が絡む |

委譲する場合も、【O】のタスクはマージ前に人間または Fable のレビューを推奨。

## 決定記録

| 日付 | 決定 |
|---|---|
| 2026-07-02 | `../File_rename.py`(main_list 依存)と `../GetFile_name.py`(存在しない `main.py` を import しており既に動作不能)は **破棄** で確定。フェーズ 0 で削除済み。これにより main_list 削除(フェーズ 1)のブロッカーは解消。 |
| 2026-07-02 | 現役コンシューマは `../file_rename/rename.py` と `download.py` の 2 本(いずれも main_json 利用)。フェーズ 4/6 の移行対象。 |

---

## フェーズ 0: 安全網の整備 ✅ 実施済み (2026-07-02)

リファクタ前に「今の挙動」を固定し、後続フェーズの回帰を検知できる状態を作る。

| タスク | 委譲 | 状態 |
|---|---|---|
| `pytest-cov` を dev 依存に追加し、CI の pytest に `--cov` を追加 | 【S】 | ✅ |
| カバレッジベースラインの記録(下記) | 【S】 | ✅ |
| `clean_title` のゴールデン特性テスト追加(実在系タイトル 34 件、`tests/test_clean_title_golden.py`) | 【O】現状挙動の採取と歪みの見極めが必要 | ✅ |
| リポジトリ衛生: 化石キャッシュ(`conect.pyc` 等)の掃除、`pyproject.toml` の冗長な `indent-width` 削除 | 【S】 | ✅ |
| `.gitattributes` 追加(`* text=auto eol=lf`)と作業コピーの LF 統一 | 【S】 | ✅ |
| コンシューマ棚卸しと生死判定(決定記録参照) | 【F】ユーザー判断 | ✅ |

**メモ**:
- パースフォールバック各段・index カスケード防止・検証の不変条件は既存テストで十分カバーされていたため、特性テストの追加は `clean_title` に絞った。
- ゴールデンテストは既知の歪み(括弧外ノイズが残る、feat 除去でスペース喪失等)も **現状仕様として固定** している。改善する場合は期待値を同一コミットで更新する。
- `uv sync` は pyproject 未宣言のパッケージ(`mutagen`, `ai-sdk-python`)を venv から削除するので注意。フェーズ 6 で依存宣言を正常化するまでは `uv pip install mutagen ai-sdk-python` で復元する。
- Windows では `core.autocrlf=true` によりチェックアウトが CRLF になり、ruff 設定(`line-ending = "lf"`)と衝突して `ruff format --check` がローカルで常に失敗していた(CI は Linux なので顕在化せず)。`.gitattributes` の `* text=auto eol=lf` で恒久修正済み。既存クローンでは `git ls-files` 対象を LF へ変換する必要がある。

**カバレッジベースライン** (2026-07-02, 145 tests passed):

| モジュール | Cover | 主な未カバー箇所 |
|---|---|---|
| utils.py | 100% | — |
| cli.py | 92% | shim 分岐・エラー経路の一部 |
| main_json.py | 79% | `__main__` デモブロック、パース例外分岐 |
| main_list.py | 75% | (フェーズ 1 で削除予定) |
| connect.py | 54% | `_selftest` 一式 |
| __main__.py | 0% | エントリポイント 7 行 |
| **src+tests 合計** | **91%** | |

---

## フェーズ 1: レガシーの削除 ✅ 実施済み (2026-07-02)

土台を触る前に、守るべき面積を減らす。完了時にバージョンを 0.2.0 へ。

| タスク | 委譲 | 状態 |
|---|---|---|
| `main_list.py` + `tests/test_main_list.py` の削除 | 【S】 | ✅ |
| `connect.set_system_prompt` / `get_system_prompt` の削除(対応テストも) | 【S】 | ✅ |
| `_parse_json_response` のフォールバック発動を `logger.warning` で計測するログ追加 | 【S】 | ✅ 削除判断はフェーズ 3(【F】)で実運用の発動頻度を見て行う |
| `main_json.py` の `__main__` デモブロック削除(CLI に一本化)、未使用になった `utils.read_titles` の削除 | 【S】 | ✅ |
| CLAUDE.md / README から main_list・デモブロックの記述を削除 | 【S】 | ✅ |
| バージョン 0.2.0 | 【S】 | ✅ |

**メモ**: テストは 145 → 132 件(削除したコードのテスト分)。全緑。

---

## フェーズ 2: connect.py の再設計 — グローバル状態の排除 ✅ 実施済み (2026-07-02)

最大の構造的負債。ここを直すとテスト・CLI・後続フェーズ全てが楽になる。

| タスク | 委譲 | 状態 |
|---|---|---|
| 公開シグネチャの設計確定(`Config` / `LLMClient` のフィールドとメソッド) | 【F】 | ✅ |
| `Config` frozen dataclass + `Config.from_env()`。**import 時の `load_dotenv()` / 環境変数読みを廃止**し `from_env()` で遅延実行 | 【O】 | ✅ BASE_URL 未設定時の明示的失敗は `__post_init__` で維持 |
| `LLMClient` クラス化: `send_message()` をメソッド化し、モジュール変数 `client` / `_system_prompt` / `model` を内部状態へ吸収 | 【O】 | ✅ `api_key` 未指定時はプレースホルダを送る改善も実施(openai SDK が None を拒否するため) |
| 後方互換シム: モジュールレベル `connect.init()` / `send_message()` をデフォルトクライアント(`_default_client`)委譲の薄いラッパとして残す | 【O】 | ✅ **DeprecationWarning の付与はフェーズ 3 完了後に延期**(main_json が内部でまだ使用しており、今付けると正常経路で警告が出るため) |
| CLI の修正: `connect.model = args.model` のモジュール変数書き換えを廃止し、`init(model=...)` 引数へ | 【O】 | ✅ |
| `_selftest` を `LLMClient` ベースに書き直し | 【S】 | ✅ |
| 「`import connect` が副作用ゼロ(env 未設定でもエラーなし)」の subprocess テスト追加 | 【S】 | ✅ |

**メモ**:
- 挙動変更(意図的): 旧 `init(system_prompt=None)` は「system プロンプトなし」を意味したが、新 API では None =「未指定」として env にフォールバックする。
- **発見**: `uv run mv2title`(console script)は **元から動かない**。pyproject に `[build-system]` が無くパッケージが venv にインストールされないため。テストが通るのはルートの `__init__.py` により pytest が親ディレクトリを sys.path に挿入するという偶然の産物。恒久対策はフェーズ 4 に追加。140 テスト全緑。

---

## フェーズ 3: main_json の分解と型付きデータモデル ✅ 実施済み (2026-07-02)

| タスク | 委譲 | 状態 |
|---|---|---|
| `models.py`: `TitleInput(title, channel=None)` / `TitleResult(index, original, title, valid)` dataclass + `to_dict()` | 【O】 | ✅ `channels` 並行リストは公開 API から消滅(内部の prompt 境界にのみ残存) |
| `preprocess.py`: `clean_title` と正規表現群を utils から移設 | 【O】 | ✅ ゴールデンテスト全通過(挙動不変) |
| `prompt.py`: `make_json_prompt` / `RESPONSE_SCHEMA` / `number_titles`(旧 edit_title) / `strip_index` を移設 | 【O】 | ✅ |
| `parsing.py`: `parse_json_response` / `normalize_batch_items`(キー吸収・index 補正) | 【O】 | ✅ index カスケード防止のコメント・テストごと移設 |
| `validation.py`: `check_results`(旧 res_check_json)/ `is_title_match` / `normalize_for_match` | 【F】 | ✅ 「title を検証し original は比較しない」不変条件のコメント・回帰テストを維持 |
| `pipeline.py`: `extract_titles(titles, client, ...)` — **`LLMClient` 明示注入**(「caller が init を先に呼ぶ」暗黙の前提を廃止) | 【F】 | ✅ |
| カンマ分割フォールバックの削除判断(フェーズ 1 の計測結果を解釈) | 【F】 | ⏸ **未実施**。実運用での warning 発動実績を確認してから判断(要ユーザー確認) |
| テスト移行: `fake_send` monkeypatch → `fake_client` フィクスチャ注入 | 【O】 | ✅ 新モジュール別にテストを分割(test_parsing / test_prompt / test_preprocess / test_validation / test_pipeline)。`fake_send` はシムテスト用に縮小して残置 |
| `main_json.py` を旧 API 名の互換シム(`DeprecationWarning`)だけにする | 【S】 | ✅ `main` / `send_batches_json` / `res_check_json` を警告付き委譲に。旧「init 先呼び」契約はアダプタで維持し、既存コンシューマ(`../file_rename/rename.py`)は無変更で動作 |
| `utils.py` の解体(残るのは `chunk_list` のみ) | 【S】 | ✅ |

**メモ**: 155 テスト全緑。dict 契約の互換シムは LLM が返した余分なキーを保持しなくなった(index/original/title/valid のみ)。connect のモジュールレベルシムへの DeprecationWarning 付与は、main_json シム(アダプタ経由で使用中)が消えるフェーズ 4 で行う。

---

## フェーズ 4: 公開 API の確立とパッケージ整備 ✅ 実施済み (2026-07-02)

バージョン 0.3.0。ユーザー決定(2026-07-02): **フェーズ 6 と一括で実施**。

| タスク | 委譲 | 状態 |
|---|---|---|
| 公開 API の設計: `__init__.py` に `extract_titles`, `TitleInput`, `TitleResult`, `LLMClient`, `Config`, `__version__`, `__all__` | 【F】 | ✅ |
| パッケージングの正常化: `[build-system]`(uv_build)を追加し、モジュールを `src/mv2title/` へ移動。`uv sync` で editable インストールされ、`uv run mv2title` / `python -m mv2title` が機能 | 【F】設計 → 【O】実施 | ✅ |
| dual-import shim(`try: from . import ...`)の除去、パッケージ内 import の相対統一 | 【S】 | ✅ |
| フェーズ 2〜3 の互換シム(`connect.init()` / `send_message()` / `main_json` シム)の最終削除 | 【S】 | ✅ コンシューマ移行(フェーズ 6)と同時に実施 |
| CLAUDE.md のアーキテクチャ記述を新構成へ全面更新 | 【O】 | ✅ |

---

## フェーズ 5: 品質ゲートとドキュメント

| タスク | 委譲 | 備考 |
|---|---|---|
| 型チェッカ(pyright 推奨)を dev 依存 + CI に追加し、型エラーを解消 | 【O】 | `Any` は `parsing.py` の境界にほぼ閉じているはず |
| ruff ルール拡充(`SIM`, `C4`, `RUF`, `PT`, `ARG`)と指摘解消 | 【S】 | |
| README 刷新(新 API クイックスタート、`.env` テンプレート例の追記) | 【S】ドラフト → 【F】レビュー | 現状 `.env` のテンプレートが存在しない |
| CHANGELOG.md 新設(0.1.0 からの変更を遡って記録) | 【S】 | |

---

## フェーズ 6: コンシューマ移行 ✅ 実施済み (2026-07-02)

リポジトリ外(`../file_rename/`、独立 git リポジトリ)。コミット `da91671`。

| タスク | 委譲 | 状態 |
|---|---|---|
| `rename.py` / `download.py`: `sys.path.insert` を廃止し、新 API(`extract_titles` + `LLMClient(Config.from_env())`)へ移行 | 【O】 | ✅ `rename.make_client()` を新設し 2 スクリプトで共用。mv2title/.env の明示読み込みは維持 |
| `file_rename/` に独自 `pyproject.toml` を作成し、`mutagen` / `yt-dlp` / `python-dotenv` / mv2title(editable パス依存)を宣言 | 【O】 | ✅ `uv sync` で専用 venv を構築。フェーズ 0 メモの「uv sync が未宣言依存を消す」問題は解消(mv2title 側 venv に mutagen 等は不要になった) |

---

## リスクと順序の根拠

- **順序**: 安全網(0)→ 面積削減(1)→ 土台(2)→ 分解(3)→ API 確立(4)→ ゲート(5)。逆順にすると、消す予定のコードに型を付けたり、グローバル状態のまま分解して注入設計をやり直すことになる。
- **最大のリスクはフェーズ 2〜3 の境界**: `fake_send` フィクスチャが `connect.send_message` の monkeypatch に依存している。各フェーズで互換シムを壊さず、テスト側の移行はフェーズ 3 でまとめて行う。
- **残る要判断ポイント**: ① カンマ分割フォールバックの削除(フェーズ 3、計測後)、② shim 除去とコンシューマ移行のタイミング(フェーズ 4/6)。
