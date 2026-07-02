"""LLM 出力の検証(入力タイトルとの突き合わせ)。"""

import logging
import re
import unicodedata
from typing import Any

from .models import TitleResult

logger = logging.getLogger(__name__)

_WS_RUN = re.compile(r"\s+")


def normalize_for_match(s: str) -> str:
	"""検証用の正規化。NFKC(全角/半角の統一)→ casefold → 空白圧縮を行います。"""
	return _WS_RUN.sub(" ", unicodedata.normalize("NFKC", s)).casefold().strip()


def is_title_match(title: str, *sources: str) -> bool:
	"""title が sources のいずれかと部分文字列関係にあるか(正規化後に比較)。

	空の title は常に False(空文字列はあらゆる文字列の部分文字列になるため)。
	"""
	nt = normalize_for_match(title)
	if not nt:
		return False
	for src in sources:
		ns = normalize_for_match(src)
		if nt in ns or (ns and ns in nt):
			return True
	return False


def check_results(
	input_text: list[str],
	response: list[dict[str, Any]],
	debug: bool = False,
	cleaned: list[str] | None = None,
) -> tuple[bool, list[TitleResult]]:
	"""LLM 出力を入力と突き合わせて検証する。

	Args:
		input_text: 呼び出し元が渡した元タイトル(前処理前)。
		response: pipeline.send_batches の出力(正規化済み dict のリスト)。
		cleaned: 前処理後のタイトル(preprocess 有効時)。title の照合先として
			input_text と併用する。省略時は input_text のみと照合。
	Returns:
		(all_ok, validated)。validated は **入力と同数・同順**(index = 位置+1)で、
		対応する出力が無い入力には title 空のプレースホルダを置く。余分な出力や
		重複 index(先勝ち)は捨てられる。各要素の検証は title と入力タイトルの
		部分文字列関係(NFKC 正規化 + casefold 後)で行い、valid フラグを立てる。
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

	validated: list[TitleResult] = []
	all_ok = length_ok
	for i, raw_title in enumerate(input_text):
		obj = by_index.get(i + 1)
		if obj is None:
			if debug:
				logger.debug("Error: No output item with index %d", i + 1)
			validated.append(TitleResult(index=i + 1, original=raw_title, title="", valid=False))
			all_ok = False
			continue
		title = str(obj.get("title") or "")
		# LLM が生成した title が入力(または前処理後タイトル)の部分文字列に
		# なっていることを検証する。original 同士の比較では LLM 出力を検証した
		# ことにならない点に注意(過去にその恒真チェックで形骸化していた)。
		ok = is_title_match(title, raw_title, sources[i])
		# original は前処理後のタイトルではなく、呼び出し元が渡した元タイトルへ戻す。
		validated.append(TitleResult(index=i + 1, original=raw_title, title=title, valid=ok))
		all_ok = all_ok and ok
		if not ok and debug:
			logger.debug("Error: Output title does not match input at index %d: %r vs %r", i, title, raw_title)

	return all_ok, validated
