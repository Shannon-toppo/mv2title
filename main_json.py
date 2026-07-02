"""旧 API の互換シム(非推奨)。pipeline.extract_titles を使用してください。

旧 API は「connect.init() を先に呼んでから main() を呼ぶ」契約だったため、
このシムはモジュールレベルの connect.send_message へ委譲するアダプタ経由で
パイプラインを実行する。将来のリリースで削除予定。
"""

import warnings
from typing import Any

try:
	from . import connect, pipeline, validation
	from .models import TitleInput
except ImportError:
	import connect  # type: ignore
	import pipeline  # type: ignore
	import validation  # type: ignore
	from models import TitleInput  # type: ignore


class _ModuleSendAdapter:
	"""connect.send_message(共有デフォルトクライアント)へ委譲する互換アダプタ。"""

	def send_message(self, prompt: str, **kwargs: Any):
		return connect.send_message(prompt, **kwargs)


def send_batches_json(
	prompts: list[str],
	channels: list[str | None] | None = None,
	batch_size: int = 10,
	debug: bool = False,
	use_schema: bool = True,
	temperature: float = 0.0,
) -> list[dict[str, Any]]:
	""".. deprecated:: 0.2.0  pipeline.send_batches() を使用してください。"""
	warnings.warn(
		"main_json.send_batches_json() は非推奨です。pipeline.send_batches() を使用してください。",
		DeprecationWarning,
		stacklevel=2,
	)
	return pipeline.send_batches(
		prompts,
		_ModuleSendAdapter(),  # type: ignore[arg-type]
		channels=channels,
		batch_size=batch_size,
		debug=debug,
		use_schema=use_schema,
		temperature=temperature,
	)


def res_check_json(
	input_text: list[str],
	response: list[dict[str, Any]],
	debug: bool = False,
	cleaned: list[str] | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
	""".. deprecated:: 0.2.0  validation.check_results() を使用してください。"""
	warnings.warn(
		"main_json.res_check_json() は非推奨です。validation.check_results() を使用してください。",
		DeprecationWarning,
		stacklevel=2,
	)
	ok, validated = validation.check_results(input_text, response, debug, cleaned=cleaned)
	return ok, [r.to_dict() for r in validated]


def main(
	text: list[str],
	channels: list[str | None] | None = None,
	batch_size: int = 10,
	bypass_check: bool = False,
	debug_mode: bool = False,
	use_schema: bool = True,
	preprocess: bool = True,
	retry_invalid: int = 1,
) -> list[dict[str, Any]]:
	"""タイトル一覧から曲名を推論する(旧 dict 契約)。

	.. deprecated:: 0.2.0
		pipeline.extract_titles() を使用してください。このモジュールは
		将来のリリースで削除されます。呼び出し前に connect.init() が必要です。
	"""
	warnings.warn(
		"main_json.main() は非推奨です。pipeline.extract_titles() を使用してください（将来のリリースで削除予定）。",
		DeprecationWarning,
		stacklevel=2,
	)
	if channels is not None and len(channels) != len(text):
		raise ValueError(f"channels の長さ ({len(channels)}) が text の長さ ({len(text)}) と一致しません。")
	inputs = [TitleInput(t, channels[i] if channels else None) for i, t in enumerate(text)]
	results = pipeline.extract_titles(
		inputs,
		_ModuleSendAdapter(),  # type: ignore[arg-type]
		batch_size=batch_size,
		bypass_check=bypass_check,
		debug_mode=debug_mode,
		use_schema=use_schema,
		preprocess=preprocess,
		retry_invalid=retry_invalid,
	)
	return [r.to_dict() for r in results]
