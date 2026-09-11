import subprocess
import sys
import types
import urllib.error
import urllib.request

import pytest

from mv2title import connect
from mv2title.connect import Config, LLMClient

# from_env は環境変数しか見ない(0.5.0 で .env の読み込みを CLI へ移した)ので、
# 環境変数を monkeypatch で明示的に管理すればテストは .env から独立する。
_ENV_KEYS = ("BASE_URL", "API_KEY", "SYSTEM_PROMPT", "MODEL")


@pytest.fixture
def clean_env(monkeypatch):
	for key in _ENV_KEYS:
		monkeypatch.delenv(key, raising=False)


def _fake_completions(monkeypatch, client: LLMClient) -> dict:
	"""LLMClient 内部の chat.completions.create をフェイクに差し替え、kwargs を捕捉する。"""
	captured: dict = {}

	class FakeCompletions:
		def create(self, **kwargs):
			captured.update(kwargs)
			return "ok"

	monkeypatch.setattr(
		client._client,
		"chat",
		type("C", (), {"completions": FakeCompletions()})(),
	)
	return captured


# ---- Config -----------------------------------------------------------------


def test_config_rejects_empty_base_url():
	with pytest.raises(ValueError, match="BASE_URL"):
		Config(base_url="")
	with pytest.raises(ValueError, match="BASE_URL"):
		Config(base_url=None)  # type: ignore[arg-type]


def test_config_defaults():
	c = Config(base_url="http://localhost:1234/v1/")
	assert c.model == connect.DEFAULT_MODEL
	assert c.timeout == connect.DEFAULT_TIMEOUT
	assert c.max_retries == connect.DEFAULT_MAX_RETRIES
	assert c.api_key is None
	assert c.system_prompt is None


def test_from_env_reads_env(clean_env, monkeypatch):
	monkeypatch.setenv("BASE_URL", "http://env:1/v1/")
	monkeypatch.setenv("API_KEY", "k")
	monkeypatch.setenv("SYSTEM_PROMPT", "sp")
	monkeypatch.setenv("MODEL", "env-model")
	c = Config.from_env()
	assert c.base_url == "http://env:1/v1/"
	assert c.api_key == "k"
	assert c.system_prompt == "sp"
	assert c.model == "env-model"


def test_from_env_missing_base_url_raises(clean_env):
	with pytest.raises(ValueError, match="BASE_URL"):
		Config.from_env()


def test_from_env_overrides_beat_env(clean_env, monkeypatch):
	monkeypatch.setenv("BASE_URL", "http://env:1/v1/")
	monkeypatch.setenv("MODEL", "env-model")
	c = Config.from_env(base_url="http://override:2/v1/", model="override-model", timeout=5.0)
	assert c.base_url == "http://override:2/v1/"
	assert c.model == "override-model"
	assert c.timeout == 5.0


def test_from_env_does_not_read_dotenv(clean_env, monkeypatch, tmp_path):
	"""from_env は .env を読まない(読み込みは CLI の責務。0.5.0 の破壊的変更)。

	引数無しの load_dotenv は呼び出し元のソースファイルから親を遡るため、
	ライブラリ内で呼ぶと利用側が意図しない .env を掴んでしまう。
	"""
	(tmp_path / ".env").write_text("BASE_URL=http://dotenv-should-not-be-read:9/v1/\n", encoding="utf-8")
	monkeypatch.chdir(tmp_path)
	monkeypatch.setenv("BASE_URL", "http://env:1/v1/")
	assert Config.from_env().base_url == "http://env:1/v1/"


def test_from_env_none_override_falls_back_to_env(clean_env, monkeypatch):
	monkeypatch.setenv("BASE_URL", "http://env:1/v1/")
	c = Config.from_env(base_url=None, model=None)
	assert c.base_url == "http://env:1/v1/"
	assert c.model == connect.DEFAULT_MODEL


# ---- LLMClient ---------------------------------------------------------------


def test_client_configures_timeout_and_retries():
	client = LLMClient(Config(base_url="http://localhost:1234/v1/", timeout=5.0, max_retries=1))
	assert client._client.timeout == 5.0
	assert client._client.max_retries == 1


def test_send_message_passes_max_tokens(monkeypatch):
	client = LLMClient(Config(base_url="http://localhost:1234/v1/", api_key="k"))
	captured = _fake_completions(monkeypatch, client)
	client.send_message("hi", max_tokens=256)
	assert captured["max_tokens"] == 256


def test_send_message_passes_response_format(monkeypatch):
	client = LLMClient(Config(base_url="http://localhost:1234/v1/", api_key="k"))
	captured = _fake_completions(monkeypatch, client)
	client.send_message("hi", response_format={"type": "json_object"})
	assert captured["response_format"] == {"type": "json_object"}
	# system_prompt 未指定なら user メッセージのみ
	assert captured["messages"] == [{"role": "user", "content": "hi"}]


