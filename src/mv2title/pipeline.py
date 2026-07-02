"""推論パイプラインのオーケストレーション。

公開エントリポイントは `extract_titles()`。`LLMClient` を明示的に注入する
(旧 API のような「connect.init() を先に呼ぶ」暗黙の前提は無い)。
"""

import logging
from collections.abc import Sequence
from typing import Any

from . import parsing, prompt, utils, validation
from .connect import LLMClient
from .models import TitleInput, TitleResult
from .preprocess import clean_title

logger = logging.getLogger(__name__)

# 部分リトライ時のサンプリング温度。temperature 0.0 のままだと同じ入力に対して
# 同じ(失敗した)出力が返りやすいため、リトライでは少しだけ揺らぎを与える。
_RETRY_TEMPERATURE = 0.4


def _send_batch_raw(
	batch: list[str],
	client: LLMClient,
	channels: list[str | None] | None = None,
	use_schema: bool = True,
	temperature: float = 0.0,
) -> str | None:
	response_format = prompt.RESPONSE_SCHEMA if use_schema else None
	response = client.send_message(
		prompt.make_json_prompt(batch, channels=channels),
		response_format=response_format,
		temperature=temperature,
	)
	return response.choices[0].message.content


def send_batches(
	prompts: list[str],
	client: LLMClient,
	channels: list[str | None] | None = None,
	batch_size: int = 10,
	debug: bool = False,
	use_schema: bool = True,
	temperature: float = 0.0,
) -> list[dict[str, Any]]:
	"""番号付きタイトルをバッチごとに LLM へ送り、正規化済み dict のリストを返す。"""
	all_objs: list[dict[str, Any]] = []
	# base はバッチ先頭の 0-based グローバルオフセット。
	# LLM の返却件数に依存せず必ず len(batch) ずつ進めることで、
	# あるバッチの件数ズレが後続バッチの採番へ波及（カスケード）するのを防ぐ。
	base = 0
	# 構造化出力をサーバが拒否したら以降のバッチでも使わない（毎回失敗させない）。
	schema_enabled = use_schema
	for batch in utils.chunk_list(prompts, batch_size):
		batch_channels = channels[base : base + len(batch)] if channels else None
		try:
			raw = _send_batch_raw(
				batch, client, channels=batch_channels, use_schema=schema_enabled, temperature=temperature
			)
		except Exception:
			if schema_enabled:
				logger.warning(
					"Structured output (response_format) failed; falling back to plain prompt.",
					exc_info=debug,
				)
				schema_enabled = False
				raw = _send_batch_raw(batch, client, channels=batch_channels, use_schema=False, temperature=temperature)
			else:
				raise
		parsed = parsing.parse_json_response(raw, debug=debug)
		all_objs.extend(parsing.normalize_batch_items(parsed, batch, base, debug=debug))
		base += len(batch)
		if debug:
			logger.debug("raw: %s", raw)

	return all_objs


def extract_titles(
	titles: Sequence[str | TitleInput],
	client: LLMClient,
	*,
	batch_size: int = 10,
	bypass_check: bool = False,
	debug_mode: bool = False,
	use_schema: bool = True,
	preprocess: bool = True,
	retry_invalid: int = 1,
) -> list[TitleResult]:
	"""タイトル一覧から曲名を推論する。

	Args:
		titles: タイトルのリスト。チャンネル名をヒントに使う場合は
			`TitleInput(title, channel)` を渡す(str と混在可)。
		client: 接続に使う LLMClient。
		preprocess: True なら LLM 送信前に preprocess.clean_title で定型ノイズ
			((Official Music Video)、【MV】、feat. ～ など)を除去する。
		retry_invalid: 検証に失敗した項目だけを再問い合わせする回数。0 で無効。
			bypass_check=True のときはリトライしない。
	Returns:
		入力と同数・同順の TitleResult のリスト。
	Raises:
		ValueError: リトライ後も検証に失敗した場合(bypass_check=False 時のみ)。
	"""
	inputs = [t if isinstance(t, TitleInput) else TitleInput(t) for t in titles]
	raw_titles = [i.title for i in inputs]
	channels = [i.channel for i in inputs] if any(i.channel for i in inputs) else None

	cleaned = [clean_title(t) for t in raw_titles] if preprocess else list(raw_titles)
	prompts = prompt.number_titles(cleaned)
	responses = send_batches(
		prompts, client, channels=channels, batch_size=batch_size, debug=debug_mode, use_schema=use_schema
	)
	ok, validated = validation.check_results(raw_titles, responses, debug_mode, cleaned=cleaned)

	# valid=False の項目だけを再問い合わせする部分リトライ。
	attempts = 0
	while not ok and not bypass_check and attempts < retry_invalid:
		attempts += 1
		invalid_pos = [i for i, res in enumerate(validated) if not res.valid]
		retry_cleaned = [cleaned[i] for i in invalid_pos]
		retry_channels = [channels[i] for i in invalid_pos] if channels else None
		if debug_mode:
			logger.debug("Retrying %d invalid items (attempt %d)", len(invalid_pos), attempts)
		retry_resp = send_batches(
			prompt.number_titles(retry_cleaned),
			client,
			channels=retry_channels,
			batch_size=batch_size,
			debug=debug_mode,
			use_schema=use_schema,
			temperature=_RETRY_TEMPERATURE,
		)
		_, retry_validated = validation.check_results(
			[raw_titles[i] for i in invalid_pos], retry_resp, debug_mode, cleaned=retry_cleaned
		)
		for j, res in enumerate(retry_validated):
			if res.valid:
				# サブセット内の通し番号からリスト全体の位置へ戻す
				res.index = invalid_pos[j] + 1
				validated[invalid_pos[j]] = res
		ok = all(res.valid for res in validated)

	if bypass_check or ok:
		return validated
	raise ValueError("Output does not match input titles.")
