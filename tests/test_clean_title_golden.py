"""clean_title のゴールデン(特性)テスト。

実在の音楽動画タイトルに近い入力に対する **現時点の挙動** をそのまま固定する。
リファクタリング(docs/refactoring-plan.md)中の意図しない挙動変化を検知するのが目的で、
ここでの期待値は「理想の出力」ではない。挙動を意図的に変える場合は、
そのコミットで期待値も一緒に更新すること。

既知の歪みも現状仕様として固定している(改善はフェーズ3以降の別判断):
- 括弧に入っていないノイズ("... Official Music Video" 等)は除去されない
- feat. 句の除去で直後の区切りに詰まりが出ることがある("Creepy Nuts- ...")
- 括弧外の定型句の一部だけ末尾区切り記号として剥がれることがある("-MUSiC CLiP-" → "-MUSiC CLiP")
"""

import pytest

from mv2title import utils

GOLDEN_CASES = [
	# --- 日本語圏の典型パターン ---
	# 「」は保持・括弧外の Official Music Video は現状除去されない
	("YOASOBI「アイドル」 Official Music Video", "YOASOBI「アイドル」 Official Music Video"),
	("米津玄師 - Lemon", "米津玄師 - Lemon"),
	("Official髭男dism - Pretender[Official Video]", "Official髭男dism - Pretender"),
	("あいみょん - マリーゴールド【OFFICIAL MUSIC VIDEO】", "あいみょん - マリーゴールド"),
	("ヨルシカ - 花に亡霊(OFFICIAL VIDEO)", "ヨルシカ - 花に亡霊"),
	("King Gnu - 白日", "King Gnu - 白日"),
	("Vaundy - 怪獣の花唄【Music Video】", "Vaundy - 怪獣の花唄"),
	("Mrs. GREEN APPLE「ケセラセラ」Official Music Video", "Mrs. GREEN APPLE「ケセラセラ」Official Music Video"),
	# ノイズキーワードが括弧の外にある場合は現状そのまま残る
	(
		"藤井 風(Fujii Kaze) - 死ぬのがいいわ(Shinunoga E-Wa)Official Video",
		"藤井 風(Fujii Kaze) - 死ぬのがいいわ(Shinunoga E-Wa)Official Video",
	),
	# 括弧外の定型句は残るが、末尾のハイフンだけ区切り記号として剥がれる
	("LiSA 『炎』 -MUSiC CLiP-", "LiSA 『炎』 -MUSiC CLiP"),
	("Eve - 廻廻奇譚 MV", "Eve - 廻廻奇譚 MV"),
	("Ado【唱】歌詞付き", "Ado【唱】歌詞付き"),
	(
		"ずっと真夜中でいいのに。『秒針を噛む』(ZUTOMAYO - Kanju)",
		"ずっと真夜中でいいのに。『秒針を噛む』(ZUTOMAYO - Kanju)",
	),
	("【MV】新時代 (ウタ from ONE PIECE FILM RED)", "新時代 (ウタ from ONE PIECE FILM RED)"),
	("back number - 水平線 (フルver)", "back number - 水平線"),
	# "～ ver." 単独はノイズ扱いしない(フルver/short ver のみ対象)
	("スピッツ / 楓（すみか ver.）", "スピッツ / 楓（すみか ver.）"),
	("RADWIMPS - 前前前世 [Official Music Video]", "RADWIMPS - 前前前世"),
	("Kenshi Yonezu - KICK BACK（Chainsaw Man）", "Kenshi Yonezu - KICK BACK（Chainsaw Man）"),
	("優里『ドライフラワー』Official Music Video", "優里『ドライフラワー』Official Music Video"),
	# 「」入りの括弧グループは最内扱いされるが、ノイズキーワードが無いので残る
	(
		"Aimer「残響散歌」MUSIC VIDEO(TVアニメ「鬼滅の刃」遊郭編オープニングテーマ)",
		"Aimer「残響散歌」MUSIC VIDEO(TVアニメ「鬼滅の刃」遊郭編オープニングテーマ)",
	),
	# --- feat. / ft. 句 ---
	("夜に駆ける feat. 誰か", "夜に駆ける"),
	# feat 句の除去で後続区切りとの間のスペースが失われる(現状の歪み)
	("Creepy Nuts feat. Ayase - モーニングルーティン", "Creepy Nuts- モーニングルーティン"),
	("Song (feat. Someone & Other)", "Song"),
	("MONKEY MAJIK - ウマーベラス feat. サンドウィッチマン【Official Music Video】", "MONKEY MAJIK - ウマーベラス"),
	# --- 英語圏の典型パターン ---
	("Queen - Bohemian Rhapsody (Official Video Remastered)", "Queen - Bohemian Rhapsody"),
	("The Weeknd - Blinding Lights (Official Music Video)", "The Weeknd - Blinding Lights"),
	("Ed Sheeran - Shape of You (Official Music Video)", "Ed Sheeran - Shape of You"),
	("ROSÉ & Bruno Mars - APT. (Official Music Video)", "ROSÉ & Bruno Mars - APT."),
	("Adele - Hello (Lyric Video)", "Adele - Hello"),
	("Coldplay - Viva La Vida (Official Audio) [HD]", "Coldplay - Viva La Vida"),
	# --- 保持されるべき括弧・エッジケース ---
	("Song (Acoustic)", "Song (Acoustic)"),
	("アーティスト『曲名』", "アーティスト『曲名』"),
	("Perfume 「ポリリズム」", "Perfume 「ポリリズム」"),
	("10-FEET - 第ゼロ感", "10-FEET - 第ゼロ感"),
]


@pytest.mark.parametrize(("title", "expected"), GOLDEN_CASES, ids=[t for t, _ in GOLDEN_CASES])
def test_clean_title_golden(title: str, expected: str):
	assert utils.clean_title(title) == expected
