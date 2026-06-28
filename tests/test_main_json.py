import json

import pytest

from mv2title import main_json


# ---- _parse_json_response -------------------------------------------------

def test_parse_pure_json_array():
	raw = '[{"index":1,"original":"a","title":"A"}]'
	assert main_json._parse_json_response(raw) == [
		{"index": 1, "original": "a", "title": "A"}
	]


def test_parse_json_with_surrounding_text():
	raw = 'ここに結果: [{"index":1,"title":"A"}] です'
	assert main_json._parse_json_response(raw) == [{"index": 1, "title": "A"}]


def test_parse_results_wrapper_returned_as_dict():
	raw = '{"results":[{"index":1,"title":"A"}]}'
	parsed = main_json._parse_json_response(raw)
	assert isinstance(parsed, dict)
	assert parsed["results"] == [{"index": 1, "title": "A"}]


def test_parse_python_literal_fallback():
	raw = "['A', 'B']"
	assert main_json._parse_json_response(raw) == ["A", "B"]


def test_parse_comma_split_last_resort():
	raw = "A, B, C"
	assert main_json._parse_json_response(raw) == ["A", "B", "C"]


def test_parse_none():
	assert main_json._parse_json_response(None) is None


# ---- send_batches_json ----------------------------------------------------

def _schema_payload(items):
	return json.dumps({"results": items}, ensure_ascii=False)


def test_send_batches_single_batch_happy(fake_send):
	fake_send([_schema_payload([
		{"index": 1, "original": "1.x", "title": "X"},
		{"index": 2, "original": "2.y", "title": "Y"},
	])])
	prompts = ["1.foo", "2.bar"]
	objs = main_json.send_batches_json(prompts, batch_size=10)
	assert [o["index"] for o in objs] == [1, 2]
	assert [o["title"] for o in objs] == ["X", "Y"]


def test_send_batches_index_is_batch_local_converted_to_global(fake_send):
	# 各バッチで index が 1 から振り直されても、グローバル連番になること
	fake_send([
		_schema_payload([
			{"index": 1, "title": "A"},
			{"index": 2, "title": "B"},
		]),
		_schema_payload([
			{"index": 1, "title": "C"},
			{"index": 2, "title": "D"},
		]),
	])
	prompts = main_json.utils.edit_title(["a", "b", "c", "d"])
	objs = main_json.send_batches_json(prompts, batch_size=2)
	assert [o["index"] for o in objs] == [1, 2, 3, 4]
	assert [o["title"] for o in objs] == ["A", "B", "C", "D"]


def test_send_batches_original_is_denumbered(fake_send):
	# LLM が original を番号付きで echo しても、入力側の生タイトルを採用
	fake_send([_schema_payload([
		{"index": 1, "original": "1.ヨルシカ Music Video", "title": "T"},
	])])
	prompts = main_json.utils.edit_title(["ヨルシカ Music Video"])
	objs = main_json.send_batches_json(prompts, batch_size=10)
	assert objs[0]["original"] == "ヨルシカ Music Video"


def test_send_batches_count_mismatch_does_not_cascade(fake_send):
	# 1 バッチ目が 1 件しか返さなくても 2 バッチ目の index がずれない
	fake_send([
		_schema_payload([{"index": 1, "title": "A"}]),          # 2件中1件のみ
		_schema_payload([{"index": 1, "title": "C"},
						 {"index": 2, "title": "D"}]),
	])
	prompts = main_json.utils.edit_title(["a", "b", "c", "d"])
	objs = main_json.send_batches_json(prompts, batch_size=2)
	# 2 バッチ目はグローバル index 3,4 になる
	assert sorted(o["index"] for o in objs) == [1, 3, 4]


def test_send_batches_loose_title_keys(fake_send):
	fake_send([_schema_payload([
		{"index": 1, "original": "1.x", "new_title": "FromNew"},
	])])
	objs = main_json.send_batches_json(["1.x"], batch_size=10)
	assert objs[0]["title"] == "FromNew"


def test_send_batches_string_items(fake_send):
	fake_send(['["A", "B"]'])
	prompts = main_json.utils.edit_title(["a", "b"])
	objs = main_json.send_batches_json(prompts, batch_size=10, use_schema=False)
	assert [o["title"] for o in objs] == ["A", "B"]
	assert [o["original"] for o in objs] == ["a", "b"]


