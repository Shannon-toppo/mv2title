from collections.abc import Iterator


def edit_title(arr: list[str]) -> list[str]:
    """番号を付けたタイトル一覧（例: 1.タイトル）を返します。"""
    return [f"{i+1}.{title}" for i, title in enumerate(arr)]


def chunk_list[T](lst: list[T], size: int) -> Iterator[list[T]]:
    """lst を size 件ずつのサブリストに分割して yield します。"""
    for i in range(0, len(lst), size):
        yield lst[i:i+size]
