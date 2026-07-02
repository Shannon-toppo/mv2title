"""OpenAI 互換エンドポイントへの接続層。

`Config`(接続設定)と `LLMClient`(クライアント本体)が中心。
import 時の副作用は無く、`.env` / 環境変数の読み込みは `Config.from_env()` を
呼んだときに初めて行われる。
"""

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletion

DEFAULT_MODEL = "gemma-4-e2b-it"
# ローカル LLM は応答が遅いことがあるため、OpenAI 既定 (600s) より短いが余裕のある値。
DEFAULT_TIMEOUT: float = 120.0
# openai SDK が接続エラー・429・5xx を指数バックオフ付きで再試行する回数。
DEFAULT_MAX_RETRIES: int = 2


@dataclass(frozen=True)
class Config:
	"""LLM 接続設定。環境変数から作る場合は `Config.from_env()` を使う。

	Attributes:
		base_url: OpenAI 互換 API のベース URL(必須)。
		api_key: API キー。ローカルサーバーなら任意の文字列で可。
		model: 使用するモデル名。
		system_prompt: 既定の system プロンプト(任意)。
		timeout: リクエスト全体のタイムアウト秒数。
		max_retries: 一時的エラー時の再試行回数(SDK が指数バックオフで処理)。
	"""

	base_url: str
	api_key: str | None = None
	model: str = DEFAULT_MODEL
	system_prompt: str | None = None
	timeout: float = DEFAULT_TIMEOUT
	max_retries: int = DEFAULT_MAX_RETRIES

	def __post_init__(self) -> None:
		if not self.base_url:
			# base_url が None/空だと OpenAI() は本番 (api.openai.com) へフォールバックする。
			# 本ライブラリはローカル OpenAI 互換サーバ前提のため、誤送信を防いで明示的に失敗させる。
			raise ValueError(
				"BASE_URL が未設定です。ローカル LLM のエンドポイント"
				"（例: http://127.0.0.1:1234/v1/）を .env の BASE_URL に設定するか、"
				"base_url 引数で明示してください。"
			)

	@classmethod
	def from_env(cls, **overrides: Any) -> "Config":
		""".env と環境変数(BASE_URL / API_KEY / SYSTEM_PROMPT / MODEL)から構築する。

		overrides に None を渡した項目は「未指定」とみなし、環境変数
		(それも無ければ dataclass の既定値)にフォールバックする。
		"""
		load_dotenv()
		values: dict[str, Any] = {
			"base_url": os.getenv("BASE_URL"),
			"api_key": os.getenv("API_KEY"),
			"system_prompt": os.getenv("SYSTEM_PROMPT"),
			"model": os.getenv("MODEL", DEFAULT_MODEL),
		}
		values.update({k: v for k, v in overrides.items() if v is not None})
		return cls(**values)


class LLMClient:
	"""OpenAI 互換クライアントの薄いラッパ。設定は `Config` で注入する。"""

	def __init__(self, config: Config) -> None:
		self.config = config
		self._client = OpenAI(
			# openai SDK は api_key=None を拒否するが、ローカル OpenAI 互換サーバは
			# キーを検証しないことが多いため、未指定ならプレースホルダを渡す。
			api_key=config.api_key or "not-needed",
			base_url=config.base_url,
			timeout=config.timeout,
			max_retries=config.max_retries,
		)

	def send_message(
		self,
		prompt: str,
		system_prompt: str | None = None,
		model_name: str | None = None,
		temperature: float = 0.0,
		response_format: dict[str, Any] | None = None,
		max_tokens: int | None = None,
	) -> ChatCompletion:
		"""メッセージを送信する。

		Args:
			prompt: ユーザーメッセージ
			system_prompt: 呼び出しごとに指定する system プロンプト(省略時は Config の値)
			model_name: 使用するモデル名(省略時は Config の値)
			temperature: サンプリング温度。抽出タスクのため既定は 0.0(決定的)
			response_format: OpenAI 互換の構造化出力指定(例: json_schema / json_object)。
				省略時は通常のテキスト応答。
			max_tokens: 応答の最大トークン数。省略時はサーバ既定。
		"""
		sp = system_prompt if system_prompt is not None else self.config.system_prompt
		messages: list[dict[str, str]] = []
		if sp:
			messages.append({"role": "system", "content": sp})
		messages.append({"role": "user", "content": prompt})

		kwargs: dict[str, Any] = {
			"model": model_name if model_name is not None else self.config.model,
			"messages": messages,
			"temperature": temperature,
		}
		if response_format is not None:
			kwargs["response_format"] = response_format
		if max_tokens is not None:
			kwargs["max_tokens"] = max_tokens

		return self._client.chat.completions.create(**kwargs)


def _selftest(prompt: str = "pingと返答してください。") -> int:
	"""
	単体実行用: .env の設定でローカル LLM への疎通を確認する。
	成功時は 0、失敗時は非 0 を返す。
	"""
	import time

	try:
		config = Config.from_env()
	except ValueError as e:
		print(f"設定の読み込みに失敗: {e}")
		return 1

	print(f"BASE_URL = {config.base_url}")
	print(f"MODEL    = {config.model}")
	print(f"API_KEY  = {'(set)' if config.api_key else '(empty)'}")
	print(f"prompt   = {prompt!r}")
	print("-" * 40)

	client = LLMClient(config)

	t0 = time.perf_counter()
	try:
		res = client.send_message(prompt, max_tokens=64)
	except Exception as e:
		print(f"send_message() 失敗: {type(e).__name__}: {e}")
		return 2
	elapsed = time.perf_counter() - t0

	try:
		content = res.choices[0].message.content
	except (AttributeError, IndexError) as e:
		print(f"応答のパースに失敗: {type(e).__name__}: {e}")
		print(f"raw: {res!r}")
		return 3

	print(f"応答 ({elapsed:.2f}s): {content!r}")
	usage = getattr(res, "usage", None)
	if usage is not None:
		print(f"usage: {usage}")
	print("OK")
	return 0


if __name__ == "__main__":
	import sys

	user_prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "pingと返答してください。"
	sys.exit(_selftest(user_prompt))
