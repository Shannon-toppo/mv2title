import pytest

from mv2title import main_list


def test_send_batches_python_literal(fake_send):
	fake_send(["['A', 'B']"])
	out = main_list.send_batches(["1.a", "2.b"], batch_size=10)
	assert out == ["A", "B"]


def test_send_batches_comma_fallback(fake_send):
	fake_send(["A, B, C"])
	out = main_list.send_batches(["1.a", "2.b", "3.c"], batch_size=10)
	assert out == ["A", "B", "C"]


def test_send_batches_multiple_batches(fake_send):
	fake_send(["['A', 'B']", "['C']"])
	out = main_list.send_batches(["1.a", "2.b", "3.c"], batch_size=2)
	assert out == ["A", "B", "C"]


def test_res_check_positional_ok():
	inp = ["a song", "b song"]
	resp = ["a song", "b song"]
	assert main_list.res_check(inp, resp, False) is True


def test_res_check_substring_ok():
	inp = ["the a song (official)", "b"]
	resp = ["a song", "b"]
	assert main_list.res_check(inp, resp, False) is True


def test_res_check_length_mismatch():
	assert main_list.res_check(["a", "b"], ["a"], False) is False


def test_res_check_content_mismatch():
	assert main_list.res_check(["a song"], ["xyz"], False) is False


def test_main_happy(fake_send):
	fake_send(["['A', 'B']"])
	out = main_list.main(["a song A", "b song B"], batch_size=10, bypass_check=True)
	assert out == ["A", "B"]


def test_main_raises_on_mismatch(fake_send):
	fake_send(["['xyz']"])
	with pytest.raises(ValueError):
		main_list.main(["a song"], batch_size=10)


def test_main_emits_deprecation_warning(fake_send):
	fake_send(["['A']"])
	with pytest.warns(DeprecationWarning):
		main_list.main(["a song A"], batch_size=10, bypass_check=True)
