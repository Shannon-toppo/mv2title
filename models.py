"""パイプラインの入出力データモデル。"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TitleInput:
	"""1 件の入力タイトル。

	Attributes:
		title: 元のタイトル(前処理前)。
		channel: チャンネル名。アーティスト名のヒントとして LLM プロンプトに
			含める(不明なら None)。
	"""

	title: str
	channel: str | None = None


@dataclass
class TitleResult:
	"""1 件の推論結果。

	Attributes:
		index: 入力リスト内の 1-based 位置。
		original: 呼び出し元が渡した元タイトル(前処理前)。
		title: LLM が抽出した曲名。
		valid: 検証(入力タイトルとの部分文字列関係)を通過したか。
	"""

	index: int
	original: str
	title: str
	valid: bool

	def to_dict(self) -> dict[str, Any]:
		"""旧 API 互換の dict 形式(index / original / title / valid)を返す。"""
		return {"index": self.index, "original": self.original, "title": self.title, "valid": self.valid}
