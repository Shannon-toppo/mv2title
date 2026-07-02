"""LLM プロンプトの組み立て(番号付与・チャンネルヒント・構造化出力スキーマ)。"""

import re
from collections.abc import Sequence
from typing import Any

_INDEX_PREFIX = re.compile(r"^\d+\.")

# 構造化出力 (OpenAI 互換 json_schema) のスキーマ。
# strict モードはトップレベルがオブジェクトである必要があるため results 配列で包む。
RESPONSE_SCHEMA: dict[str, Any] = {
	"type": "json_schema",
	"json_schema": {
		"name": "title_extraction",
		"strict": True,
		"schema": {
			"type": "object",
			"properties": {
				"results": {
					"type": "array",
					"items": {
						"type": "object",
						"properties": {
							"index": {"type": "integer"},
							"original": {"type": "string"},
							"title": {"type": "string"},
						},
						"required": ["index", "original", "title"],
						"additionalProperties": False,
					},
				}
			},
			"required": ["results"],
			"additionalProperties": False,
		},
	},
}


def number_titles(arr: list[str]) -> list[str]:
	"""番号を付けたタイトル一覧(例: 1.タイトル)を返します。

	LLM が出力を入力に対応付けられるよう、1-based の採番を行う。
	"""
	return [f"{i + 1}.{title}" for i, title in enumerate(arr)]


def strip_index(title: str) -> str:
	"""number_titles が付与した先頭の "N." 番号を1つだけ取り除きます（無ければそのまま）。"""
	return _INDEX_PREFIX.sub("", title, count=1)


def make_json_prompt(batch: list[str], channels: Sequence[str | None] | None = None) -> str:
	"""番号付きタイトルのバッチから LLM への指示文を組み立てる。

	channels が指定されている場合、各項目に `[チャンネル名]` プレフィックスを
	付与し、アーティスト名のヒントとして LLM に渡す。
	"""
	has_channel = channels is not None and any(ch and ch.strip() for ch in channels)
	lines: list[str] = []
	for i, item in enumerate(batch):
		ch = channels[i] if channels and i < len(channels) else None
		if ch and ch.strip():
			dot = item.find(".")
			lines.append(f"{item[: dot + 1]}[{ch.strip()}] {item[dot + 1 :]}")
		else:
			lines.append(item)
	items = "\n".join(lines)
	channel_hint = (
		"チャンネル名が [チャンネル名] の形式で付与されている場合があります。"
		"チャンネル名はアーティスト名の手がかりとして使い、曲名のみを抽出してください。\n"
		if has_channel
		else ""
	)
	p = (
		"以下は番号付きのタイトル一覧です。\n"
		f"{channel_hint}"
		"各入力に対して、次の形式のJSON配列を返してください。"
		"配列の各要素はオブジェクトで、少なくともキー `index` (整数)、`original` (元の文字列)、`title` (変換後タイトル) を持ってください。\n"
		"出力は純粋な JSON の配列のみとし、余分な説明文は含めないでください。\n\n"
		"入力:\n"
		f"{items}\n"
	)
	return p
