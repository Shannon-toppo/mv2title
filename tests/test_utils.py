import pytest

from mv2title import utils


def test_edit_title_numbers_from_one():
	assert utils.edit_title(["a", "b", "c"]) == ["1.a", "2.b", "3.c"]


def test_edit_title_empty():
	assert utils.edit_title([]) == []


def test_chunk_list_even():
	assert list(utils.chunk_list([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]


def test_chunk_list_remainder():
	assert list(utils.chunk_list([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_chunk_list_larger_than_list():
	assert list(utils.chunk_list([1, 2], 10)) == [[1, 2]]


def test_chunk_list_empty():
	assert list(utils.chunk_list([], 3)) == []


def test_strip_index_basic():
	assert utils.strip_index("1.タイトル") == "タイトル"


def test_strip_index_only_first_prefix():
	# 本来の数字・ドットは保持し、先頭の採番だけ剥がす
	assert utils.strip_index("12.3.14 song") == "3.14 song"


def test_strip_index_no_prefix():
	assert utils.strip_index("no prefix") == "no prefix"


def test_strip_index_roundtrip_with_edit_title():
	titles = ["曲A", "曲B feat. X", "10秒"]
	numbered = utils.edit_title(titles)
	assert [utils.strip_index(t) for t in numbered] == titles


def test_read_titles(tmp_path):
	p = tmp_path / "t.txt"
	p.write_text("  曲A \n\n曲B\n  \n曲C\n", encoding="utf-8")
	assert utils.read_titles(str(p)) == ["曲A", "曲B", "曲C"]


def test_read_titles_missing(tmp_path):
	with pytest.raises(FileNotFoundError):
		utils.read_titles(str(tmp_path / "nope.txt"))


# ---- clean_title ------------------------------------------------------------

def test_clean_title_removes_noise_brackets():
	assert utils.clean_title("Artist「曲名」(Official Music Video)") == "Artist「曲名」"
	assert utils.clean_title("曲名【MV】") == "曲名"
	assert utils.clean_title("Song [OFFICIAL VIDEO]") == "Song"
	assert utils.clean_title("曲名（公式）") == "曲名"


def test_clean_title_keeps_informative_brackets():
	# ノイズキーワードを含まない括弧（曲名の一部かもしれない）は残す
	assert utils.clean_title("Song (Acoustic)") == "Song (Acoustic)"
	assert utils.clean_title("アーティスト『曲名』") == "アーティスト『曲名』"


def test_clean_title_removes_feat():
	assert utils.clean_title("Song feat. Someone") == "Song"
	assert utils.clean_title("Song (feat. Someone)") == "Song"
	assert utils.clean_title("Song ft. A & B") == "Song"


def test_clean_title_trims_leftover_separators():
	assert utils.clean_title("曲名 (Official Music Video) - ") == "曲名"


def test_clean_title_falls_back_when_everything_removed():
	# 全部ノイズ扱いになった場合は元のタイトルを返す（空文字列にしない）
	assert utils.clean_title("【MV】") == "【MV】"


def test_clean_title_plain_passthrough():
	assert utils.clean_title("ただの曲名") == "ただの曲名"
	assert utils.clean_title("") == ""


# ---- normalize_for_match / is_title_match -----------------------------------

def test_normalize_for_match_nfkc_casefold_whitespace():
	assert utils.normalize_for_match("ＡＢＣ　Ｓｏｎｇ") == "abc song"
	assert utils.normalize_for_match("  A   B  ") == "a b"


def test_is_title_match_substring():
	assert utils.is_title_match("曲名", "アーティスト 曲名 MV") is True


def test_is_title_match_fullwidth_and_case():
	assert utils.is_title_match("ABC", "ｱｰﾃｨｽﾄ ＡＢＣ ｓｏｎｇ") is True


def test_is_title_match_multiple_sources():
	# 元タイトルに直接含まれなくても、前処理後タイトルに含まれていれば一致
	assert utils.is_title_match("A B", "A 【MV】 B", "A B") is True


def test_is_title_match_empty_title_is_false():
	assert utils.is_title_match("", "anything") is False
	assert utils.is_title_match("   ", "anything") is False


def test_is_title_match_mismatch():
	assert utils.is_title_match("xyz", "a song") is False
