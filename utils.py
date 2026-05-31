import re
from collections.abc import Iterator


_INDEX_PREFIX = re.compile(r"^\d+\.")


def edit_title(arr: list[str]) -> list[str]:
    """番号を付けたタイトル一覧（例: 1.タイトル）を返します。"""
    return [f"{i+1}.{title}" for i, title in enumerate(arr)]


def strip_index(title: str) -> str:
    """edit_title が付与した先頭の "N." 番号を1つだけ取り除きます（無ければそのまま）。"""
    return _INDEX_PREFIX.sub("", title, count=1)


def chunk_list[T](lst: list[T], size: int) -> Iterator[list[T]]:
    """lst を size 件ずつのサブリストに分割して yield します。"""
    for i in range(0, len(lst), size):
        yield lst[i:i+size]
