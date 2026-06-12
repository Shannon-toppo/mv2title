import os
import re
import unicodedata
from collections.abc import Iterator


_INDEX_PREFIX = re.compile(r"^\d+\.")

# --- LLM 前のルールベース前処理 ---------------------------------------------

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


def edit_title(arr: list[str]) -> list[str]:
    """番号を付けたタイトル一覧（例: 1.タイトル）を返します。"""
    return [f"{i+1}.{title}" for i, title in enumerate(arr)]


def strip_index(title: str) -> str:
    """edit_title が付与した先頭の "N." 番号を1つだけ取り除きます（無ければそのまま）。"""
    return _INDEX_PREFIX.sub("", title, count=1)


def read_titles(path: str) -> list[str]:
    """1 行 1 タイトルのファイルを読み、前後空白・空行を除いたリストを返します。"""
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def chunk_list[T](lst: list[T], size: int) -> Iterator[list[T]]:
    """lst を size 件ずつのサブリストに分割して yield します。"""
    for i in range(0, len(lst), size):
        yield lst[i:i+size]