def test_send_batches_uses_schema_by_default(fake_send):
	state = fake_send([_schema_payload([{"index": 1, "title": "A"}])])
	main_json.send_batches_json(["1.a"], batch_size=10)
	assert state.calls[0].response_format is not None


def test_send_batches_no_schema_flag(fake_send):
	state = fake_send(['[{"index":1,"title":"A"}]'])
	main_json.send_batches_json(["1.a"], batch_size=10, use_schema=False)
	assert state.calls[0].response_format is None


def test_send_batches_falls_back_when_schema_rejected(fake_send):
	# 最初の schema 付き呼び出しは例外、以降は plain で成功させる
	def producer(prompt, response_format=None):
		if response_format is not None:
			raise RuntimeError("server rejects schema")
		return '[{"index":1,"title":"A"},{"index":2,"title":"B"}]'

	state = fake_send(producer)
	objs = main_json.send_batches_json(["1.a", "2.b"], batch_size=2)
	assert [o["title"] for o in objs] == ["A", "B"]
	# 1回目(schema)失敗 + 同バッチを plain で再試行 = 2 calls
	assert len(state.calls) == 2
	assert state.calls[0].response_format is not None
	assert state.calls[1].response_format is None


# ---- res_check_json -------------------------------------------------------

def test_res_check_all_valid():
	inp = ["a song", "b song"]
	resp = [
		{"index": 1, "original": "a song", "title": "a"},
		{"index": 2, "original": "b song", "title": "b"},
	]
	ok, validated = main_json.res_check_json(inp, resp)
	assert ok is True
	assert all(o["valid"] for o in validated)


def test_res_check_matches_by_index_when_shuffled():
	inp = ["a song", "b song", "c song"]
	resp = [
		{"index": 3, "original": "c song", "title": "c"},
		{"index": 1, "original": "a song", "title": "a"},
		{"index": 2, "original": "b song", "title": "b"},
	]
	ok, validated = main_json.res_check_json(inp, resp)
	assert ok is True
	assert all(o["valid"] for o in validated)
	# 戻り値は入力と同順に並べ直される
	assert [o["index"] for o in validated] == [1, 2, 3]
	assert [o["title"] for o in validated] == ["a", "b", "c"]


def test_res_check_length_mismatch_but_per_item_validated():
	inp = ["a song", "b song", "c song"]
	resp = [
		{"index": 1, "original": "a song", "title": "a"},
		{"index": 3, "original": "c song", "title": "c"},
	]
	ok, validated = main_json.res_check_json(inp, resp)
	assert ok is False  # 件数不一致なので全体は False
	assert len(validated) == 3  # 欠けた入力にもプレースホルダが入る
	by_idx = {o["index"]: o for o in validated}
	assert by_idx[1]["valid"] is True
	assert by_idx[3]["valid"] is True
	assert by_idx[2]["valid"] is False
	assert by_idx[2]["title"] == ""


def test_res_check_substring_mismatch():
	inp = ["a song"]
	resp = [{"index": 1, "original": "totally different", "title": "X"}]
	ok, validated = main_json.res_check_json(inp, resp)
	assert ok is False
	assert validated[0]["valid"] is False


def test_res_check_validates_title_not_original_echo():
	# original が入力と一致していても title が無関係なら invalid。
	# （以前は original 同士の比較だったため常に valid になっていた回帰テスト）
	inp = ["some long video title"]
	resp = [{"index": 1, "original": "some long video title", "title": "unrelated"}]
	ok, validated = main_json.res_check_json(inp, resp)
	assert ok is False
	assert validated[0]["valid"] is False


def test_res_check_normalizes_fullwidth_and_case():
	# NFKC 正規化 + casefold 後に比較される（全角/半角・大文字小文字の差を吸収）
	inp = ["ＳｏｎｇＴｉｔｌｅ Official"]
	resp = [{"index": 1, "title": "songtitle"}]
	ok, validated = main_json.res_check_json(inp, resp)
	assert ok is True
	assert validated[0]["valid"] is True


def test_res_check_empty_title_invalid():
	# 空文字列はあらゆる文字列の部分文字列だが、valid にしてはいけない
	ok, validated = main_json.res_check_json(["a song"], [{"index": 1, "title": ""}])
	assert ok is False
	assert validated[0]["valid"] is False


