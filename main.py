import json
import conect


def edit_title(arr):
    sprit_num = 10
    arr_2 = []
    arr_2 = list(map(lambda x:f"{x[0]+1}.{x[1]}",enumerate(arr)))
    # print(arr_2)
    reslte = []
    
    for i in range(0,len(arr_2),sprit_num):
        reslte.append(arr_2[i:i+sprit_num])
    print(arr_2)
    return arr_2

def send(prompt):
    conect.init()
    conect.send_message(" ".join(prompt))
    res = conect.response.choices[0].message.content
    # print("Raw response:", res)
    return res

def list_search(arr, keyword_list):
    result = []
    for item in arr:
        found = False
        for keyword in keyword_list:
            if keyword in item:
                found = True
                break
        result.append(found)
    # print(arr)
    # print(keyword_list)
    # print(result)
    return result

def res_check(input_text, response):
    if not len(input_text) == len(response):
            print("Error: The number of input titles does not match the number of output titles.")
            print(f"Input length: {len(input_text)}, Output length: {len(response)}")
            return False
    else:
        result_list = list_search(input_text, list(response))
        for i in result_list:
            if not i:
                print("Error: One or more input titles were not found in the output.",i)
                return False
            else:
                    return True

def main(text):
    prompt = edit_title(text)
    res = send(prompt)[1:-1]
    res_2 = list(res.split(","))
    # print("res_2 type:", type(res_2))
    # print("res_2:", res_2[0])
    result = res_check(text, res_2)
    if result:
        return res
    else:
        return "Failure: The output titles are not valid or do not match the input titles."


if __name__ == "__main__":
    test_list_2 = ["MIMI - サイエンス (feat.重音テトSV)",
                    "『ソルティメロウ』 / feat. 可不",
                    "『天使の涙』 / feat.初音ミク",
                    "『アンコールダンス』/ feat. 重音テトSV",
                    "『夜と幸せ』/ feat. 詩の出素。",
                    "『桜の戦略 』/ MIMI feat. マス",
                    "『お砂糖哀歌』 / feat. 初音ミク",
                    "『恋しくなったら手を叩こう』/ MIMI feat.花鏡紅璃",
                    "『恋しくなったら手を叩こう』 / feat.重音テトSV",
                    "ヒューマとニズム-Hata",
                    "暴飲暴食P 「うそつきマカロン」feat. 重音テト ",
                    "あんずの花/ すりぃ feat.ねね(Official Music Video)",
                    "ヨルシカ「ただ君に晴れ」Music Video",
                    "[self cover] The Beast. /スペクタルP feat 可不"]

    print(main(test_list_2[0:5]))