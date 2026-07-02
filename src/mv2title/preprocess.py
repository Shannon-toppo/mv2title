"""LLM 送信前のルールベース前処理(定型ノイズの除去)。"""

import re

# 括弧内に現れたら「定型ノイズ」とみなすキーワード。
# 誤除去を避けるため、タイトル本文には出にくい強いキーワードに限定する。
_NOISE_KEYWORD = re.compile(
	r"\b(?:official|music\s*video|m/?v|pv|audio|lyric(?:s)?(?:\s*video)?|"
	r"visuali[sz]er|teaser|trailer|video|full\s*ver(?:sion)?\.?|short\s*ver\.?|hd|hq|4k)\b"
	r"|公式|高音質|歌詞付き|歌詞動画|フルver|ミュージック\s*ビデオ|オフィシャル",
	re.IGNORECASE,
)

# 最内の括弧グループ(中に別の括弧を含まないもの)。
# 「」『』は曲名そのものを囲う慣習があるため対象外。
_BRACKET_GROUP = re.compile(r"[(\[{【（〔［]([^()\[\]{}【】（）〔〕［］]*)[)\]}】）〕］]")

_FEAT = re.compile(
	r"\s*[(（\[]\s*(?:feat\.?|ft\.?|featuring)\s[^)）\]]*[)）\]]"
	r"|\s+(?:feat\.?|ft\.?|featuring)\s+[^()\[\]（）【】/|‐–—-]+",
	re.IGNORECASE,
)

_EDGE_SEPARATORS = re.compile(r"^[\s/|・:：‐–—-]+|[\s/|・:：‐–—-]+$")

_WS_RUN = re.compile(r"\s+")


def clean_title(title: str) -> str:
	"""LLM へ送る前にタイトルから定型ノイズを除去します。

	除去対象: feat./ft. 句、ノイズキーワード((Official Music Video)、【MV】 など)
	を含む括弧グループ、先頭・末尾に残った区切り記号。
	すべて除去されて空になった場合は安全側に倒して元のタイトルを返します。
	"""
	s = _FEAT.sub("", title)

	def _drop_if_noise(m: re.Match[str]) -> str:
		return "" if _NOISE_KEYWORD.search(m.group(1)) else m.group(0)

	# 最内の括弧から繰り返し評価する(ノイズ括弧が入れ子でも落とせるように)
	prev = None
	while prev != s:
		prev = s
		s = _BRACKET_GROUP.sub(_drop_if_noise, s)

	s = _WS_RUN.sub(" ", s)
	s = _EDGE_SEPARATORS.sub("", s).strip()
	return s if s else title.strip()
