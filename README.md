# mv2title
>[!WARNING]
>このプロジェクトは発展途上であり、仕様の破壊的変更や互換性の消失などがあるかもしれません。
### 概要
YoutubeなどのMVのタイトルから、曲名を推測するライブラリです。
推測にはローカルLLMを使用します。(OpenAI互換のAPIが使えれば、オンラインでもできると思います。(未確認))
また、LLMの出力の正当性を検証します。

### 準備
1. このライブラリを使用したい場所に置く。
2. LM studioやllama.cppなどでLLMをホストする。
3. リポジトリ直下に `.env` を作成し、以下のキーを設定する（`BASE_URL` のみ必須）。
   ```
   BASE_URL=http://127.0.0.1:1234/v1/
   API_KEY=dummy
   SYSTEM_PROMPT=あなたはタイトル分類の専門家です。与えられたMVのタイトルから曲名を抜き出してください。
   MODEL=gemma-4-e2b-it
   ```
   ローカルサーバの場合 `API_KEY` は任意の文字列で構いません。`SYSTEM_PROMPT` 省略時は `connect.init(system_prompt=...)` で渡すか、未指定のまま `send_message` 呼び出し時に上書きしてください。
4. `uv sync` で依存をインストールする。

### 使い方
`connect.init()` を呼んでから `main_json.main()` にリスト形式でタイトルを渡すと、**入力と同数・同順**の dict のリスト（`{index, original, title, valid}`）が返ります。

```python
from mv2title import connect, main_json

connect.init()
results = main_json.main(["アーティスト『曲名』(Official Music Video)"])
# => [{"index": 1, "original": "アーティスト『曲名』(Official Music Video)",
#      "title": "曲名", "valid": True}]
```

LLMにはgemma4-e2b-it(Q4)([Hugging Face](https://huggingface.co/lmstudio-community/gemma-4-E2B-it-GGUF))を使用しました。

`main_json.main()` のオプション

| オプション名 | 初期値 | 備考 |
|:------------|:-----:|:-----|
|batch_size|10|入力リストが長い場合に、いくつで分割するかを選択できます。
|bypass_check|False|検証に失敗しても例外を出さず結果を返します（各項目の `valid` フラグは付与されます）。
|preprocess|True|LLM 送信前に定型ノイズ（`(Official Music Video)`、`【MV】`、`feat. ～` など）を正規表現で除去します。`False` で無効化できます。
|retry_invalid|1|検証に失敗した項目**だけ**を再問い合わせする回数。`0` で無効。リトライ時は temperature を少し上げ、同じ失敗の再発を避けます。
|use_schema|True|OpenAI 互換の構造化出力（json_schema）を使います。サーバが拒否した場合は自動でプレーンプロンプトにフォールバックします。
|debug_mode|False|`logging` によるデバッグログを有効化します。

接続まわりのオプション（`connect.init()`）

| オプション名 | 初期値 | 備考 |
|:------------|:-----:|:-----|
|timeout|120.0|リクエスト全体のタイムアウト秒数。
|max_retries|2|一時的エラー（接続失敗・429・5xx）時の再試行回数。openai SDK が指数バックオフ付きで処理します。

`connect.send_message()` には `max_tokens` も指定できます（省略時はサーバ既定）。

### CLI
```
mv2title "タイトル1" "タイトル2"
mv2title -f titles.txt --format tsv
cat titles.txt | mv2title --format titles
```
主なフラグ: `--no-preprocess` / `--retry N` / `--timeout SEC` / `--no-schema` / `--bypass-check` / `-b N` / `-o FILE` / `--debug`

### 検証ロジック
出力の各項目について以下を確認し、`valid` フラグを立てます。文字列比較は **NFKC 正規化 + casefold + 空白圧縮** 後に行うため、全角/半角や大文字小文字の違いは吸収されます。
1. 入力と同じ `index` の項目が出力に存在する。
2. `title` が空でなく、`title` と入力タイトル（または前処理後タイトル）のどちらかが他方を含む。

全項目が valid かつ件数が一致したときのみ全体を正当と判断します。失敗時は `retry_invalid` 回まで失敗項目のみを再問い合わせし、それでも失敗が残れば `ValueError` を送出します（`bypass_check=True` の場合は送出せずそのまま返します）。

### main_list について（非推奨）
`main_list.py` は LLM 出力をプレーンなリスト文字列として受け取る旧実装で、現在は呼び出すと `DeprecationWarning` が出ます。将来のリリースで削除予定のため、`main_json` を使用してください。

### 今後の開発方針（Roadmap）
実装予定だが未着手の項目:

1. **開発基盤の整備** — ruff の導入、GitHub Actions による CI（pytest + ruff）、`pyproject.toml` のメタデータ（description 等）の整備。
2. **配布形態の改善** — 消費者スクリプト（`../file_rename/` など）が `sys.path` 操作でパッケージを参照している現状を、editable インストール（`uv pip install -e`）に置き換える。あわせて `mutagen` / `yt-dlp` を optional-dependencies（extras。例: `mv2title[rename]`）として宣言する。
3. **pydantic によるレスポンスモデル化** — `_parse_json_response` の多段フォールバックと手書きのキー正規化（`new_title`/`name`/`video_title` → `title`）を pydantic モデル + validator に置き換え、パース処理の見通しを良くする。

### ライセンス
MIT
