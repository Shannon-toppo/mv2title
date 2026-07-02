from mv2title import prompt

# ---- number_titles / strip_index ---------------------------------------------


def test_number_titles_numbers_from_one():
	assert prompt.number_titles(["a", "b", "c"]) == ["1.a", "2.b", "3.c"]


def test_number_titles_empty():
	assert prompt.number_titles([]) == []


def test_strip_index_basic():
	assert prompt.strip_index("1.タイトル") == "タイトル"


def test_strip_index_only_first_prefix():
	# 本来の数字・ドットは保持し、先頭の採番だけ剥がす
	assert prompt.strip_index("12.3.14 song") == "3.14 song"


def test_strip_index_no_prefix():
	assert prompt.strip_index("no prefix") == "no prefix"


def test_strip_index_roundtrip_with_number_titles():
	titles = ["曲A", "曲B feat. X", "10秒"]
	numbered = prompt.number_titles(titles)
	assert [prompt.strip_index(t) for t in numbered] == titles


# ---- make_json_prompt ---------------------------------------------------------


def test_make_json_prompt_with_channels():
	batch = ["1.YOASOBI「アイドル」", "2.ヨルシカ - 春泥棒"]
	channels = ["Official YOASOBI", "ヨルシカ"]
	p = prompt.make_json_prompt(batch, channels=channels)
	assert "[Official YOASOBI]" in p
	assert "[ヨルシカ]" in p
	assert "チャンネル名" in p


def test_make_json_prompt_channels_none_backward_compat():
	batch = ["1.some title"]
	prompt_without = prompt.make_json_prompt(batch)
	prompt_none = prompt.make_json_prompt(batch, channels=None)
	assert prompt_without == prompt_none
	assert "チャンネル名" not in prompt_without


def test_make_json_prompt_mixed_channels():
	batch = ["1.title A", "2.title B", "3.title C"]
	channels = ["ChA", None, "ChC"]
	p = prompt.make_json_prompt(batch, channels=channels)
	assert "[ChA]" in p
	assert "[ChC]" in p
	assert "チャンネル名" in p
	# チャンネルなしの項目にはブラケットが付かない
	assert "2.title B" in p


def test_make_json_prompt_empty_channel_treated_as_none():
	batch = ["1.title"]
	channels = ["  "]
	p = prompt.make_json_prompt(batch, channels=channels)
	assert "チャンネル名" not in p
	assert "1.title" in p
