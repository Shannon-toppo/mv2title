"""推論パイプラインのオーケストレーション。

公開エントリポイントは `extract_titles()`。`LLMClient` を明示的に注入する
(旧 API のような「connect.init() を先に呼ぶ」暗黙の前提は無い)。
"""

import logging
from collections.abc import Sequence
from typing import Any

from . import parsing, prompt, utils, validation
from .connect import LLMClient, ModelMismatchError
from .models import TitleInput, TitleResult
from .preprocess import clean_title

logger = logging.getLogger(__name__)

# 部分リトライ時のサンプリング温度。temperature 0.0 のままだと同じ入力に対して
# 同じ(失敗した)出力が返りやすいため、リトライでは少しだけ揺らぎを与える。
_RETRY_TEMPERATURE = 0.4


def _send_batch_raw(
	batch: list[str],
	client: LLMClient,
	channels: Sequence[str | None] | None = None,
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
	channels: Sequence[str | None] | None = None,
	batch_size: int = 10,
	debug: bool = False,
	use_schema: bool = True,
	temperature: float = 0.0,
) -> list[dict[str, Any]]:
	"""番号付きタイトルをバッチごとに LLM へ送り、正規化済み dict のリストを返す。

	構造化出力 (`response_format`) は 2 つの経路でラッチ解除される。どちらの場合も
	以降のバッチはプレーンプロンプトで送り、同じ失敗を毎バッチ繰り返さない。

	1. サーバが `response_format` を拒否した(例外)。そのバッチはプレーンで再送する。
	2. 200 で返ったが件数が入力より少ない。制約付きデコードで配列が途中で打ち切られた形
	   (gemma-4-e2b + LM Studio では `finish_reason=stop` / `reasoning_tokens=0` で
	   1 件だけ返る挙動が決定的に再現する)。このバッチの欠落分はここでは再送せず、
	   `extract_titles` の部分リトライが拾う。
	"""
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
		except ModelMismatchError:
			# 指定と違うモデルが答えた場合は構造化出力の拒否ではない。プレーンで
			# 再送すると同じ別モデルにもう一度推論させてしまうため、そのまま送出する。
			raise
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
		items = parsing.normalize_batch_items(parsed, batch, base, debug=debug)
		all_objs.extend(items)
		if schema_enabled and len(items) < len(batch):
			# 打ち切り(上記 2)。以降のバッチは無駄打ちになるのでプレーンへ落とす。
			logger.warning(
				"Structured output returned %d/%d items (truncated); "
				"falling back to plain prompt for the remaining batches.",
				len(items),
				len(batch),
			)
			schema_enabled = False
		base += len(batch)
		if debug:
			logger.debug("raw: %s", raw)

	return all_objs


def _retry_positions(
	positions: list[int],
	*,
	validated: list[TitleResult],
	raw_titles: list[str],
	cleaned: list[str],
	channels: list[str | None] | None,
	client: LLMClient,
	batch_size: int,
	temperature: float,
	debug: bool,
) -> None:
	"""指定位置の項目だけを再問い合わせし、valid になったものを validated へ書き戻す。

	リトライは常に `use_schema=False`(プレーンプロンプト)で送る。構造化出力を付けると
	モデルが配列の 1 件目だけ出して停止する事例があり、それは温度を振っても変わらない
	(制約付きデコード下では思考トークンが挟めず打ち切られるため決定的に再現する)。
	同じ条件で問い直しても同じ打ち切りを繰り返すだけなので、リトライでは制約を外す。
	"""
	retry_cleaned = [cleaned[i] for i in positions]
	retry_channels = [channels[i] for i in positions] if channels else None
	retry_resp = send_batches(
		prompt.number_titles(retry_cleaned),
		client,
		channels=retry_channels,
		batch_size=batch_size,
		debug=debug,
		use_schema=False,
		temperature=temperature,
	)
	_, retry_validated = validation.check_results(
		[raw_titles[i] for i in positions], retry_resp, debug, cleaned=retry_cleaned
	)
	for j, res in enumerate(retry_validated):
		if res.valid:
			# サブセット内の通し番号からリスト全体の位置へ戻す
			res.index = positions[j] + 1
			validated[positions[j]] = res


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
		bypass_check: True なら検証に失敗しても例外を投げずに結果を返す。
			**リトライの実施可否には影響しない**(0.4.0 で分離)。つまり
			bypass_check=True の呼び出しでも欠けた項目の回収は試みるため、
			LLM への往復が増えることがある。往復を止めたいときは
			`retry_invalid=0` を指定する。
		preprocess: True なら LLM 送信前に preprocess.clean_title で定型ノイズ
			((Official Music Video)、【MV】、feat. ～ など)を除去する。
		retry_invalid: 検証に失敗した項目だけを再問い合わせする回数。0 で無効。
			リトライは失敗の質で 2 群に分けて送る(下記参照)。
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
	# bypass_check とは独立させてある: bypass_check は「最後に ValueError を投げるか」
	# だけを決め、リトライを回すかどうかは retry_invalid が持つ。
	# (bypass_check=True は「検証に落ちても結果が欲しい」であって
	#  「回収を試みなくてよい」ではないため。)
	attempts = 0
	while not ok and attempts < retry_invalid:
		attempts += 1
		invalid_pos = [i for i, res in enumerate(validated) if not res.valid]
		# 失敗の質で 2 群に分ける。原因が違うので温度の扱いも変える。
		#   missing : 応答にその項目が無く空のプレースホルダで埋まった
		#             (打ち切り)。プレーンプロンプトに落とすだけで回収できるので
		#             1 回目は temperature 0.0 のまま(決定的な抽出が本来の設計)。
		#             2 回目以降は同じ問い合わせの再生になるので温度を上げる。
		#   mismatch: title は返ったが is_title_match に落ちた(言い換え・幻覚)。
		#             同じ出力の再生を避けるため最初から温度を上げる。
		missing = [i for i in invalid_pos if not validated[i].title]
		mismatch = [i for i in invalid_pos if validated[i].title]
		if debug_mode:
			logger.debug(
				"Retrying %d invalid items (attempt %d): missing=%d mismatch=%d",
				len(invalid_pos),
				attempts,
				len(missing),
				len(mismatch),
			)
		groups = (
			(missing, 0.0 if attempts == 1 else _RETRY_TEMPERATURE),
			(mismatch, _RETRY_TEMPERATURE),
		)
		for positions, temperature in groups:
			if not positions:
				continue
			_retry_positions(
				positions,
				validated=validated,
				raw_titles=raw_titles,
				cleaned=cleaned,
				channels=channels,
				client=client,
				batch_size=batch_size,
				temperature=temperature,
				debug=debug_mode,
			)
		ok = all(res.valid for res in validated)

	if bypass_check or ok:
		return validated
	raise ValueError("Output does not match input titles.")
