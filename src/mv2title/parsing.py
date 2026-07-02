"""LLM 応答のパースと正規化。

信頼できない LLM 出力を扱う境界層。`Any` 型はこのモジュールにほぼ閉じる。
"""

import ast
import json
import logging
from typing import Any

from . import prompt

logger = logging.getLogger(__name__)


def _extract_json_substring(s: str) -> str | None:
	start = s.find("[")
	end = s.rfind("]")
	if start != -1 and end != -1 and end > start:
		return s[start : end + 1]
	return None


def parse_json_response(raw: str | None, debug: bool = False) -> Any:
	"""LLM の生応答を多段フォールバックでパースする。

	1. そのまま JSON としてパース
	2. 角括弧の部分文字列を抽出してパース(応答に説明文が混ざる場合)
	3. `ast.literal_eval`(単引用符の Python リテラル風)
	4. カンマ分割(最後の手段)

	3・4 は main_list 時代の遺産で削除候補のため、発動したら warning で計測する
	(docs/refactoring-plan.md フェーズ 3 で発動実績を見て削除判断)。
	"""
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
		try:
			parsed = ast.literal_eval(s)
			logger.warning("parse fallback fired: ast.literal_eval (削除候補の計測ログ)")
			return parsed
		except Exception:
			s_inner = s[1:-1] if s.startswith("[") and s.endswith("]") else s
			parts = [p.strip().strip("\"'") for p in s_inner.split(",") if p.strip()]
			logger.warning("parse fallback fired: comma-split (削除候補の計測ログ)")
			return parts


def normalize_batch_items(
	parsed: Any,
	batch: list[str],
	base: int,
	debug: bool = False,
) -> list[dict[str, Any]]:
	"""1 バッチ分のパース結果を {index, original, title} の dict リストへ正規化する。

	Args:
		parsed: parse_json_response の出力。
		batch: このバッチの番号付き入力タイトル。
		base: バッチ先頭の 0-based グローバルオフセット。
	Returns:
		正規化済み dict のリスト。パース結果が使えない場合は空リスト
		(その場合は warning を出し、このバッチの入力は出力無し扱いになる)。
	"""
	# 構造化出力は {"results": [...]} 形式で包まれて返るため取り出す。
	if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
		parsed = parsed["results"]

	if parsed is None:
		logger.warning("Batch parse returned None, skipping %d items: %s", len(batch), batch)
		return []

	# parsed がリストか辞書かを判定して正規化(それ以外は破棄)
	if isinstance(parsed, dict):
		items: list[Any] = [parsed]
	elif isinstance(parsed, (list, tuple)):
		items = list(parsed)
	else:
		logger.warning("Unexpected parsed type %s, skipping %d items: %s", type(parsed), len(batch), batch)
		return []

	normalized: list[dict[str, Any]] = []
	for pos, item in enumerate(items):
		# LLM は index をバッチごとに 1 から振り直す(バッチ内ローカル番号)ため、
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
		orig_fallback = prompt.strip_index(batch[local_pos]) if local_pos < len(batch) else ""
		if isinstance(item, dict):
			obj = item.copy()
			obj["index"] = global_index
			# LLM は番号付き入力をそのまま echo しがちなので、元タイトルは常に入力側を採用する。
			obj["original"] = orig_fallback
			if "title" not in obj:
				# title が無ければ別名キーを探す
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

	if debug:
		logger.debug("normalized items: %s", normalized)
	return normalized
