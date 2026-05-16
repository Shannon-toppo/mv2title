import ast

try:
    from . import connect
    from . import utils
except ImportError:
    import connect  # type: ignore
    import utils    # type: ignore


def _send_batch_raw(batch):
    """connect モジュールに生のメッセージを送り、raw response を返す（内部用）。"""
    response = connect.send_message(" ".join(batch))
    return response.choices[0].message.content


def send_batches(prompts, batch_size=10, debug=False):
    """prompts (list of str) を batch_size ごとに送信し、すべての応答を平坦なリストとして返す。

    応答が Python リテラルのリスト表現なら ast.literal_eval でパースし、そうでなければカンマ区切りで分割して補正します。
    """
    all_responses = []
    raw = ""
    for batch in utils.chunk_list(prompts, batch_size):
        raw = _send_batch_raw(batch)
        parsed = None
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                all_responses.extend(parsed)
                continue
        except Exception:
            parsed = None

        # フォールバック: 角括弧を削ってカンマで分割
        s = raw.strip()
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1]
        parts = [p.strip().strip("'\"") for p in s.split(",") if p.strip()]
        all_responses.extend(parts)
    if debug:
        print(f"[DEBUG],send_batches: all_responses: {all_responses}")
        print(f"[DEBUG],send_batches: raw responses: {raw}")
    return all_responses


def list_search(arr, keyword_list):
    result = []
    for item in arr:
        found = False
        for keyword in keyword_list:
            if keyword in item:
                found = True
                break
        result.append(found)
    return result


def res_check(input_text, response, debug):
    """input_text（元タイトルリスト）と response（出力タイトルリスト）を比較して妥当性を返す。"""
    if len(input_text) != len(response):
        if debug:
            print("Error: The number of input titles does not match the number of output titles.")
            print(f"Input length: {len(input_text)}, Output length: {len(response)}")
        return False

    result_list = list_search(input_text, response)
    if all(result_list):
        return True

    for idx, ok in enumerate(result_list):
        if not ok:
            if debug:
                print(f"Error: Input title not found in output at index {idx}: {input_text[idx]}")
    return False


def main(text, batch_size=10, bypass_check=False, debug_mode=False):
    """text: list of original titles. 戻り値: 応答タイトルのリストまたは失敗メッセージ文字列。"""
    connect.init()
    prompts = utils.edit_title(text)
    responses = send_batches(prompts, batch_size=batch_size, debug=debug_mode)
    if bypass_check:
        return responses
    result = res_check(text, responses, debug_mode)
    if result:
        return responses
    else:
        if debug_mode:
            print("Failure: The output titles are not valid or do not match the input titles.")
        return "Error"


if __name__ == "__main__":
    test_list_2 = [
        "暴飲暴食P 「うそつきマカロン」feat. 重音テト ",
        "あんずの花/ すりぃ feat.ねね(Official Music Video)",
        "【初音ミク】幸福でも不幸でもない平凡で幸福な日々と幸福でも不幸でもある非凡で不幸な日々【オリジナル曲】by HaTa",
        "ヨルシカ「ただ君に晴れ」Music Video",
        "[self cover] The Beast. /スペクタルP feat 可不",
        "MIMI - サイエンス (feat.重音テトSV)",
        "『ソルティメロウ』 / feat. 可不",
        "『天使の涙』 / feat.初音ミク",
        "『アンコールダンス』/ feat. 重音テトSV",
        "『夜と幸せ』/ feat. 詩の出素。",
        "『桜の戦略 』/ MIMI feat. マス",
        "『お砂糖哀歌』 / feat. 初音ミク",
        "『恋しくなったら手を叩こう』/ MIMI feat.花鏡紅璃",
        "『恋しくなったら手を叩こう』 / feat.重音テトSV",
        "「ヒューマとニズム」-Hata"
    ]

    print(main(test_list_2, batch_size=10, bypass_check=False, debug_mode=False))
