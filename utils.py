import os
import re
from collections.abc import Iterator


_INDEX_PREFIX = re.compile(r"^\d+\.")


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
