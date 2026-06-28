import pytest

from mv2title import connect


def test_send_message_requires_init(monkeypatch):
	monkeypatch.setattr(connect, "client", None)
	with pytest.raises(RuntimeError):
		connect.send_message("hi")


def test_init_rejects_empty_base_url():
	with pytest.raises(ValueError):
		connect.init(base_url=None)
	with pytest.raises(ValueError):
		connect.init(base_url="")


def test_init_sets_client_and_system_prompt():
	connect.init(api_key="k", base_url="http://localhost:1234/v1/", system_prompt="sp")
	assert connect.client is not None
	assert connect.get_system_prompt() == "sp"


def test_set_system_prompt():
	connect.init(api_key="k", base_url="http://localhost:1234/v1/")
	connect.set_system_prompt("new")
	assert connect.get_system_prompt() == "new"


def test_init_configures_timeout_and_retries():
	connect.init(api_key="k", base_url="http://localhost:1234/v1/",
				 timeout=5.0, max_retries=1)
	assert connect.client.timeout == 5.0
	assert connect.client.max_retries == 1


def test_init_defaults_timeout_and_retries():
	connect.init(api_key="k", base_url="http://localhost:1234/v1/")
	assert connect.client.timeout == connect.DEFAULT_TIMEOUT
	assert connect.client.max_retries == connect.DEFAULT_MAX_RETRIES


def test_send_message_passes_max_tokens(monkeypatch):
	connect.init(api_key="k", base_url="http://localhost:1234/v1/")
	captured = {}

	class FakeCompletions:
		def create(self, **kwargs):
			captured.update(kwargs)
			return "ok"

	monkeypatch.setattr(
		connect.client, "chat",
		type("C", (), {"completions": FakeCompletions()})(),
	)

	connect.send_message("hi", max_tokens=256)
	assert captured["max_tokens"] == 256


def test_send_message_passes_response_format(monkeypatch):
	connect.init(api_key="k", base_url="http://localhost:1234/v1/")
	captured = {}

	class FakeCompletions:
		def create(self, **kwargs):
			captured.update(kwargs)
			return "ok"

	monkeypatch.setattr(
		connect.client, "chat",
		type("C", (), {"completions": FakeCompletions()})(),
	)

	connect.send_message("hi", response_format={"type": "json_object"})
	assert captured["response_format"] == {"type": "json_object"}
	# system_prompt 未指定なら user メッセージのみ
	assert captured["messages"][-1] == {"role": "user", "content": "hi"}


def test_send_message_omits_response_format_when_none(monkeypatch):
	connect.init(api_key="k", base_url="http://localhost:1234/v1/")
	captured = {}

	class FakeCompletions:
		def create(self, **kwargs):
			captured.update(kwargs)
			return "ok"

	monkeypatch.setattr(
		connect.client, "chat",
		type("C", (), {"completions": FakeCompletions()})(),
	)

	connect.send_message("hi")
	assert "response_format" not in captured
	assert "max_tokens" not in captured


def test_send_message_resolves_model_at_call_time(monkeypatch):
	connect.init(api_key="k", base_url="http://localhost:1234/v1/")
	captured = {}

	class FakeCompletions:
		def create(self, **kwargs):
			captured.update(kwargs)
			return "ok"

	monkeypatch.setattr(
		connect.client, "chat",
		type("C", (), {"completions": FakeCompletions()})(),
	)
	monkeypatch.setattr(connect, "model", "my-model")

	connect.send_message("hi")
	assert captured["model"] == "my-model"
