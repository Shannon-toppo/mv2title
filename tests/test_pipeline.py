import json

import pytest

from mv2title import pipeline, prompt
from mv2title.models import TitleInput


def _schema_payload(items):
	return json.dumps({"results": items}, ensure_ascii=False)


# ---- send_batches -------------------------------------------------------------


def test_send_batches_single_batch_happy(fake_client):
	state = fake_client(
		[
			_schema_payload(
				[
					{"index": 1, "original": "1.x", "title": "X"},
					{"index": 2, "original": "2.y", "title": "Y"},
				]
			)
		]
	)
	objs = pipeline.send_batches(["1.foo", "2.bar"], state.client, batch_size=10)
	assert [o["index"] for o in objs] == [1, 2]
	assert [o["title"] for o in objs] == ["X", "Y"]


def test_send_batches_index_is_batch_local_converted_to_global(fake_client):
	# 各バッチで index が 1 から振り直されても、グローバル連番になること
	state = fake_client(
		[
			_schema_payload([{"index": 1, "title": "A"}, {"index": 2, "title": "B"}]),
			_schema_payload([{"index": 1, "title": "C"}, {"index": 2, "title": "D"}]),
		]
	)
	prompts = prompt.number_titles(["a", "b", "c", "d"])
	objs = pipeline.send_batches(prompts, state.client, batch_size=2)
	assert [o["index"] for o in objs] == [1, 2, 3, 4]
	assert [o["title"] for o in objs] == ["A", "B", "C", "D"]


def test_send_batches_count_mismatch_does_not_cascade(fake_client):
	# 1 バッチ目が 1 件しか返さなくても 2 バッチ目の index がずれない
	state = fake_client(
		[
			_schema_payload([{"index": 1, "title": "A"}]),  # 2件中1件のみ
			_schema_payload([{"index": 1, "title": "C"}, {"index": 2, "title": "D"}]),
		]
	)
	prompts = prompt.number_titles(["a", "b", "c", "d"])
	objs = pipeline.send_batches(prompts, state.client, batch_size=2)
	# 2 バッチ目はグローバル index 3,4 になる
	assert sorted(o["index"] for o in objs) == [1, 3, 4]


def test_send_batches_uses_schema_by_default(fake_client):
	state = fake_client([_schema_payload([{"index": 1, "title": "A"}])])
	pipeline.send_batches(["1.a"], state.client, batch_size=10)
	assert state.calls[0].response_format is not None


def test_send_batches_no_schema_flag(fake_client):
	state = fake_client(['[{"index":1,"title":"A"}]'])
	pipeline.send_batches(["1.a"], state.client, batch_size=10, use_schema=False)
	assert state.calls[0].response_format is None


def test_send_batches_falls_back_when_schema_rejected(fake_client):
	# 最初の schema 付き呼び出しは例外、以降は plain で成功させる
	def producer(prompt_text, response_format=None):
		if response_format is not None:
			raise RuntimeError("server rejects schema")
		return '[{"index":1,"title":"A"},{"index":2,"title":"B"}]'

	state = fake_client(producer)
	objs = pipeline.send_batches(["1.a", "2.b"], state.client, batch_size=2)
	assert [o["title"] for o in objs] == ["A", "B"]
	# 1回目(schema)失敗 + 同バッチを plain で再試行 = 2 calls
	assert len(state.calls) == 2
	assert state.calls[0].response_format is not None
	assert state.calls[1].response_format is None


def test_send_batches_channels_sliced_across_batches(fake_client):
	state = fake_client(
		[
			_schema_payload([{"index": 1, "title": "A"}, {"index": 2, "title": "B"}]),
			_schema_payload([{"index": 1, "title": "C"}]),
		]
	)
	prompts = prompt.number_titles(["a", "b", "c"])
	channels = ["ch1", "ch2", "ch3"]
	pipeline.send_batches(prompts, state.client, channels=channels, batch_size=2)
	assert "[ch1]" in state.calls[0].prompt
	assert "[ch2]" in state.calls[0].prompt
	assert "[ch3]" in state.calls[1].prompt
	assert "[ch1]" not in state.calls[1].prompt


# ---- extract_titles -----------------------------------------------------------


def test_extract_titles_returns_results(fake_client):
	state = fake_client([_schema_payload([{"index": 1, "original": "1.a song", "title": "a"}])])
	out = pipeline.extract_titles(["a song"], state.client, batch_size=10)
	assert out[0].title == "a"
	assert out[0].valid is True
	assert out[0].original == "a song"


def test_extract_titles_raises_on_validation_failure(fake_client):
	# LLM が 2 件中 1 件しか返さない → 失敗分の部分リトライも失敗 → ValueError
	state = fake_client(
		[
			_schema_payload([{"index": 1, "title": "a"}]),
			_schema_payload([]),  # リトライ分も空応答
		]
	)
	with pytest.raises(ValueError, match="does not match input titles"):
		pipeline.extract_titles(["a song", "b song"], state.client, batch_size=10)


