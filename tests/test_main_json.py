"""旧 API 互換シム(main_json)のテスト。

新 API のテストは test_pipeline.py / test_validation.py / test_parsing.py を参照。
シムは「connect.init() 済みのモジュールレベル send_message へ委譲する」旧契約を
維持するため、fake_send(connect.send_message の monkeypatch)で検証する。
"""

import json

import pytest

from mv2title import connect, main_json


def _schema_payload(items):
	return json.dumps({"results": items}, ensure_ascii=False)


def test_main_warns_and_returns_dicts(fake_send):
	fake_send([_schema_payload([{"index": 1, "original": "1.a song", "title": "a"}])])
	with pytest.warns(DeprecationWarning):
		out = main_json.main(["a song"])
	assert out == [{"index": 1, "original": "a song", "title": "a", "valid": True}]


def test_main_requires_connect_init(monkeypatch):
	# 旧契約: connect.init() を呼んでいなければ RuntimeError
	monkeypatch.setattr(connect, "_default_client", None)
	with pytest.warns(DeprecationWarning), pytest.raises(RuntimeError):
		main_json.main(["a song"])


def test_main_channels_appear_in_prompt(fake_send):
	state = fake_send([_schema_payload([{"index": 1, "title": "アイドル"}])])
	with pytest.warns(DeprecationWarning):
		out = main_json.main(
			["YOASOBI「アイドル」Official Music Video"],
			channels=["Official YOASOBI"],
		)
	assert "[Official YOASOBI]" in state.calls[0].prompt
	assert out[0]["title"] == "アイドル"
	assert out[0]["valid"] is True


def test_main_channels_length_mismatch_raises():
	with pytest.warns(DeprecationWarning), pytest.raises(ValueError, match="channels の長さ"):
		main_json.main(["a", "b"], channels=["ch1"])


def test_main_raises_on_validation_failure(fake_send):
	fake_send(
		[
			_schema_payload([{"index": 1, "title": "zzz"}]),
			_schema_payload([]),  # リトライ分も失敗
		]
	)
	with pytest.warns(DeprecationWarning), pytest.raises(ValueError):
		main_json.main(["a song"])


def test_send_batches_json_warns_and_delegates(fake_send):
	fake_send([_schema_payload([{"index": 1, "title": "A"}])])
	with pytest.warns(DeprecationWarning):
		objs = main_json.send_batches_json(["1.a"], batch_size=10)
	assert objs[0]["title"] == "A"


def test_res_check_json_warns_and_returns_dicts():
	with pytest.warns(DeprecationWarning):
		ok, validated = main_json.res_check_json(["a song"], [{"index": 1, "title": "a"}])
	assert ok is True
	assert validated[0] == {"index": 1, "original": "a song", "title": "a", "valid": True}
