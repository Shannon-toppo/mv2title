"""
構造化出力 (JSON) を用いてタイトル変換を行うモジュール
main_list.py を参考にしつつ、LLM の出力を JSON 配列として受け取り処理します。
"""
import json
import ast
import logging
from typing import Any

try:
	from . import connect
	from . import utils
except ImportError:
	import connect  # type: ignore
	import utils    # type: ignore

logger = logging.getLogger(__name__)


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


def _make_json_prompt(batch: list[str]) -> str:
	items = "\n".join(batch)
	p = (
		"以下は番号付きのタイトル一覧です。\n"
		"各入力に対して、次の形式のJSON配列を返してください。"
		"配列の各要素はオブジェクトで、少なくともキー `index` (整数)、`original` (元の文字列)、`title` (変換後タイトル) を持ってください。\n"
		"出力は純粋な JSON の配列のみとし、余分な説明文は含めないでください。\n\n"
		"入力:\n"
		f"{items}\n"
	)
	return p


def _send_batch_raw(batch: list[str], use_schema: bool = True) -> str | None:
	response_format = _RESPONSE_SCHEMA if use_schema else None
	response = connect.send_message(_make_json_prompt(batch), response_format=response_format)
	return response.choices[0].message.content


def _extract_json_substring(s: str) -> str | None:
	start = s.find("[")
	end = s.rfind("]")
	if start != -1 and end != -1 and end > start:
		return s[start:end+1]
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
			parts = [p.strip().strip('\"\'') for p in s_inner.split(",") if p.strip()]
			return parts


def send_batches_json(
	prompts: list[str], batch_size: int = 10, debug: bool = False, use_schema: bool = True
) -> list[dict[str, Any]]:
	all_objs: list[dict[str, Any]] = []
	# base はバッチ先頭の 0-based グローバルオフセット。
	# LLM の返却件数に依存せず必ず len(batch) ずつ進めることで、
	# あるバッチの件数ズレが後続バッチの採番へ波及（カスケード）するのを防ぐ。
	base = 0
	# 構造化出力をサーバが拒否したら以降のバッチでも使わない（毎回失敗させない）。
	schema_enabled = use_schema
	for batch in utils.chunk_list(prompts, batch_size):
		try:
			raw = _send_batch_raw(batch, use_schema=schema_enabled)
		except Exception:
			if schema_enabled:
				logger.warning(
					"Structured output (response_format) failed; falling back to plain prompt.",
					exc_info=debug,
				)
				schema_enabled = False
				raw = _send_batch_raw(batch, use_schema=False)
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
) -> tuple[bool, list[dict[str, Any]]]:
	validated: list[dict[str, Any]] = [obj.copy() for obj in response]

	# 既定は invalid。件数不一致でも全件破棄せず、index ごとに検証して valid を立てる。
	for obj in validated:
		obj["valid"] = False

	length_ok = len(input_text) == len(response)
	if not length_ok and debug:
		logger.debug(
			"Error: The number of input titles does not match the number of output items. "
			"Input length: %d, Output length: %d", len(input_text), len(response)
		)

	# 配列順ではなく index (グローバル通し番号) で入力と突き合わせる
	by_index: dict[int, dict[str, Any]] = {
		obj["index"]: obj
		for obj in validated
		if isinstance(obj.get("index"), int) and not isinstance(obj.get("index"), bool)
	}

	ok_list: list[bool] = []
	for i in range(len(input_text)):
		obj = by_index.get(i + 1)
		if obj is None:
			ok_list.append(False)
			if debug:
				logger.debug("Error: No output item with index %d", i + 1)
			continue
		orig = obj.get("original", "")
		# 比較: 少なくとも一方が他方を含む形で一致していることを期待する
		ok = input_text[i] in orig or orig in input_text[i]
		obj["valid"] = ok
		ok_list.append(ok)
		if not ok and debug:
			logger.debug(
				"Error: Input title not found in output at index %d: %s vs %s",
				i, input_text[i], orig
			)

	return (length_ok and all(ok_list)), validated


def main(
	text: list[str],
	batch_size: int = 10,
	bypass_check: bool = False,
	debug_mode: bool = False,
	use_schema: bool = True,
) -> list[dict[str, Any]]:
	prompts = utils.edit_title(text)
	responses = send_batches_json(
		prompts, batch_size=batch_size, debug=debug_mode, use_schema=use_schema
	)
	ok, validated = res_check_json(text, responses, debug_mode)
	if bypass_check or ok:
		return validated
	raise ValueError("Output does not match input titles.")


if __name__ == "__main__":
	test_list_2 = [
		"暴飲暴食P 「うそつきマカロン」feat. 重音テト ",
		"あんずの花/ すりぃ feat.ねね(Official Music Video)",
		"【初音ミク】幸福でも不幸でもない平凡で幸福な日々と幸福でも不幸でもある非凡で不幸な日々【オリジナル曲】by HaTa",
		"ヨルシカ「ただ君に晴れ」Music Video",
		"[self cover] The Beast. /スペクタルP feat 可不",
		"MIMI - サイエンス (feat.重音テトSV)",
		"『ソルティメロウ』 / feat. 可不",
		"『天使の涙』 / feat.初音ミク",
		"『アンコールダンス』/ feat. 重音テトSV",
		"『夜と幸せ』/ feat. 詩の出素。",
		"『桜の戦略 』/ MIMI feat. マス",
		"『お砂糖哀歌』 / feat. 初音ミク",
		"『恋しくなったら手を叩こう』/ MIMI feat.花鏡紅璃",
		"『恋しくなったら手を叩こう』 / feat.重音テトSV",
		"「ヒューマとニズム」-Hata",
		"月詠み『花と散る』Music Video"
	]

	connect.init()
	out = main(test_list_2, batch_size=10, bypass_check=False, debug_mode=False)
	print(json.dumps(out, ensure_ascii=False, indent=2))
