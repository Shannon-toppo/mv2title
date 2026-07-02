import json

import pytest

from mv2title import cli
from mv2title.models import TitleResult


def _args(**over):
	base = dict(
		titles=[],
		input_file=None,
		output=None,
		format="json",
		batch_size=10,
		bypass_check=False,
		no_schema=False,
		base_url=None,
		model=None,
		debug=False,
	)
	base.update(over)
	return type("NS", (), base)()


def _fake_extract(inputs, client, **kw):
	"""入力をそのまま大文字化して返す extract_titles のフェイク。"""
	return [TitleResult(index=i + 1, original=t.title, title=t.title.upper(), valid=True) for i, t in enumerate(inputs)]


@pytest.fixture
def fake_pipeline(monkeypatch):
	"""Config / LLMClient / pipeline.extract_titles をモックし、呼び出しを捕捉する。"""
	state = {"config_kwargs": None, "inputs": None, "kwargs": None, "extract": _fake_extract}

	class _FakeConfig:
		@staticmethod
		def from_env(**kw):
			state["config_kwargs"] = kw
			return object()  # Config の代わりのダミー

	def fake_extract(inputs, client, **kw):
		state["inputs"] = list(inputs)
		state["kwargs"] = kw
		return state["extract"](inputs, client, **kw)

	monkeypatch.setattr(cli, "Config", _FakeConfig)
	monkeypatch.setattr(cli, "LLMClient", lambda config: object())
	monkeypatch.setattr(cli.pipeline, "extract_titles", fake_extract)
	return state


# ---- 入力の読み取り -----------------------------------------------------------


def test_read_titles_positional():
	assert cli._read_titles(_args(titles=["a", "b"])) == ["a", "b"]


def test_read_titles_file(tmp_path):
	p = tmp_path / "in.txt"
	p.write_text("a\n\nb\n", encoding="utf-8")
	assert cli._read_titles(_args(input_file=str(p))) == ["a", "b"]


def test_read_titles_stdin(monkeypatch):
	import io

	fake_stdin = io.StringIO("x\ny\n")
	fake_stdin.isatty = lambda: False
	monkeypatch.setattr("sys.stdin", fake_stdin)
	assert cli._read_titles(_args()) == ["x", "y"]


def test_read_titles_priority_positional_over_file(tmp_path):
	p = tmp_path / "in.txt"
	p.write_text("fromfile\n", encoding="utf-8")
	assert cli._read_titles(_args(titles=["pos"], input_file=str(p))) == ["pos"]


# ---- 出力フォーマット ----------------------------------------------------------


def test_format_json():
	res = [{"index": 1, "original": "o", "title": "t", "valid": True}]
	assert json.loads(cli._format_output(res, "json")) == res


def test_format_titles():
	res = [{"title": "A"}, {"title": "B"}]
	assert cli._format_output(res, "titles") == "A\nB"


def test_format_tsv():
	res = [{"index": 1, "original": "o", "title": "t", "valid": True}]
	out = cli._format_output(res, "tsv").splitlines()
	assert out[0] == "index\toriginal\ttitle\tvalid"
	assert out[1] == "1\to\tt\tTrue"


def test_format_unknown():
	with pytest.raises(ValueError):
		cli._format_output([], "xml")


# ---- 引数パーサ ---------------------------------------------------------------


def test_build_parser_defaults():
	p = cli.build_parser()
	ns = p.parse_args(["foo", "bar"])
	assert ns.titles == ["foo", "bar"]
	assert ns.format == "json"
	assert ns.batch_size == 10


def test_build_parser_channel_flag():
	p = cli.build_parser()
	ns = p.parse_args(["--channel", "YOASOBI", "foo"])
	assert ns.channel == "YOASOBI"


# ---- main() ------------------------------------------------------------------


def test_main_no_input_errors(monkeypatch):
	# 標準入力を tty 扱いにして「入力なし」を作る
	import sys

	monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
	with pytest.raises(SystemExit):
		cli.main(["--format", "titles"])


def test_main_end_to_end(fake_pipeline, capsys):
	rc = cli.main(["--format", "titles", "abc", "def"])
	assert rc == 0
	assert capsys.readouterr().out.strip() == "ABC\nDEF"


def test_main_base_url_guard(monkeypatch, capsys):
	class _BoomConfig:
		@staticmethod
		def from_env(**kw):
			raise ValueError("BASE_URL 未設定")

	monkeypatch.setattr(cli, "Config", _BoomConfig)
	rc = cli.main(["x"])
	assert rc == 2
	assert "BASE_URL" in capsys.readouterr().err


def test_main_validation_error_returns_1(fake_pipeline, capsys):
	def boom(inputs, client, **kw):
		raise ValueError("Output does not match input titles.")

	fake_pipeline["extract"] = boom
	rc = cli.main(["x"])
	assert rc == 1
	assert "検証エラー" in capsys.readouterr().err