def test_send_message_omits_optional_kwargs_when_none(monkeypatch):
	client = LLMClient(Config(base_url="http://localhost:1234/v1/", api_key="k"))
	captured = _fake_completions(monkeypatch, client)
	client.send_message("hi")
	assert "response_format" not in captured
	assert "max_tokens" not in captured


def test_send_message_uses_config_system_prompt_and_model(monkeypatch):
	client = LLMClient(Config(base_url="http://localhost:1234/v1/", system_prompt="sp", model="my-model"))
	captured = _fake_completions(monkeypatch, client)
	client.send_message("hi")
	assert captured["messages"][0] == {"role": "system", "content": "sp"}
	assert captured["model"] == "my-model"


def test_send_message_call_args_override_config(monkeypatch):
	client = LLMClient(Config(base_url="http://localhost:1234/v1/", system_prompt="sp", model="my-model"))
	captured = _fake_completions(monkeypatch, client)
	client.send_message("hi", system_prompt="call-sp", model_name="call-model", temperature=0.7)
	assert captured["messages"][0] == {"role": "system", "content": "call-sp"}
	assert captured["model"] == "call-model"
	assert captured["temperature"] == 0.7


# ---- import 時の副作用 ---------------------------------------------------------


def test_import_has_no_side_effects(tmp_path):
	# BASE_URL 等の環境変数が無くても import だけでは失敗せず、
	# .env の読み込みやクライアント生成も行われないこと。
	# 環境変数はホワイトリスト方式で最小限だけ引き継ぎ、cwd も repo 外にして
	# .env が偶然読まれても検知できるようにする。
	import os
	from pathlib import Path

	code = "import mv2title.connect; print('ok')"
	env = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "PATH", "TEMP", "TMP")}
	# mv2title パッケージ(src/mv2title)の親ディレクトリを import 可能にする
	env["PYTHONPATH"] = str(Path(connect.__file__).resolve().parent.parent)
	res = subprocess.run(
		[sys.executable, "-c", code],
		capture_output=True,
		text=True,
		env=env,
		cwd=str(tmp_path),
		timeout=60,
	)
	assert res.returncode == 0, res.stderr
	assert "ok" in res.stdout


# ---- モデル名の解決と応答モデルの確認 -------------------------------------------
# (LM Studio は一覧と完全一致しない名前だとロード中の別モデルで黙って答える)


def _fake_urlopen(monkeypatch, body: bytes, status: int = 200) -> dict:
	"""urlopen を status/body 固定のフェイクへ差し替え、リクエスト内容を記録する。"""
	seen: dict = {}

	http_status = status

	class FakeResp:
		status = http_status

		def __enter__(self):
			return self

		def __exit__(self, *a):
			return False

		def read(self, n=-1):
			return body

	def fake_urlopen(req, timeout=0):
		seen["url"] = req.full_url
		seen["timeout"] = timeout
		return FakeResp()

	monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
	return seen


_SERVER_IDS = ["google/gemma-4-e4b", "google/gemma-4-e2b", "hy-mt2-1.8b@bf16", "hy-mt2-1.8b@8bit"]
_SERVER_BODY = (
	b'{"data": [{"id": "google/gemma-4-e4b"}, {"id": "google/gemma-4-e2b"},'
	b' {"id": "hy-mt2-1.8b@bf16"}, {"id": "hy-mt2-1.8b@8bit"}]}'
)


def _config(base_url="http://127.0.0.1:1234/v1/", model="m1") -> Config:
	return Config(base_url=base_url, model=model)


def test_fetch_model_ids_success(monkeypatch):
	seen = _fake_urlopen(monkeypatch, b'{"object": "list", "data": [{"id": "m1"}, {"id": "m2"}]}')
	assert connect.fetch_model_ids(_config(), timeout=1.5) == ["m1", "m2"]
	# 末尾スラッシュに頑健(//models にならない)で、指定した timeout が使われる
	assert seen["url"] == "http://127.0.0.1:1234/v1/models"
	assert seen["timeout"] == 1.5


def test_fetch_model_ids_error_json_with_200(monkeypatch):
	# LM Studio は存在しないパス(/v1 抜けなど)にも HTTP 200 でエラー JSON を
	# 返すため、ステータスだけ見ると偽陽性になる。ボディ検証で弾く。
	_fake_urlopen(monkeypatch, b'{"error":"Unexpected endpoint or method. (GET /models)"}')
	with pytest.raises(connect.ConnectionCheckError, match="/models"):
		connect.fetch_model_ids(_config(base_url="http://127.0.0.1:1234"))


