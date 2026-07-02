"""汎用ヘルパー。"""

from collections.abc import Iterator


def chunk_list[T](lst: list[T], size: int) -> Iterator[list[T]]:
	"""lst を size 件ずつのサブリストに分割して yield します。"""
	for i in range(0, len(lst), size):
		yield lst[i : i + size]
