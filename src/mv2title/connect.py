"""OpenAI 互換エンドポイントへの接続層。

`Config`(接続設定)と `LLMClient`(クライアント本体)が中心。
import 時の副作用は無く、環境変数の読み込みは `Config.from_env()` を
呼んだときに初めて行われる。

`.env` はライブラリからは読まない(0.5.0 で変更)。`load_dotenv()` は
引数無しだと **呼び出し元のソースファイル** から親ディレクトリを遡るため、
利用側アプリが意図しない `mv2title/.env` を掴む事故が起きていた。
`.env` を使いたい場合は CLI(`cli.main` / `_selftest`)のように利用側で
`load_dotenv()` を呼ぶか、環境変数を自分で設定すること。
"""

import dataclasses
import json
import os
import urllib.request
from collections.abc import Sequence
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
		"""環境変数(BASE_URL / API_KEY / SYSTEM_PROMPT / MODEL)から構築する。

		overrides に None を渡した項目は「未指定」とみなし、環境変数
		(それも無ければ dataclass の既定値)にフォールバックする。

		`.env` は読まない。必要なら呼び出し側で `dotenv.load_dotenv()` を
		先に実行すること(モジュール docstring 参照)。
		"""
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


class ConnectionCheckError(Exception):
	"""エンドポイントの疎通確認に失敗した(接続不可・/models 形式でない等)。"""


class ModelMismatchError(Exception):
	"""指定したモデルとは別のモデルが応答した(サーバー側の差し替え)。"""


def model_aliases(model_id: str) -> set[str]:
	"""モデル名の表記ゆれ(publisher 有無・量子化サフィックス・大小文字)を列挙する。

	/models が返す id は publisher 付き(例: "google/gemma-4-e2b")だが、
	LM Studio の画面や設定では publisher を省いた "gemma-4-e2b" と書かれる。
	これは「同じモデルを指しているか」を比べるためのもので、サーバーへ送る
	名前には使わない: LM Studio は省略形を同じモデルに解決するとは限らず、
	別のモデルがロード中だとそちらで答える(`make_client` 参照)。
	"""
	base = model_id.strip().lower().split("@", 1)[0]
	aliases = {base}
	if "/" in base:
		aliases.add(base.rsplit("/", 1)[1])
	return {a for a in aliases if a}


def resolve_model(model: str, server_ids: Sequence[str]) -> str:
	"""設定のモデル名を、サーバーの一覧にある完全な id へ解決する。

	大小文字違いを除いた完全一致を最優先し、無ければ表記ゆれ(`model_aliases`)
	で一致する id が 1 つだけのときにそれを返す。候補が複数(量子化違いが
	並んでいる等)や一覧に無いときは決めつけず、指定をそのまま返す。
	"""
	wanted = model.strip()
	for sid in server_ids:
		if sid.lower() == wanted.lower():
			return sid
	aliases = model_aliases(wanted)
	matches = [sid for sid in server_ids if model_aliases(sid) & aliases]
	return matches[0] if len(matches) == 1 else wanted


def fetch_model_ids(config: Config, timeout: float = 3.0) -> list[str]:
	"""GET {base_url}/models でサーバーのモデル id 一覧を取る。

	openai SDK の `models.list()` ではなく urllib を使うのは意図的で、SDK は
	ボディをページ型へパースしてしまい、LM Studio が存在しないパスへ HTTP 200 で
	返すエラー JSON(例: BASE_URL の /v1 抜け)を見分けられないため。
	ステータスコードだけでは判定せず、ボディが /models 応答の形("data" リスト)
	であることまで確認する。

	Raises:
		ConnectionCheckError: 接続できない・エラー応答・/models 形式でない。
	"""
	url = config.base_url.rstrip("/") + "/models"
	req = urllib.request.Request(
		url,
		headers={"Authorization": f"Bearer {config.api_key or 'not-needed'}"},
	)
	try:
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			status = getattr(resp, "status", 200)
			if not 200 <= status < 300:
				raise ConnectionCheckError(f"エンドポイントがエラーを返しました (HTTP {status})")
			body = resp.read(65536)
	except ConnectionCheckError:
		raise
	except Exception as e:
		raise ConnectionCheckError(f"接続できません ({config.base_url}): {e}") from e
	try:
		payload = json.loads(body)
	except ValueError:
		payload = None
	if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
		raise ConnectionCheckError(
			f"応答が OpenAI 互換の /models 形式ではありません ({url})。"
			"BASE_URL のパス(例: 末尾の /v1)が正しいか確認してください。"
		)
	return [m["id"] for m in payload["data"] if isinstance(m, dict) and isinstance(m.get("id"), str)]


