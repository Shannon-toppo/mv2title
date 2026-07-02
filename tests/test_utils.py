from mv2title import utils


def test_chunk_list_even():
	assert list(utils.chunk_list([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]


def test_chunk_list_remainder():
	assert list(utils.chunk_list([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_chunk_list_larger_than_list():
	assert list(utils.chunk_list([1, 2], 10)) == [[1, 2]]


def test_chunk_list_empty():
	assert list(utils.chunk_list([], 3)) == []