def test_res_check_duplicate_index_first_wins():
	inp = ["a song"]
	resp = [
		{"index": 1, "title": "a"},
		{"index": 1, "title": "zzz"},
	]
	ok, validated = main_json.res_check_json(inp, resp)
	assert len(validated) == 1
	assert validated[0]["title"] == "a"
	assert validated[0]["valid"] is True
	assert ok is False  # 件数不一致（2 件返ってきている）


def test_res_check_matches_against_cleaned_source():
	# 前処理でノイズ除去した文字列から抽出された title も valid と判定できる
	inp = ["A 【MV】 B"]
	resp = [{"index": 1, "title": "A B"}]
	ok, validated = main_json.res_check_json(inp, resp, cleaned=["A B"])
	assert ok is True
	assert validated[0]["valid"] is True
	# original は前処理後ではなく元のタイトル
	assert validated[0]["original"] == "A 【MV】 B"


# ---- main -----------------------------------------------------------------

def test_main_returns_validated(fake_send):
	fake_send([_schema_payload([
		{"index": 1, "original": "1.a song", "title": "a"},
	])])
	out = main_json.main(["a song"], batch_size=10)
	assert out[0]["title"] == "a"
	assert out[0]["valid"] is True


def test_main_raises_on_validation_failure(fake_send):
	# LLM が 2 件中 1 件しか返さない → 失敗分の部分リトライも失敗 → ValueError
	fake_send([
		_schema_payload([{"index": 1, "title": "a"}]),
		_schema_payload([]),  # リトライ分も空応答
	])
	with pytest.raises(ValueError):
		main_json.main(["a song", "b song"], batch_size=10)


def test_main_bypass_check(fake_send):
	# 件数不一致でも bypass_check なら例外を出さず返す（リトライもしない）
	fake_send([_schema_payload([
		{"index": 1, "title": "a"},
	])])
	out = main_json.main(["a song", "b song"], batch_size=10, bypass_check=True)
	assert len(out) == 2
	assert out[0]["title"] == "a"
	assert out[0]["valid"] is True
	assert out[1]["valid"] is False


def test_main_partial_retry_recovers(fake_send):
	# 検証に失敗した項目だけが再問い合わせされ、成功すれば全体が valid になる
	state = fake_send([
		_schema_payload([
			{"index": 1, "title": "a"},
			{"index": 2, "title": "zzz"},  # b song と不一致
		]),
		_schema_payload([{"index": 1, "title": "b"}]),  # リトライは 1 件のみ
	])
	out = main_json.main(["a song", "b song"], batch_size=10)
	assert [o["title"] for o in out] == ["a", "b"]
	assert [o["index"] for o in out] == [1, 2]
	assert all(o["valid"] for o in out)
	assert len(state.calls) == 2
	# リトライのプロンプトには失敗した 1 件だけが含まれる
	assert "b song" in state.calls[1].prompt
	assert "a song" not in state.calls[1].prompt
	# リトライは temperature を上げて同一出力の再発を避ける
	assert state.calls[1].temperature > state.calls[0].temperature


def test_main_retry_disabled(fake_send):
	# retry_invalid=0 なら再問い合わせせず即座に失敗する
	# （余計な呼び出しがあれば conftest の fake_send が AssertionError を出す）
	fake_send([_schema_payload([{"index": 1, "title": "zzz"}])])
	with pytest.raises(ValueError):
		main_json.main(["a song"], batch_size=10, retry_invalid=0)


def test_main_preprocess_strips_noise_from_prompt(fake_send):
	state = fake_send([_schema_payload([{"index": 1, "title": "a song"}])])
	out = main_json.main(["a song (Official Music Video)"])
	assert "Official Music Video" not in state.calls[0].prompt
	assert out[0]["valid"] is True
	# original には前処理前の元タイトルが入る
	assert out[0]["original"] == "a song (Official Music Video)"


def test_main_no_preprocess_keeps_raw_title(fake_send):
	state = fake_send([_schema_payload([{"index": 1, "title": "a song"}])])
	main_json.main(["a song (Official Music Video)"], preprocess=False)
	assert "Official Music Video" in state.calls[0].prompt
