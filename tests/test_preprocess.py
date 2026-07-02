from mv2title import preprocess


def test_clean_title_removes_noise_brackets():
	assert preprocess.clean_title("Artist「曲名」(Official Music Video)") == "Artist「曲名」"
	assert preprocess.clean_title("曲名【MV】") == "曲名"
	assert preprocess.clean_title("Song [OFFICIAL VIDEO]") == "Song"
	assert preprocess.clean_title("曲名（公式）") == "曲名"


def test_clean_title_keeps_informative_brackets():
	# ノイズキーワードを含まない括弧（曲名の一部かもしれない）は残す
	assert preprocess.clean_title("Song (Acoustic)") == "Song (Acoustic)"
	assert preprocess.clean_title("アーティスト『曲名』") == "アーティスト『曲名』"


def test_clean_title_removes_feat():
	assert preprocess.clean_title("Song feat. Someone") == "Song"
	assert preprocess.clean_title("Song (feat. Someone)") == "Song"
	assert preprocess.clean_title("Song ft. A & B") == "Song"


def test_clean_title_trims_leftover_separators():
	assert preprocess.clean_title("曲名 (Official Music Video) - ") == "曲名"


def test_clean_title_falls_back_when_everything_removed():
	# 全部ノイズ扱いになった場合は元のタイトルを返す（空文字列にしない）
	assert preprocess.clean_title("【MV】") == "【MV】"


def test_clean_title_plain_passthrough():
	assert preprocess.clean_title("ただの曲名") == "ただの曲名"
	assert preprocess.clean_title("") == ""
