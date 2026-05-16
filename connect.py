from openai import OpenAI
from dotenv import load_dotenv
import os


client = None
_system_prompt = None

load_dotenv()

key = os.getenv("API_KEY")
url = os.getenv("BASE_URL")
sys_pmt = os.getenv("SYSTEM_PROMPT")


def init(api_key=key, base_url=url, system_prompt=sys_pmt):
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
        api_key=api_key,
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
    if client is None:
        raise RuntimeError("connect.init() を先に呼んでください。")
    sp = system_prompt if system_prompt is not None else _system_prompt
    messages = []
    if sp:
        messages.append({"role": "system", "content": sp})
    messages.append({"role": "user", "content": prompt})

    return client.chat.completions.create(
        model="gemma-4-e2b-it",
        messages=messages
    )
