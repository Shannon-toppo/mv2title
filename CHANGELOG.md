# Changelog

## 0.5.0 (2026-09-12)

### 追加
- モデル名の解決とモデル差し替えの検出を `connect.py` に追加した。LM Studio は `/models` の一覧と完全一致しない名前を受けても **エラーにせず、ロード中の別モデルで黙って答える**(実測: e4b だけロードした状態で `MODEL=gemma-4-e2b` → 応答の `model` は `google/gemma-4-e4b`。`no-such-model-xyz` ですら答えた。2 つ以上ロード中なら 400 `model_not_found` になるので、サーバの状態に依存する)。
  - `fetch_model_ids(config, timeout=3.0)` — `GET {base_url}/models` を **urllib** で叩く。openai SDK の `models.list()` はボディをページ型へパースしてしまい、LM Studio が存在しないパス(`BASE_URL` の `/v1` 抜けなど)へ **HTTP 200 でエラー JSON** を返すケースを見分けられないため。ボディが `{"data": [...]}` の形であることまで検証し、駄目なら `ConnectionCheckError`。
  - `model_aliases(model_id)` / `resolve_model(model, server_ids)` — publisher 省略(`google/gemma-4-e2b` ↔ `gemma-4-e2b`)・`@quant` サフィックス・大小文字の揺れを同一視する。解決は大小文字無視の完全一致が最優先、次に表記ゆれで一致する id が **1 つだけ** のとき。候補が複数(量子化違いが並ぶ等)や一覧に無いときは決めつけず指定のまま返す。エイリアスは **比較専用** で、サーバへ送る名前には使わない。
  - `ModelCheckedClient` / `ModelMismatchError` — 応答の `model` 欄を要求と突き合わせ、別モデルなら例外。一度不一致を見たら以降は **送信せずに** 同じ例外を投げる。
  - `make_client(config, *, timeout=3.0)` — id 一覧を取って `config.model` を解決し、`ModelCheckedClient` を返す。一覧が取れなければ解決を諦めてそのまま進む(失敗理由は実際の推論呼び出しで出る)。
  - `check_endpoint(config, timeout)` — 疎通確認の素材 `(モデル id 一覧, 解決後のモデル名)` を返す。文言の組み立ては GUI / CLI 側に任せる。
  - 公開 API として `__init__.py` から再エクスポート(`fetch_model_ids` / `model_aliases` / `resolve_model` / `make_client` / `check_endpoint` / `ModelCheckedClient` / `ModelMismatchError` / `ConnectionCheckError`)。
- `cli.main()` と `connect._selftest` が `make_client` 経由でクライアントを作るようになり、CLI でもモデル解決と差し替え検出が効く。CLI はモデル不一致を終了コード 3 で報告する。

### 変更
- `pipeline.send_batches` は `ModelMismatchError` を **構造化出力の拒否として扱わない**。従来の `except Exception` はサーバが `response_format` を拒否したとみなして同じバッチをプレーンで再送するため、そのままだと違うモデルにもう一度推論させてしまう。専用の `except` で即時送出する。

### 破壊的変更
- **`Config.from_env()` が `.env` を読まなくなった。** 引数無しの `load_dotenv()` は **呼び出し元のソースファイル** から親ディレクトリを遡るため、利用側アプリが意図せず `mv2title/.env` を掴む(frozen ビルドでは cwd から遡る)。読み込みは入口の責務とし、`cli.main()` と `connect._selftest` で `load_dotenv()` を呼ぶようにした。`from_env` は `os.environ` のみを見る。
  - ライブラリとして使う側でこれに依存していた場合は、自分で `dotenv.load_dotenv()` を呼ぶか環境変数を設定すること。`python-dotenv` は引き続き依存に残る。
  - 利用側 `../file_rename/core.py` は import 時に自前で `.env` を読んでいる(`find_env_file()`)ため影響しない。同リポジトリは次回の変更で自前の `make_client` / `resolve_model` / `_ModelCheckedClient` / `check_connection` をここのものへ差し替える予定。

## 0.4.1 (2026-09-10)

### 修正
- 構造化出力(`use_schema=True`)で **1 件目しか返らない打ち切り** を修正した。原因はプロンプト文面と `RESPONSE_SCHEMA` の不一致で、`make_json_prompt` が「JSON 配列を返せ」と指示する一方、strict モードの制約からスキーマはトップレベルをオブジェクトにしており `{"results": [...]}` を強制していた。モデルは配列を書き始めたところに文法を押し付けられ、要素 1 個で辻褄を合わせて閉じてしまう。指示文を `results` オブジェクトの形に合わせた。
  - 実測(LM Studio + gemma-4-e2b, `temperature=0`, 3 件): 旧文面 / `use_schema=True` は calls=2(1/3 件で 0.4.0 の打ち切りラッチが作動)、新文面は calls=1 で 3/3(5 回とも再現)。`make_json_prompt` はスキーマあり/なしの両経路で使われるためプレーン経路も確認した。
- 文面とスキーマの対応を守るテストを追加し、`RESPONSE_SCHEMA` 直上に理由をコメントで固定した。
- CLAUDE.md の原因説明を訂正。「制約付きデコードでは思考トークンを挟めない」は誤りで、`reasoning_tokens=0` は原因ではなく症状だった。

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
