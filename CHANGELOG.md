# Changelog

## 0.4.0 (2026-09-10)

### 修正
- `bypass_check=True` のとき部分リトライが走らず、欠けた項目が空文字のまま返る問題を修正。`bypass_check` と `retry_invalid` の責務を分離し、`bypass_check` は **最後に `ValueError` を投げるかどうか** だけを制御するようにした。リトライの実施可否は `retry_invalid` が持つ(`retry_invalid=0` で無効)。
  - 背景: 構造化出力(`response_format`)を付けると、モデルが配列の 1 件目だけ出して停止する。実測(LM Studio + gemma-4-e2b)では `finish_reason=stop` / `completion_tokens=37` / `reasoning_tokens=0` で 1 要素のみ。`response_format` を外すと同条件で全件返る(`reasoning_tokens=555`)。制約付きデコード下では思考トークンを挟めず打ち切られるため、**schema を付ける限り決定的に再現する**。
  - 症状: `extract_titles(..., batch_size=5, bypass_check=True)` に 2 件以上渡すと 1 件目以外の `title` が空文字で返っていた(`n=5` → 1 件目のみ `valid=True`)。
- 部分リトライを **常にプレーンプロンプト(`use_schema=False`)** で送るようにした。打ち切りは決定的なので、従来の「温度だけ上げて同じ schema で問い直す」では回復できない。
- リトライ対象を失敗の質で 2 群に分けるようにした。`missing`(応答にその項目が無く空プレースホルダで埋まった)は 1 回目は `temperature=0.0` のまま(schema を外すだけで回復するため)、2 回目以降と `mismatch`(`title` は返ったが `is_title_match` に落ちた)は `_RETRY_TEMPERATURE`(0.4)で問い直す。

### 変更
- `send_batches` の構造化出力ラッチを拡張。従来はサーバが `response_format` を **拒否した(例外)** ときだけ以降のバッチで無効化していたが、**200 で返ったが件数が入力より少ない**(打ち切り)場合も同様にラッチするようにした。大きいリストで毎バッチ 1 件しか返らない無駄打ちを避けられる(例: 12 件 / `batch_size=5` のシミュレーションで LLM 呼び出しは 4 回)。打ち切ったバッチ自体の欠落分は `extract_titles` の部分リトライが回収する。

### 互換性
- `extract_titles` のシグネチャと戻り値の契約(入力と同数・同順)は不変。
- `bypass_check=True` の呼び出しで LLM への往復が増えることがある(欠けた項目の回収を試みるため)。往復を増やしたくない場合は `retry_invalid=0` を指定する。docstring にも明記した。
- 利用側(`../file_rename/core.py`)の回避策 `_retry_missing_titles`(空で返った項目だけを `use_schema=False` で拾い直す)は、本修正でライブラリ側が空の項目を返さなくなるため自然に no-op になる。二重リトライにはならないので、動作確認のうえ将来的に削除してよい。

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