def test_extract_titles_bypass_check(fake_client):
	# 件数不一致でも bypass_check なら例外を出さず返す（リトライもしない）
	state = fake_client([_schema_payload([{"index": 1, "title": "a"}])])
	out = pipeline.extract_titles(["a song", "b song"], state.client, batch_size=10, bypass_check=True)
	assert len(out) == 2
	assert out[0].title == "a"
	assert out[0].valid is True
	assert out[1].valid is False


def test_extract_titles_partial_retry_recovers(fake_client):
	# 検証に失敗した項目だけが再問い合わせされ、成功すれば全体が valid になる
	state = fake_client(
		[
			_schema_payload(
				[
					{"index": 1, "title": "a"},
					{"index": 2, "title": "zzz"},  # b song と不一致
				]
			),
			_schema_payload([{"index": 1, "title": "b"}]),  # リトライは 1 件のみ
		]
	)
	out = pipeline.extract_titles(["a song", "b song"], state.client, batch_size=10)
	assert [r.title for r in out] == ["a", "b"]
	assert [r.index for r in out] == [1, 2]
	assert all(r.valid for r in out)
	assert len(state.calls) == 2
	# リトライのプロンプトには失敗した 1 件だけが含まれる
	assert "b song" in state.calls[1].prompt
	assert "a song" not in state.calls[1].prompt
	# リトライは temperature を上げて同一出力の再発を避ける
	assert state.calls[1].temperature > state.calls[0].temperature


def test_extract_titles_retry_disabled(fake_client):
	# retry_invalid=0 なら再問い合わせせず即座に失敗する
	# （余計な呼び出しがあれば conftest の fake_client が AssertionError を出す）
	state = fake_client([_schema_payload([{"index": 1, "title": "zzz"}])])
	with pytest.raises(ValueError, match="does not match input titles"):
		pipeline.extract_titles(["a song"], state.client, batch_size=10, retry_invalid=0)


def test_extract_titles_preprocess_strips_noise_from_prompt(fake_client):
	state = fake_client([_schema_payload([{"index": 1, "title": "a song"}])])
	out = pipeline.extract_titles(["a song (Official Music Video)"], state.client)
	assert "Official Music Video" not in state.calls[0].prompt
	assert out[0].valid is True
	# original には前処理前の元タイトルが入る
	assert out[0].original == "a song (Official Music Video)"


def test_extract_titles_no_preprocess_keeps_raw_title(fake_client):
	state = fake_client([_schema_payload([{"index": 1, "title": "a song"}])])
	pipeline.extract_titles(["a song (Official Music Video)"], state.client, preprocess=False)
	assert "Official Music Video" in state.calls[0].prompt


# ---- TitleInput / channels ----------------------------------------------------


def test_extract_titles_with_channel(fake_client):
	state = fake_client([_schema_payload([{"index": 1, "title": "アイドル"}])])
	out = pipeline.extract_titles(
		[TitleInput("YOASOBI「アイドル」Official Music Video", "Official YOASOBI")],
		state.client,
	)
	assert "[Official YOASOBI]" in state.calls[0].prompt
	assert out[0].title == "アイドル"
	assert out[0].valid is True


def test_extract_titles_mixed_str_and_title_input(fake_client):
	state = fake_client(
		[
			_schema_payload(
				[
					{"index": 1, "title": "a"},
					{"index": 2, "title": "b"},
				]
			)
		]
	)
	out = pipeline.extract_titles(["a song", TitleInput("b song", "chB")], state.client)
	assert "[chB]" in state.calls[0].prompt
	assert [r.valid for r in out] == [True, True]


def test_extract_titles_channels_partial_retry(fake_client):
	state = fake_client(
		[
			_schema_payload(
				[
					{"index": 1, "title": "a"},
					{"index": 2, "title": "zzz"},
				]
			),
			_schema_payload([{"index": 1, "title": "b"}]),
		]
	)
	out = pipeline.extract_titles(
		[TitleInput("a song", "chA"), TitleInput("b song", "chB")],
		state.client,
		batch_size=10,
	)
	assert [r.title for r in out] == ["a", "b"]
	# リトライプロンプトには失敗した項目のチャンネルだけが含まれる
	assert "[chB]" in state.calls[1].prompt
	assert "[chA]" not in state.calls[1].prompt


def test_extract_titles_plain_strings_have_no_channel_hint(fake_client):
	state = fake_client([_schema_payload([{"index": 1, "title": "a"}])])
	out = pipeline.extract_titles(["a song"], state.client)
	assert "チャンネル名" not in state.calls[0].prompt
	assert out[0].valid is True