def test_main_passes_preprocess_and_retry(fake_pipeline):
	rc = cli.main(["--no-preprocess", "--retry", "2", "x"])
	assert rc == 0
	assert fake_pipeline["kwargs"]["preprocess"] is False
	assert fake_pipeline["kwargs"]["retry_invalid"] == 2


def test_main_preprocess_enabled_by_default(fake_pipeline):
	assert cli.main(["x"]) == 0
	assert fake_pipeline["kwargs"]["preprocess"] is True
	assert fake_pipeline["kwargs"]["retry_invalid"] == 1


def test_main_passes_timeout_to_config(fake_pipeline):
	assert cli.main(["--timeout", "5", "x"]) == 0
	assert fake_pipeline["config_kwargs"]["timeout"] == 5.0


def test_main_omits_timeout_when_not_given(fake_pipeline):
	# timeout 未指定時は Config に渡さず、既定値に任せる
	assert cli.main(["x"]) == 0
	assert "timeout" not in fake_pipeline["config_kwargs"]


def test_main_passes_model_and_base_url_to_config(fake_pipeline):
	assert cli.main(["--model", "my-model", "--base-url", "http://x/v1/", "x"]) == 0
	assert fake_pipeline["config_kwargs"]["model"] == "my-model"
	assert fake_pipeline["config_kwargs"]["base_url"] == "http://x/v1/"


def test_main_writes_output_file(fake_pipeline, tmp_path):
	out = tmp_path / "out.json"
	rc = cli.main(["--output", str(out), "hello"])
	assert rc == 0
	data = json.loads(out.read_text(encoding="utf-8"))
	assert data[0]["title"] == "HELLO"


def test_main_passes_channel_as_title_input(fake_pipeline):
	rc = cli.main(["--channel", "MyCh", "a", "b"])
	assert rc == 0
	assert [i.channel for i in fake_pipeline["inputs"]] == ["MyCh", "MyCh"]


def test_main_no_channel_passes_none(fake_pipeline):
	assert cli.main(["x"]) == 0
	assert [i.channel for i in fake_pipeline["inputs"]] == [None]


# ---- --input-json -----------------------------------------------------------


def test_read_input_json(tmp_path):
	p = tmp_path / "in.json"
	p.write_text(
		json.dumps(
			[
				{"title": "YOASOBI「アイドル」", "channel": "Official YOASOBI"},
				{"title": "ヨルシカ - 春泥棒"},
			],
			ensure_ascii=False,
		),
		encoding="utf-8",
	)
	titles, channels = cli._read_input_json(str(p))
	assert titles == ["YOASOBI「アイドル」", "ヨルシカ - 春泥棒"]
	assert channels == ["Official YOASOBI", None]


def test_read_input_json_skips_empty_title(tmp_path):
	p = tmp_path / "in.json"
	p.write_text('[{"title": "a"}, {"title": "  "}, {"title": "b"}]', encoding="utf-8")
	titles, channels = cli._read_input_json(str(p))
	assert titles == ["a", "b"]
	assert len(channels) == 2


def test_read_input_json_rejects_non_array(tmp_path):
	p = tmp_path / "in.json"
	p.write_text('{"title": "a"}', encoding="utf-8")
	with pytest.raises(ValueError, match="JSON配列"):
		cli._read_input_json(str(p))


def test_read_input_json_rejects_missing_title(tmp_path):
	p = tmp_path / "in.json"
	p.write_text('[{"channel": "ch"}]', encoding="utf-8")
	with pytest.raises(ValueError, match="title"):
		cli._read_input_json(str(p))


def test_main_input_json_end_to_end(fake_pipeline, tmp_path):
	p = tmp_path / "in.json"
	p.write_text(
		json.dumps(
			[
				{"title": "title A", "channel": "chA"},
				{"title": "title B"},
			],
			ensure_ascii=False,
		),
		encoding="utf-8",
	)
	rc = cli.main(["--input-json", str(p)])
	assert rc == 0
	assert [i.title for i in fake_pipeline["inputs"]] == ["title A", "title B"]
	assert [i.channel for i in fake_pipeline["inputs"]] == ["chA", None]


def test_main_input_json_channel_flag_overrides(fake_pipeline, tmp_path):
	p = tmp_path / "in.json"
	p.write_text('[{"title": "a", "channel": "fromJson"}, {"title": "b"}]', encoding="utf-8")
	rc = cli.main(["--input-json", str(p), "--channel", "override"])
	assert rc == 0
	assert [i.channel for i in fake_pipeline["inputs"]] == ["override", "override"]


def test_main_input_json_invalid_file(capsys):
	rc = cli.main(["--input-json", "/nonexistent/file.json"])
	assert rc == 2
