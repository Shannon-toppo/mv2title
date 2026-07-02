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

## フェーズ 2: connect.py の再設計 — グローバル状態の排除

最大の構造的負債。ここを直すとテスト・CLI・後続フェーズ全てが楽になる。

| タスク | 委譲 | 備考 |
|---|---|---|
| 公開シグネチャの設計確定(`Config` / `LLMClient` のフィールドとメソッド) | 【F】 | 後続タスクの前提。フェーズ 3 の注入設計と整合させる |
| `Config` dataclass(`base_url`, `api_key`, `model`, `system_prompt`, `timeout`, `max_retries`)+ `Config.from_env()` の実装。**import 時の `load_dotenv()` / 環境変数読みを廃止**し `from_env()` で遅延実行 | 【O】 | BASE_URL 未設定時に明示的に失敗する安全策(api.openai.com への誤送信防止)は維持 |
| `LLMClient` クラス化: `send_message()` をメソッド化し、モジュール変数 `client` / `_system_prompt` / `model` を内部状態へ吸収 | 【O】 | |
| 後方互換シム: モジュールレベル `connect.init()` / `send_message()` をデフォルトクライアント委譲の薄いラッパとして 1 バージョン残す(`DeprecationWarning`) | 【O】 | 既存テストの `fake_send`(`connect.send_message` を monkeypatch)がこの間も動くこと |
| CLI の修正: `connect.model = args.model` のモジュール変数書き換えを廃止し、`Config` 組み立て → `LLMClient` 生成へ | 【O】 | |
| `_selftest` を `LLMClient` ベースに書き直し | 【S】 | 疎通確認は実用機能なので維持 |
| 「`import connect` が副作用ゼロ(env 未設定でもエラー・警告なし)」のテスト追加 | 【S】 | |

**完了条件**: 全緑 + import 副作用ゼロのテストが通る。

---

## フェーズ 3: main_json の分解と型付きデータモデル

| タスク | 委譲 | 備考 |
|---|---|---|
| `models.py`: `TitleInput(title, channel=None)` / `TitleResult(index, original, title, valid)` dataclass + `to_dict()` | 【O】 | `channels` 並行リストと dict 契約の置き換え |
| `preprocess.py`: `clean_title` と正規表現群を utils から移設 | 【O】 | ゴールデンテストが安全網 |
| `prompt.py`: `_make_json_prompt` / `_RESPONSE_SCHEMA` / `edit_title` / `strip_index` を移設 | 【O】 | 番号付与は「プロンプトの都合」なので utils から移す |
| `parsing.py`: `_parse_json_response` / `_extract_json_substring` / キー吸収・index 補正ロジックを移設 | 【O】 | index カスケード防止のコメント・テストごと移す |
| `validation.py`: `res_check_json` / `is_title_match` / `normalize_for_match` を移設 | 【F】 | 「title を検証し original は比較しない」不変条件に触るため |
| `pipeline.py`: オーケストレーション(前処理→送信→検証→部分リトライ)+ **`client: LLMClient` 引数の導入**(「caller が init を先に呼ぶ」暗黙の前提を廃止) | 【F】 | 新公開 API の契約設計そのもの |
| カンマ分割フォールバックの削除判断(フェーズ 1 の計測結果を解釈) | 【F】 | 発動実績ゼロなら削除、`ast.literal_eval` 段は残す |
| テスト移行: `fake_send` monkeypatch → `LLMClient` のフェイク注入 | 【O】 | |
| `main_json.py` を旧 API 名の互換シム(`DeprecationWarning`)だけにする | 【S】 | |
| `utils.py` の解体(残るのは `chunk_list` 程度) | 【S】 | |

**完了条件**: 全緑 + 旧 API 経由の呼び出しにも Deprecation 警告付きで互換。

---

## フェーズ 4: 公開 API の確立とパッケージ整備

バージョン 0.3.0。

| タスク | 委譲 | 備考 |
|---|---|---|
| 公開 API の設計: `__init__.py` に `extract_titles`, `TitleInput`, `TitleResult`, `LLMClient`, `Config`, `__version__`, `__all__` | 【F】 | 名前と契約の最終決定 |
| dual-import shim(`try: from . import ...`)の除去、パッケージ内 import の相対統一 | 【S】 | コンシューマの editable install 移行(フェーズ 6)が前提。CLAUDE.md の「Preserve it」記述も同時更新 |
| フェーズ 2〜3 の互換シム(`connect.init()` ラッパ・`main_json` シム)の最終削除 | 【S】 | コンシューマ移行完了後 |
| CLAUDE.md のアーキテクチャ記述を新構成へ全面更新 | 【O】 | |

> ⚠️ 要判断: shim 除去はコンシューマ側(`../file_rename/`)の同時修正が必要。フェーズ 6 と同一 PR にするか、shim をもう 1 バージョン残すか。

---

## フェーズ 5: 品質ゲートとドキュメント

| タスク | 委譲 | 備考 |
|---|---|---|
| 型チェッカ(pyright 推奨)を dev 依存 + CI に追加し、型エラーを解消 | 【O】 | `Any` は `parsing.py` の境界にほぼ閉じているはず |
| ruff ルール拡充(`SIM`, `C4`, `RUF`, `PT`, `ARG`)と指摘解消 | 【S】 | |
| README 刷新(新 API クイックスタート、`.env` テンプレート例の追記) | 【S】ドラフト → 【F】レビュー | 現状 `.env` のテンプレートが存在しない |
| CHANGELOG.md 新設(0.1.0 からの変更を遡って記録) | 【S】 | |

---

## フェーズ 6(任意): コンシューマ移行

リポジトリ外(`../file_rename/`)のため本体とは別作業。

| タスク | 委譲 | 備考 |
|---|---|---|
| `rename.py` / `download.py`: `sys.path.insert` を editable install(`uv pip install -e`)に置換し、新 API(`extract_titles` + `LLMClient`)へ移行 | 【O】 | |
| `file_rename/` に独自 `pyproject.toml` を作成し、`mutagen` / `yt-dlp` / mv2title(パス依存)を宣言 | 【O】 | フェーズ 0 メモの「uv sync が未宣言依存を消す」問題の恒久対策 |

---

## リスクと順序の根拠

- **順序**: 安全網(0)→ 面積削減(1)→ 土台(2)→ 分解(3)→ API 確立(4)→ ゲート(5)。逆順にすると、消す予定のコードに型を付けたり、グローバル状態のまま分解して注入設計をやり直すことになる。
- **最大のリスクはフェーズ 2〜3 の境界**: `fake_send` フィクスチャが `connect.send_message` の monkeypatch に依存している。各フェーズで互換シムを壊さず、テスト側の移行はフェーズ 3 でまとめて行う。
- **残る要判断ポイント**: ① カンマ分割フォールバックの削除(フェーズ 3、計測後)、② shim 除去とコンシューマ移行のタイミング(フェーズ 4/6)。
