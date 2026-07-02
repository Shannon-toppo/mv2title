from mv2title import parsing

# ---- parse_json_response ----------------------------------------------------


def test_parse_pure_json_array():
	raw = '[{"index":1,"original":"a","title":"A"}]'
	assert parsing.parse_json_response(raw) == [{"index": 1, "original": "a", "title": "A"}]


def test_parse_json_with_surrounding_text():
	raw = 'ここに結果: [{"index":1,"title":"A"}] です'
	assert parsing.parse_json_response(raw) == [{"index": 1, "title": "A"}]


def test_parse_results_wrapper_returned_as_dict():
	raw = '{"results":[{"index":1,"title":"A"}]}'
	parsed = parsing.parse_json_response(raw)
	assert isinstance(parsed, dict)
	assert parsed["results"] == [{"index": 1, "title": "A"}]


def test_parse_python_literal_fallback():
	raw = "['A', 'B']"
	assert parsing.parse_json_response(raw) == ["A", "B"]


def test_parse_comma_split_last_resort():
	raw = "A, B, C"
	assert parsing.parse_json_response(raw) == ["A", "B", "C"]


def test_parse_none():
	assert parsing.parse_json_response(None) is None


# ---- normalize_batch_items --------------------------------------------------


def test_normalize_unwraps_results_dict():
	parsed = {"results": [{"index": 1, "title": "A"}]}
	objs = parsing.normalize_batch_items(parsed, ["1.a"], base=0)
	assert objs == [{"index": 1, "original": "a", "title": "A"}]


def test_normalize_none_returns_empty():
	assert parsing.normalize_batch_items(None, ["1.a"], base=0) == []


def test_normalize_unexpected_type_returns_empty():
	assert parsing.normalize_batch_items(42, ["1.a"], base=0) == []


def test_normalize_converts_local_index_to_global():
	parsed = [{"index": 1, "title": "C"}, {"index": 2, "title": "D"}]
	objs = parsing.normalize_batch_items(parsed, ["3.c", "4.d"], base=2)
	assert [o["index"] for o in objs] == [3, 4]


def test_normalize_out_of_range_index_falls_back_to_position():
	parsed = [{"index": 99, "title": "A"}]
	objs = parsing.normalize_batch_items(parsed, ["1.a"], base=0)
	assert objs[0]["index"] == 1


def test_normalize_original_is_denumbered_input():
	# LLM が original を番号付きで echo しても、入力側の生タイトルを採用
	parsed = [{"index": 1, "original": "1.ヨルシカ Music Video", "title": "T"}]
	objs = parsing.normalize_batch_items(parsed, ["1.ヨルシカ Music Video"], base=0)
	assert objs[0]["original"] == "ヨルシカ Music Video"


def test_normalize_loose_title_keys():
	parsed = [{"index": 1, "new_title": "FromNew"}]
	objs = parsing.normalize_batch_items(parsed, ["1.x"], base=0)
	assert objs[0]["title"] == "FromNew"


def test_normalize_missing_title_becomes_empty():
	parsed = [{"index": 1}]
	objs = parsing.normalize_batch_items(parsed, ["1.x"], base=0)
	assert objs[0]["title"] == ""


def test_normalize_string_items_pair_with_batch():
	objs = parsing.normalize_batch_items(["A", "B"], ["1.a", "2.b"], base=0)
	assert [o["title"] for o in objs] == ["A", "B"]
	assert [o["original"] for o in objs] == ["a", "b"]