class ModelCheckedClient(LLMClient):
	"""応答の model 欄を確かめ、指定と違うモデルが答えたら止める LLMClient。

	`resolve_model` で解決できなかった名前(一覧に無い・候補が複数)でも、
	サーバーが黙って別のモデルで推論した結果をタイトルとして使わないための
	最後の砦。一度不一致を見たら以降はリクエストを送らずに同じ例外を投げる
	(安価な保険。`pipeline.send_batches` 側でも `ModelMismatchError` は
	構造化出力の拒否と区別して即時送出する)。
	"""

	def __init__(self, config: Config) -> None:
		super().__init__(config)
		self._mismatch: ModelMismatchError | None = None

	def send_message(
		self,
		prompt: str,
		system_prompt: str | None = None,
		model_name: str | None = None,
		temperature: float = 0.0,
		response_format: dict[str, Any] | None = None,
		max_tokens: int | None = None,
	) -> ChatCompletion:
		if self._mismatch is not None:
			raise self._mismatch
		res = super().send_message(
			prompt,
			system_prompt,
			model_name,
			temperature=temperature,
			response_format=response_format,
			max_tokens=max_tokens,
		)
		requested = model_name if model_name is not None else self.config.model
		answered = getattr(res, "model", None)
		if (
			isinstance(answered, str)
			and answered
			and requested
			and not (model_aliases(requested) & model_aliases(answered))
		):
			self._mismatch = ModelMismatchError(
				f"指定したモデル '{requested}' ではなく '{answered}' が応答しました"
				"(サーバーが別のモデルに差し替えています)。"
				f"'{requested}' をロードするか、MODEL をサーバーのモデル一覧にある名前に"
				"してください。"
			)
			raise self._mismatch
		return res


def make_client(config: Config, *, timeout: float = 3.0) -> LLMClient:
	"""モデル名をサーバーの一覧へ解決したうえで `ModelCheckedClient` を返す。

	LM Studio は一覧の id と完全一致しない名前を受けると、エラーにせず
	ロード中の別モデルで黙って答える。実測: e4b をロード中に "gemma-4-e2b" を
	指定 → google/gemma-4-e4b が応答、"google/gemma-4-e2b" を指定 → e2b が
	JIT ロードされて応答した。一覧が取れないときは解決を諦め、そのままの
	モデル名で進む(失敗理由は実際の推論呼び出しで出る)。
	"""
	try:
		ids = fetch_model_ids(config, timeout=timeout)
	except ConnectionCheckError:
		ids = []
	model = resolve_model(config.model or "", ids)
	if model and model != config.model:
		config = dataclasses.replace(config, model=model)
	return ModelCheckedClient(config)


def check_endpoint(config: Config, timeout: float = 3.0) -> tuple[list[str], str]:
	"""疎通確認の結果を (モデル id 一覧, 解決後のモデル名) で返す。

	補完呼び出しをしない軽量チェック。文言の組み立ては利用側に任せる
	(一覧に `config.model` が含まれるかどうかも呼び出し側で判断できる)。

	Raises:
		ConnectionCheckError: 接続できない・/models 形式でない。
	"""
	ids = fetch_model_ids(config, timeout=timeout)
	return ids, resolve_model(config.model or "", ids)


def _selftest(prompt: str = "pingと返答してください。") -> int:
	"""
	単体実行用: .env の設定でローカル LLM への疎通を確認する。
	成功時は 0、失敗時は非 0 を返す。
	"""
	import time

	# 単体実行はコマンドラインの入口なので、ここで .env を読む(ライブラリは読まない)。
	load_dotenv()
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

	client = make_client(config)
	if client.config.model != config.model:
		print(f"MODEL 解決: {config.model} → {client.config.model}")

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
