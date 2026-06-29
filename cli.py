"""
コマンドラインから mv2title を実行するエントリポイント。

入力ソース（優先順位）:
  1. 位置引数で渡されたタイトル（例: `mv2title "曲A" "曲B"`）
  2. -f/--input-file で指定したファイル（1 行 1 タイトル）
  3. 標準入力（パイプやリダイレクト。例: `cat titles.txt | mv2title`）

出力:
  --format json|titles|tsv で切り替え、-o/--output でファイルへ書き出し可能。
"""

import argparse
import json
import logging
import sys
from typing import Any

try:
	from . import connect, main_json
except ImportError:
	import connect  # type: ignore
	import main_json  # type: ignore


def _read_titles(args: argparse.Namespace) -> list[str]:
	"""位置引数 → -f ファイル → 標準入力 の順でタイトル一覧を読み取る。"""
	if args.titles:
		lines = list(args.titles)
	elif args.input_file:
		with open(args.input_file, encoding="utf-8") as f:
			lines = f.readlines()
	elif not sys.stdin.isatty():
		lines = sys.stdin.readlines()
	else:
		lines = []
	# 前後空白と空行を除去
	return [line.strip() for line in lines if line.strip()]


def _format_output(results: list[dict[str, Any]], fmt: str) -> str:
	"""検証結果リストを指定フォーマットの文字列にする。"""
	if fmt == "json":
		return json.dumps(results, ensure_ascii=False, indent=2)
	if fmt == "titles":
		return "\n".join(str(r.get("title", "")) for r in results)
	if fmt == "tsv":
		rows = ["index\toriginal\ttitle\tvalid"]
		for r in results:
			rows.append(f"{r.get('index', '')}\t{r.get('original', '')}\t{r.get('title', '')}\t{r.get('valid', '')}")
		return "\n".join(rows)
	raise ValueError(f"未知の出力フォーマット: {fmt}")


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		prog="mv2title",
		description="ノイズの多い音楽動画タイトルから曲名を推論します（ローカル LLM 使用）。",
	)
	parser.add_argument(
		"titles",
		nargs="*",
		help="変換するタイトル。省略時は -f または標準入力から読み取ります。",
	)
	parser.add_argument(
		"-f",
		"--input-file",
		help="1 行 1 タイトルの入力ファイル。",
	)
	parser.add_argument(
		"-o",
		"--output",
		help="結果の書き出し先ファイル。省略時は標準出力。",
	)
	parser.add_argument(
		"--format",
		choices=("json", "titles", "tsv"),
		default="json",
		help="出力フォーマット（既定: json）。",
	)
	parser.add_argument(
		"-b",
		"--batch-size",
		type=int,
		default=10,
		help="1 回の LLM 呼び出しで処理する件数（既定: 10）。",
	)
	parser.add_argument(
		"--bypass-check",
		action="store_true",
		help="入出力の検証をスキップし、結果をそのまま返します。",
	)
	parser.add_argument(
		"--no-schema",
		action="store_true",
		help="構造化出力 (json_schema) を使わず、プレーンプロンプトで問い合わせます。",
	)
	parser.add_argument(
		"--no-preprocess",
		action="store_true",
		help="LLM 送信前の定型ノイズ除去（(Official Music Video)、【MV】、feat. ～ など）を無効化します。",
	)
	parser.add_argument(
		"--retry",
		type=int,
		default=1,
		metavar="N",
		help="検証に失敗した項目のみ再問い合わせする回数（既定: 1。0 で無効）。",
	)
	parser.add_argument(
		"--timeout",
		type=float,
		metavar="SEC",
		help="LLM リクエストのタイムアウト秒数（既定: 120）。",
	)
	parser.add_argument(
		"--base-url",
		help="LLM エンドポイント。省略時は .env の BASE_URL を使用します。",
	)
	parser.add_argument(
		"--model",
		help="使用するモデル名。省略時は .env の MODEL を使用します。",
	)
	parser.add_argument(
		"--debug",
		action="store_true",
		help="デバッグログを有効化します。",
	)
	return parser


def main(argv: list[str] | None = None) -> int:
	parser = build_parser()
	args = parser.parse_args(argv)

	logging.basicConfig(
		level=logging.DEBUG if args.debug else logging.WARNING,
		format="%(levelname)s:%(name)s:%(message)s",
	)

	titles = _read_titles(args)
	if not titles:
		parser.error("タイトルが指定されていません。位置引数・-f ファイル・標準入力のいずれかで渡してください。")

	init_kwargs: dict[str, Any] = {"base_url": args.base_url or connect.url}
	if args.timeout is not None:
		init_kwargs["timeout"] = args.timeout
	try:
		connect.init(**init_kwargs)
	except ValueError as e:
		print(f"エラー: {e}", file=sys.stderr)
		return 2

	if args.model:
		connect.model = args.model

	try:
		results = main_json.main(
			titles,
			batch_size=args.batch_size,
			bypass_check=args.bypass_check,
			debug_mode=args.debug,
			use_schema=not args.no_schema,
			preprocess=not args.no_preprocess,
			retry_invalid=args.retry,
		)
	except ValueError as e:
		print(f"検証エラー: {e}", file=sys.stderr)
		return 1

	text = _format_output(results, args.format)
	if args.output:
		with open(args.output, "w", encoding="utf-8") as f:
			f.write(text + "\n")
	else:
		print(text)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
