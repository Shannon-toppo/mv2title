import subprocess
import sys

import pytest

from mv2title import connect
from mv2title.connect import Config, LLMClient

# .env をテストに混入させないため、from_env を使うテストでは load_dotenv を無効化し、
# 環境変数は monkeypatch で明示的に管理する。
_ENV_KEYS = ("BASE_URL", "API_KEY", "SYSTEM_PROMPT", "MODEL")


@pytest.fixture
def clean_env(monkeypatch):
	monkeypatch.setattr(connect, "load_dotenv", lambda *a, **kw: None)
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
	with pytest.raises(ValueError):
		Config(base_url="")
	with pytest.raises(ValueError):
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
	with pytest.raises(ValueError):
		Config.from_env()


def test_from_env_overrides_beat_env(clean_env, monkeypatch):
	monkeypatch.setenv("BASE_URL", "http://env:1/v1/")
	monkeypatch.setenv("MODEL", "env-model")
	c = Config.from_env(base_url="http://override:2/v1/", model="override-model", timeout=5.0)
	assert c.base_url == "http://override:2/v1/"
	assert c.model == "override-model"
	assert c.timeout == 5.0


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


# ---- モジュールレベル互換シム -------------------------------------------------


def test_send_message_requires_init(monkeypatch):
	monkeypatch.setattr(connect, "_default_client", None)
	with pytest.raises(RuntimeError):
		connect.send_message("hi")


def test_init_builds_default_client(clean_env, monkeypatch):
	monkeypatch.setenv("BASE_URL", "http://env:1/v1/")
	client = connect.init(api_key="k", system_prompt="sp", timeout=5.0, max_retries=1)
	assert connect.get_default_client() is client
	assert client.config.base_url == "http://env:1/v1/"
	assert client.config.system_prompt == "sp"
	assert client._client.timeout == 5.0
	assert client._client.max_retries == 1


def test_init_rejects_missing_base_url(clean_env):
	with pytest.raises(ValueError):
		connect.init()
	with pytest.raises(ValueError):
		connect.init(base_url="")


def test_module_send_message_delegates_to_default_client(clean_env, monkeypatch):
	monkeypatch.setenv("BASE_URL", "http://env:1/v1/")
	client = connect.init(api_key="k")
	captured = _fake_completions(monkeypatch, client)
	connect.send_message("hi", max_tokens=32)
	assert captured["messages"][-1] == {"role": "user", "content": "hi"}
	assert captured["max_tokens"] == 32


# ---- import 時の副作用 ---------------------------------------------------------


def test_import_has_no_side_effects(tmp_path):
	# BASE_URL 等の環境変数が無くても import だけでは失敗せず、
	# .env の読み込みやクライアント生成も行われないこと。
	# 環境変数はホワイトリスト方式で最小限だけ引き継ぎ、cwd も repo 外にして
	# .env が偶然読まれても検知できるようにする。
	import os
	from pathlib import Path

	code = "import mv2title.connect as c; assert c._default_client is None; print('ok')"
	env = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "PATH", "TEMP", "TMP")}
	# mv2title パッケージ(= リポジトリルート)の親ディレクトリを import 可能にする
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
