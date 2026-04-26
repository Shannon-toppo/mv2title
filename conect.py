from openai import OpenAI

# グローバル変数
client = None
response = None
_system_prompt = None


def init(
    api_key="hogehoge",
    base_url="http://127.0.0.1:8080/v1/",
    system_prompt="あなたはタイトル分類の専門家です。与えられたMVのタイトルから曲名を抜き出してください。出力はリスト形式([要素1,要素2])で行い、それ以外は出力しないでください。"
    ):
    """
    クライアント初期化

    Args:
        api_key (str): APIキー。ローカルサーバーなら適当で可
        base_url (str): APIのベースURL
        system_prompt (str|None): 初期の system プロンプト（任意）
    """
    global client, _system_prompt
    _system_prompt = system_prompt
    client = OpenAI(
        api_key=api_key,  # ローカルサーバーなので適当なキーでOK
        base_url=base_url
    )


def set_system_prompt(prompt):
    """グローバルな system プロンプトを設定する。"""
    global _system_prompt
    _system_prompt = prompt


def get_system_prompt():
    """現在のグローバル system プロンプトを返す。"""
    return _system_prompt


def send_message(prompt, system_prompt=None):
    """
    メッセージを送信する。

    Args:
        prompt (str): ユーザーメッセージ
        system_prompt (str|None): 呼び出しごとに指定する system プロンプト（省略時はグローバルを使用）
    """
    global response
    sp = system_prompt if system_prompt is not None else _system_prompt
    messages = []
    if sp:
        messages.append({"role": "system", "content": sp})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model="gemma-4-e2b-it",
        messages=messages
    )
    return response