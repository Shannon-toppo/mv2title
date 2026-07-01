"""
構造化出力 (JSON) を用いてタイトル変換を行うモジュール
main_list.py を参考にしつつ、LLM の出力を JSON 配列として受け取り処理します。
"""

import ast
import json
import logging
from typing import Any

try:
	from . import connect, utils
except ImportError:
	import connect  # type: ignore
	import utils  # type: ignore

logger = logging.getLogger(__name__)

# 部分リトライ時のサンプリング温度。temperature 0.0 のままだと同じ入力に対して
# 同じ(失敗した)出力が返りやすいため、リトライでは少しだけ揺らぎを与える。
_RETRY_TEMPERATURE = 0.4


# 構造化出力 (OpenAI 互換 json_schema) のスキーマ。
# strict モードはトップレベルがオブジェクトである必要があるため results 配列で包む。
_RESPONSE_SCHEMA: dict[str, Any] = {
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


def _make_json_prompt(batch: list[str], channels: list[str | None] | None = None) -> str:
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


def _send_batch_raw(
	batch: list[str],
	channels: list[str | None] | None = None,
	use_schema: bool = True,
	temperature: float = 0.0,
) -> str | None:
	response_format = _RESPONSE_SCHEMA if use_schema else None
	response = connect.send_message(
		_make_json_prompt(batch, channels=channels),
		response_format=response_format,
		temperature=temperature,
	)
	return response.choices[0].message.content


def _extract_json_substring(s: str) -> str | None:
	start = s.find("[")
	end = s.rfind("]")
	if start != -1 and end != -1 and end > start:
		return s[start : end + 1]
	return None


def _parse_json_response(raw: str | None, debug: bool = False) -> Any:
	if raw is None:
		return None
	s = raw.strip()
	try:
		data = json.loads(s)
		return data
	except Exception:
		sub = _extract_json_substring(s)
		if sub:
			try:
				data = json.loads(sub)
				return data
			except Exception:
				if debug:
					logger.debug("JSON parsing failed even after extracting substring")
		# フォールバック: Python リテラル風やカンマ区切りの文字列リストを処理
		try:
			parsed = ast.literal_eval(s)
			return parsed
		except Exception:
			# 最後の手段: カンマで分割して文字列リストにする
			if s.startswith("[") and s.endswith("]"):
				s_inner = s[1:-1]
			else:
				s_inner = s
			parts = [p.strip().strip("\"'") for p in s_inner.split(",") if p.strip()]
			return parts


def send_batches_json(
	prompts: list[str],
	channels: list[str | None] | None = None,
	batch_size: int = 10,
	debug: bool = False,
	use_schema: bool = True,
	temperature: float = 0.0,
) -> list[dict[str, Any]]:
	all_objs: list[dict[str, Any]] = []
	# base はバッチ先頭の 0-based グローバルオフセット。
	# LLM の返却件数に依存せず必ず len(batch) ずつ進めることで、
	# あるバッチの件数ズレが後続バッチの採番へ波及（カスケード）するのを防ぐ。
	base = 0
	# 構造化出力をサーバが拒否したら以降のバッチでも使わない（毎回失敗させない）。
	schema_enabled = use_schema
	for batch in utils.chunk_list(prompts, batch_size):
		batch_channels = channels[base : base + len(batch)] if channels else None
		try:
			raw = _send_batch_raw(batch, channels=batch_channels, use_schema=schema_enabled, temperature=temperature)
		except Exception:
			if schema_enabled:
				logger.warning(
					"Structured output (response_format) failed; falling back to plain prompt.",
					exc_info=debug,
				)
				schema_enabled = False
				raw = _send_batch_raw(batch, channels=batch_channels, use_schema=False, temperature=temperature)
			else:
				raise
		parsed = _parse_json_response(raw, debug=debug)

		# 構造化出力は {"results": [...]} 形式で包まれて返るため取り出す。
		if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
			parsed = parsed["results"]

		if parsed is None:
			logger.warning("Batch parse returned None, skipping %d items: %s", len(batch), batch)
			base += len(batch)
			continue

		# parsed がリストか辞書かを判定して正規化（それ以外は破棄）
		if isinstance(parsed, dict):
			items: list[Any] = [parsed]
		elif isinstance(parsed, (list, tuple)):
			items = list(parsed)
		else:
			logger.warning("Unexpected parsed type %s, skipping %d items: %s", type(parsed), len(batch), batch)
			base += len(batch)
			continue

		normalized: list[dict[str, Any]] = []
		for pos, item in enumerate(items):
			# LLM は index をバッチごとに 1 から振り直す（バッチ内ローカル番号）ため、
			# それを base に足してリスト全体のグローバル番号へ変換する。
			# index がバッチ内の妥当な範囲 (1..len(batch)) なら並び替えの手がかりとして尊重し、
			# 範囲外・欠落・非整数なら配列順 (pos) にフォールバックする。
			local_pos = pos
			if isinstance(item, dict):
				idx = item.get("index")
				if isinstance(idx, bool):
					idx = None
				elif not isinstance(idx, int):
					try:
						idx = int(idx)  # type: ignore[arg-type]
					except (TypeError, ValueError):
						idx = None
				if isinstance(idx, int) and 1 <= idx <= len(batch):
					local_pos = idx - 1
			global_index = base + local_pos + 1
			# 対応する元タイトル。LLM が echo した original ではなく、番号を剥がした入力を正とする。
			orig_fallback = utils.strip_index(batch[local_pos]) if local_pos < len(batch) else ""
			if isinstance(item, dict):
				obj = item.copy()
				obj["index"] = global_index
				# LLM は番号付き入力をそのまま echo しがちなので、元タイトルは常に入力側を採用する。
				obj["original"] = orig_fallback
				if "title" not in obj:
					# try other possible keys
					for k in ("new_title", "name", "video_title"):
						if k in obj:
							obj["title"] = obj[k]
							break
					else:
						obj["title"] = ""
				normalized.append(obj)
			else:
				# 文字列の場合は batch の対応する元タイトルと組にする
				normalized.append({"index": global_index, "original": orig_fallback, "title": str(item)})

		all_objs.extend(normalized)
		base += len(batch)
		if debug:
			logger.debug("raw: %s", raw)
			logger.debug("parsed items: %s", normalized)

	return all_objs


def res_check_json(
	input_text: list[str],
	response: list[dict[str, Any]],
	debug: bool = False,
	cleaned: list[str] | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
	"""LLM 出力を入力と突き合わせて検証する。

	Args:
		input_text: 呼び出し元が渡した元タイトル（前処理前）。
		response: send_batches_json の出力。
		cleaned: 前処理後のタイトル（preprocess 有効時）。title の照合先として
			input_text と併用する。省略時は input_text のみと照合。
	Returns:
		(all_ok, validated)。validated は **入力と同数・同順**（index = 位置+1）で、
		対応する出力が無い入力には title 空のプレースホルダを置く。余分な出力や
		重複 index（先勝ち）は捨てられる。各要素の検証は title と入力タイトルの
		部分文字列関係（NFKC 正規化 + casefold 後）で行い、valid フラグを立てる。
	"""
	sources = cleaned if cleaned is not None else input_text

	# 配列順ではなく index (グローバル通し番号) で入力と突き合わせる。重複 index は先勝ち。
	by_index: dict[int, dict[str, Any]] = {}
	for obj in response:
		idx = obj.get("index")
		if isinstance(idx, bool) or not isinstance(idx, int):
			continue
		by_index.setdefault(idx, obj)

	length_ok = len(input_text) == len(response)
	if not length_ok and debug:
		logger.debug(
			"Error: The number of input titles does not match the number of output items. "
			"Input length: %d, Output length: %d",
			len(input_text),
			len(response),
		)

	validated: list[dict[str, Any]] = []
	all_ok = length_ok
	for i, raw_title in enumerate(input_text):
		obj = by_index.get(i + 1)
		if obj is None:
			if debug:
				logger.debug("Error: No output item with index %d", i + 1)
			validated.append({"index": i + 1, "original": raw_title, "title": "", "valid": False})
			all_ok = False
			continue
		out = obj.copy()
		out["index"] = i + 1
		# original は前処理後のタイトルではなく、呼び出し元が渡した元タイトルへ戻す。
		out["original"] = raw_title
		title = str(out.get("title") or "")
		# LLM が生成した title が入力（または前処理後タイトル）の部分文字列に
		# なっていることを検証する。original 同士の比較では LLM 出力を検証した
		# ことにならない点に注意（過去にその恒真チェックで形骸化していた）。
		ok = utils.is_title_match(title, raw_title, sources[i])
		out["valid"] = ok
		validated.append(out)
		all_ok = all_ok and ok
		if not ok and debug:
			logger.debug("Error: Output title does not match input at index %d: %r vs %r", i, title, raw_title)

	return all_ok, validated


def main(
	text: list[str],
	channels: list[str | None] | None = None,
	batch_size: int = 10,
	bypass_check: bool = False,
	debug_mode: bool = False,
	use_schema: bool = True,
	preprocess: bool = True,
	retry_invalid: int = 1,
) -> list[dict[str, Any]]:
	"""タイトル一覧から曲名を推論する。

	Args:
		channels: 各タイトルに対応するチャンネル名のリスト（省略可）。
			指定時はアーティスト名のヒントとして LLM プロンプトに含める。
		preprocess: True なら LLM 送信前に utils.clean_title で定型ノイズ
			（(Official Music Video)、【MV】、feat. ～ など）を除去する。
		retry_invalid: 検証に失敗した項目だけを再問い合わせする回数。0 で無効。
			bypass_check=True のときはリトライしない。
	Returns:
		入力と同数・同順の dict のリスト（index / original / title / valid）。
	Raises:
		ValueError: リトライ後も検証に失敗した場合（bypass_check=False 時のみ）。
			channels の長さが text と一致しない場合。
	"""
	if channels is not None and len(channels) != len(text):
		raise ValueError(f"channels の長さ ({len(channels)}) が text の長さ ({len(text)}) と一致しません。")
	cleaned = [utils.clean_title(t) for t in text] if preprocess else list(text)
	prompts = utils.edit_title(cleaned)
	responses = send_batches_json(
		prompts, channels=channels, batch_size=batch_size, debug=debug_mode, use_schema=use_schema
	)
	ok, validated = res_check_json(text, responses, debug_mode, cleaned=cleaned)

	# valid=False の項目だけを再問い合わせする部分リトライ。
	attempts = 0
	while not ok and not bypass_check and attempts < retry_invalid:
		attempts += 1
		invalid_pos = [i for i, obj in enumerate(validated) if not obj.get("valid")]
		retry_cleaned = [cleaned[i] for i in invalid_pos]
		retry_channels = [channels[i] for i in invalid_pos] if channels else None
		if debug_mode:
			logger.debug("Retrying %d invalid items (attempt %d)", len(invalid_pos), attempts)
		retry_resp = send_batches_json(
			utils.edit_title(retry_cleaned),
			channels=retry_channels,
			batch_size=batch_size,
			debug=debug_mode,
			use_schema=use_schema,
			temperature=_RETRY_TEMPERATURE,
		)
		_, retry_validated = res_check_json(
			[text[i] for i in invalid_pos], retry_resp, debug_mode, cleaned=retry_cleaned
		)
		for j, obj in enumerate(retry_validated):
			if obj.get("valid"):
				# サブセット内の通し番号からリスト全体の位置へ戻す
				obj["index"] = invalid_pos[j] + 1
				validated[invalid_pos[j]] = obj
		ok = all(obj.get("valid") for obj in validated)

	if bypass_check or ok:
		return validated
	raise ValueError("Output does not match input titles.")


if __name__ == "__main__":
	import os

	# デモ用の入力はリポジトリ管理外の test.json（タイトル＋チャンネル名）から読み込む。
	# test.json が無ければ従来の test.txt（1 行 1 タイトル）にフォールバックする。
	_dir = os.path.dirname(__file__)
	_json_file = os.path.join(_dir, "test.json")
	_txt_file = os.path.join(_dir, "test.txt")

	if os.path.exists(_json_file):
		with open(_json_file, encoding="utf-8") as _f:
			_data = json.load(_f)
		test_list_2 = [str(item["title"]).strip() for item in _data if str(item.get("title", "")).strip()]
		test_channels: list[str | None] | None = [
			str(item["channel"]).strip() if item.get("channel") is not None else None
			for item in _data
			if str(item.get("title", "")).strip()
		]
	else:
		test_list_2 = utils.read_titles(_txt_file)
		test_channels = None

	connect.init()
	out = main(test_list_2, channels=test_channels, batch_size=10, bypass_check=False, debug_mode=False)
	print(json.dumps(out, ensure_ascii=False, indent=2))
