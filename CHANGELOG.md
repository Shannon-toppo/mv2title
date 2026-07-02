# Changelog

## 0.3.0 (2026-07-02)

### 破壊的変更
- 旧 API を削除: `main_json.main()` / `send_batches_json()` / `res_check_json()`、`connect.init()` / `connect.send_message()`。`extract_titles()` + `LLMClient(Config.from_env())` へ移行してください。
- `channels` 並行リスト引数を廃止し、`TitleInput(title, channel)` に置き換え。
- パッケージを標準の src レイアウト(`src/mv2title/`)へ移動し、`[build-system]`(uv_build)を追加。dual-import shim を全廃(利用側は editable インストールで参照する)。

### 追加
- 公開 API を `__init__.py` に定義: `extract_titles` / `TitleInput` / `TitleResult` / `LLMClient` / `Config` / `__version__`。
- console script `mv2title` と `python -m mv2title` が動作するように(従来はパッケージ未インストールのため実は動いていなかった)。
- 型チェック(pyright)を導入し CI に追加。ruff ルールを拡充(`SIM` / `C4` / `RUF` / `PT` / `ARG`)。

## 0.2.0 (2026-07-02)

- 非推奨だった `main_list.py`(プレーンリスト契約の旧実装)を削除。
- `connect.py` を `Config`(frozen dataclass)+ `LLMClient` へ再設計。import 時の `load_dotenv()` / 環境変数読みを廃止し、`Config.from_env()` で遅延実行。
- `main_json.py` を責務別モジュール(`models` / `preprocess` / `prompt` / `parsing` / `validation` / `pipeline`)に分解し、`pipeline.extract_titles()` を新設(この時点では `main_json` は互換シムとして残存)。
- パースフォールバック(`ast.literal_eval` / カンマ分割)の発動を warning で計測するログを追加(発動実績ゼロを確認後に削除予定)。
- 開発基盤: `pytest-cov` によるカバレッジ計測、`clean_title` のゴールデン特性テスト(実在系タイトル 34 件)、`.gitattributes` による LF 強制(Windows の autocrlf 環境で `ruff format --check` が落ちる問題の恒久修正)。

## 0.1.0

- 初期リリース: `main_json` / `main_list` / `connect` / `utils`、CLI(`cli.py`)、チャンネル名ヒント対応。
