from mv2title import validation

# ---- normalize_for_match / is_title_match -----------------------------------


def test_normalize_for_match_nfkc_casefold_whitespace():
	assert validation.normalize_for_match("ＡＢＣ　Ｓｏｎｇ") == "abc song"
	assert validation.normalize_for_match("  A   B  ") == "a b"


def test_is_title_match_substring():
	assert validation.is_title_match("曲名", "アーティスト 曲名 MV") is True


def test_is_title_match_fullwidth_and_case():
	assert validation.is_title_match("ABC", "ｱｰﾃｨｽﾄ ＡＢＣ ｓｏｎｇ") is True


def test_is_title_match_multiple_sources():
	# 元タイトルに直接含まれなくても、前処理後タイトルに含まれていれば一致
	assert validation.is_title_match("A B", "A 【MV】 B", "A B") is True


def test_is_title_match_empty_title_is_false():
	assert validation.is_title_match("", "anything") is False
	assert validation.is_title_match("   ", "anything") is False


def test_is_title_match_mismatch():
	assert validation.is_title_match("xyz", "a song") is False


# ---- check_results ------------------------------------------------------------


def test_check_results_all_valid():
	inp = ["a song", "b song"]
	resp = [
		{"index": 1, "original": "a song", "title": "a"},
		{"index": 2, "original": "b song", "title": "b"},
	]
	ok, validated = validation.check_results(inp, resp)
	assert ok is True
	assert all(r.valid for r in validated)


def test_check_results_matches_by_index_when_shuffled():
	inp = ["a song", "b song", "c song"]
	resp = [
		{"index": 3, "original": "c song", "title": "c"},
		{"index": 1, "original": "a song", "title": "a"},
		{"index": 2, "original": "b song", "title": "b"},
	]
	ok, validated = validation.check_results(inp, resp)
	assert ok is True
	assert all(r.valid for r in validated)
	# 戻り値は入力と同順に並べ直される
	assert [r.index for r in validated] == [1, 2, 3]
	assert [r.title for r in validated] == ["a", "b", "c"]


def test_check_results_length_mismatch_but_per_item_validated():
	inp = ["a song", "b song", "c song"]
	resp = [
		{"index": 1, "original": "a song", "title": "a"},
		{"index": 3, "original": "c song", "title": "c"},
	]
	ok, validated = validation.check_results(inp, resp)
	assert ok is False  # 件数不一致なので全体は False
	assert len(validated) == 3  # 欠けた入力にもプレースホルダが入る
	by_idx = {r.index: r for r in validated}
	assert by_idx[1].valid is True
	assert by_idx[3].valid is True
	assert by_idx[2].valid is False
	assert by_idx[2].title == ""


def test_check_results_substring_mismatch():
	inp = ["a song"]
	resp = [{"index": 1, "original": "totally different", "title": "X"}]
	ok, validated = validation.check_results(inp, resp)
	assert ok is False
	assert validated[0].valid is False


def test_check_results_validates_title_not_original_echo():
	# original が入力と一致していても title が無関係なら invalid。
	# （以前は original 同士の比較だったため常に valid になっていた回帰テスト）
	inp = ["some long video title"]
	resp = [{"index": 1, "original": "some long video title", "title": "unrelated"}]
	ok, validated = validation.check_results(inp, resp)
	assert ok is False
	assert validated[0].valid is False


def test_check_results_normalizes_fullwidth_and_case():
	# NFKC 正規化 + casefold 後に比較される（全角/半角・大文字小文字の差を吸収）
	inp = ["ＳｏｎｇＴｉｔｌｅ Official"]
	resp = [{"index": 1, "title": "songtitle"}]
	ok, validated = validation.check_results(inp, resp)
	assert ok is True
	assert validated[0].valid is True


def test_check_results_empty_title_invalid():
	# 空文字列はあらゆる文字列の部分文字列だが、valid にしてはいけない
	ok, validated = validation.check_results(["a song"], [{"index": 1, "title": ""}])
	assert ok is False
	assert validated[0].valid is False


def test_check_results_duplicate_index_first_wins():
	inp = ["a song"]
	resp = [
		{"index": 1, "title": "a"},
		{"index": 1, "title": "zzz"},
	]
	ok, validated = validation.check_results(inp, resp)
	assert len(validated) == 1
	assert validated[0].title == "a"
	assert validated[0].valid is True
	assert ok is False  # 件数不一致（2 件返ってきている）


def test_check_results_matches_against_cleaned_source():
	# 前処理でノイズ除去した文字列から抽出された title も valid と判定できる
	inp = ["A 【MV】 B"]
	resp = [{"index": 1, "title": "A B"}]
	ok, validated = validation.check_results(inp, resp, cleaned=["A B"])
	assert ok is True
	assert validated[0].valid is True
	# original は前処理後ではなく元のタイトル
	assert validated[0].original == "A 【MV】 B"
