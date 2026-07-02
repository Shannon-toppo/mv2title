"""pytest 共通フィクスチャ。

LLM へは一切接続せず、fake_client(LLMClient 互換のフェイク)を
pipeline.extract_titles などへ注入してオフラインで検証する。
"""

from types import SimpleNamespace

import pytest


def make_completion(content: str):
	"""send_message が返す ChatCompletion の最小モック。"""
	message = SimpleNamespace(content=content)
	choice = SimpleNamespace(message=message)
	return SimpleNamespace(choices=[choice])


def _make_producer(responses):
	if callable(responses):
		return responses
	seq = list(responses)
	it = iter(seq)

	def producer(prompt, **kwargs):
		try:
			return next(it)
		except StopIteration as e:  # pragma: no cover - 想定外の余分な呼び出し
			raise AssertionError("fake client/send: 応答が不足しています") from e

	return producer


@pytest.fixture
def fake_client():
	"""LLMClient 互換のフェイクを生成するヘルパー。

	使い方:
		state = fake_client(["raw1", "raw2"])          # 呼び出し毎に順番に返す
		state = fake_client(lambda prompt, **kw: "..")  # プロンプトに応じて返す
		pipeline.extract_titles([...], state.client)
	呼び出し履歴は state.calls に記録される。
	"""

	def _install(responses):
		state = SimpleNamespace(calls=[])
		producer = _make_producer(responses)

		class _FakeClient:
			def send_message(
				self,
				prompt,
				system_prompt=None,
				model_name=None,
				temperature=0.0,
				response_format=None,
				max_tokens=None,
			):
				state.calls.append(
					SimpleNamespace(
						prompt=prompt,
						response_format=response_format,
						temperature=temperature,
					)
				)
				return make_completion(producer(prompt, response_format=response_format))

		state.client = _FakeClient()
		return state

	return _install
