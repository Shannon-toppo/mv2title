"""pytest 共通フィクスチャ。

LLM へは一切接続せず、connect.send_message をモックしてオフラインで検証する。
"""
from types import SimpleNamespace

import pytest


def make_completion(content: str):
	"""connect.send_message が返す ChatCompletion の最小モック。"""
	message = SimpleNamespace(content=content)
	choice = SimpleNamespace(message=message)
	return SimpleNamespace(choices=[choice])


@pytest.fixture
def fake_send(monkeypatch):
	"""connect.send_message を差し替えるヘルパー。

	使い方:
		fake_send(["raw1", "raw2"])           # バッチ毎に順番に返す
		fake_send(lambda prompt, **kw: "...")  # プロンプトに応じて返す
	呼び出し履歴は戻り値オブジェクトの .calls に記録される。
	"""
	import mv2title.connect as connect

	state = SimpleNamespace(calls=[])

	def _install(responses):
		if callable(responses):
			producer = responses
		else:
			seq = list(responses)
			it = iter(seq)

			def producer(prompt, **kwargs):
				try:
					return next(it)
				except StopIteration:  # pragma: no cover - 想定外の余分な呼び出し
					raise AssertionError("fake_send: 応答が不足しています")

		def fake(prompt, system_prompt=None, model_name=None,
				 temperature=0.0, response_format=None, max_tokens=None):
			state.calls.append(SimpleNamespace(
				prompt=prompt, response_format=response_format,
				temperature=temperature,
			))
			return make_completion(producer(prompt, response_format=response_format))

		monkeypatch.setattr(connect, "send_message", fake)
		return state

	return _install
