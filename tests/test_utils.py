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