def test_fetch_model_ids_non_json_with_200(monkeypatch):
	# LLM 以外のサーバ(管理画面など)が HTML を 200 で返すケースも弾く
	_fake_urlopen(monkeypatch, b"<html>hello</html>")
	with pytest.raises(connect.ConnectionCheckError):
		connect.fetch_model_ids(_config())


def test_fetch_model_ids_refused(monkeypatch):
	def boom(req, timeout=0):
		raise urllib.error.URLError("connection refused")

	monkeypatch.setattr(urllib.request, "urlopen", boom)
	with pytest.raises(connect.ConnectionCheckError, match="接続できません"):
		connect.fetch_model_ids(_config())


@pytest.mark.parametrize(
	("model", "expected"),
	[
		("gemma-4-e2b", "google/gemma-4-e2b"),  # publisher 省略 → 完全な id
		("Gemma-4-E2B", "google/gemma-4-e2b"),  # 大小文字の揺れ
		("google/gemma-4-e2b", "google/gemma-4-e2b"),  # 完全一致
		("hy-mt2-1.8b@8bit", "hy-mt2-1.8b@8bit"),  # 完全一致は量子化違いより優先
		("hy-mt2-1.8b", "hy-mt2-1.8b"),  # 候補が複数なら決めつけない
		("gemma-4-e2b-it", "gemma-4-e2b-it"),  # 一覧に無ければそのまま
	],
)
def test_resolve_model(model, expected):
	assert connect.resolve_model(model, _SERVER_IDS) == expected


def test_resolve_model_without_list():
	assert connect.resolve_model("gemma-4-e2b", []) == "gemma-4-e2b"


@pytest.mark.parametrize(
	"model",
	[
		"gemma-4-e2b",  # publisher 省略(LM Studio の設定画面はこの表記)
		"Gemma-4-E2B",  # 大文字小文字の揺れ
		"google/gemma-4-e2b@q4_k_m",  # 量子化サフィックス付き
		"google/gemma-4-e2b",  # 完全一致
	],
)
def test_model_aliases_match_full_id(model):
	assert connect.model_aliases(model) & connect.model_aliases("google/gemma-4-e2b")


def test_model_aliases_do_not_match_other_model():
	assert not (connect.model_aliases("gemma-4-e2b") & connect.model_aliases("google/gemma-4-e4b"))


def test_check_endpoint_returns_ids_and_resolved_model(monkeypatch):
	_fake_urlopen(monkeypatch, _SERVER_BODY)
	ids, resolved = connect.check_endpoint(_config(model="gemma-4-e2b"))
	assert ids == _SERVER_IDS
	assert resolved == "google/gemma-4-e2b"


def test_make_client_resolves_model(monkeypatch):
	_fake_urlopen(monkeypatch, _SERVER_BODY)
	client = connect.make_client(_config(model="gemma-4-e2b"))
	assert client.config.model == "google/gemma-4-e2b"
	assert isinstance(client, connect.ModelCheckedClient)


def test_make_client_keeps_model_when_list_unavailable(monkeypatch):
	def boom(req, timeout=0):
		raise urllib.error.URLError("connection refused")

	monkeypatch.setattr(urllib.request, "urlopen", boom)
	assert connect.make_client(_config(model="gemma-4-e2b")).config.model == "gemma-4-e2b"


def _checked_client(monkeypatch, answered, model="google/gemma-4-e2b"):
	"""応答の model 欄が answered になる ModelCheckedClient と、送信の記録。"""
	sent = []

	def fake_send(self, prompt, system_prompt=None, model_name=None, **kwargs):
		sent.append(kwargs)
		message = types.SimpleNamespace(content='{"results": [{"id": 1, "title": "Song"}]}')
		return types.SimpleNamespace(model=answered, choices=[types.SimpleNamespace(message=message)])

	monkeypatch.setattr(LLMClient, "send_message", fake_send)
	return connect.ModelCheckedClient(_config(model=model)), sent


def test_checked_client_rejects_substituted_model(monkeypatch):
	client, sent = _checked_client(monkeypatch, answered="google/gemma-4-e4b")
	with pytest.raises(connect.ModelMismatchError) as exc:
		client.send_message("p")
	assert "google/gemma-4-e2b" in str(exc.value)
	assert "google/gemma-4-e4b" in str(exc.value)
	# 2 回目以降は送らずに同じ理由で止める(違うモデルで推論させない)
	with pytest.raises(connect.ModelMismatchError):
		client.send_message("p")
	assert len(sent) == 1


@pytest.mark.parametrize("answered", ["google/gemma-4-e2b", "gemma-4-e2b", None, ""])
def test_checked_client_accepts_same_model(monkeypatch, answered):
	"""表記ゆれの範囲の一致と、model 欄を返さないサーバーは通す。"""
	client, sent = _checked_client(monkeypatch, answered=answered)
	client.send_message("p")
	assert len(sent) == 1
