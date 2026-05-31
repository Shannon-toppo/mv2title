import json

import pytest

from mv2title import cli


def _args(**over):
    base = dict(titles=[], input_file=None, output=None, format="json",
                batch_size=10, bypass_check=False, no_schema=False,
                base_url=None, model=None, debug=False)
    base.update(over)
    return type("NS", (), base)()


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


def test_build_parser_defaults():
    p = cli.build_parser()
    ns = p.parse_args(["foo", "bar"])
    assert ns.titles == ["foo", "bar"]
    assert ns.format == "json"
    assert ns.batch_size == 10


def test_main_no_input_errors(monkeypatch):
    # 標準入力を tty 扱いにして「入力なし」を作る
    import sys
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    with pytest.raises(SystemExit):
        cli.main(["--format", "titles"])


def test_main_end_to_end(monkeypatch, capsys):
    # connect.init と main_json.main をモックして CLI 全体を検証
    monkeypatch.setattr(cli.connect, "init", lambda **kw: None)
    monkeypatch.setattr(cli.connect, "url", "http://x/v1/", raising=False)
    monkeypatch.setattr(
        cli.main_json, "main",
        lambda titles, **kw: [
            {"index": i + 1, "original": t, "title": t.upper(), "valid": True}
            for i, t in enumerate(titles)
        ],
    )
    rc = cli.main(["--format", "titles", "abc", "def"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "ABC\nDEF"


def test_main_base_url_guard(monkeypatch, capsys):
    def boom(**kw):
        raise ValueError("BASE_URL 未設定")
    monkeypatch.setattr(cli.connect, "init", boom)
    monkeypatch.setattr(cli.connect, "url", None, raising=False)
    rc = cli.main(["x"])
    assert rc == 2
    assert "BASE_URL" in capsys.readouterr().err


def test_main_writes_output_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.connect, "init", lambda **kw: None)
    monkeypatch.setattr(cli.connect, "url", "http://x/v1/", raising=False)
    monkeypatch.setattr(
        cli.main_json, "main",
        lambda titles, **kw: [{"index": 1, "original": titles[0],
                               "title": "T", "valid": True}],
    )
    out = tmp_path / "out.json"
    rc = cli.main(["--output", str(out), "hello"])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["title"] == "T"
