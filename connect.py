from openai import OpenAI
from openai.types.chat import ChatCompletion
from dotenv import load_dotenv
from typing import Any
import os


client: OpenAI | None = None
_system_prompt: str | None = None

load_dotenv()

key: str | None = os.getenv("API_KEY")
url: str | None = os.getenv("BASE_URL")
sys_pmt: str | None = os.getenv("SYSTEM_PROMPT")
model: str = os.getenv("MODEL", "gemma-4-e2b-it")

# ローカル LLM は応答が遅いことがあるため、OpenAI 既定 (600s) より短いが余裕のある値。
DEFAULT_TIMEOUT: float = 120.0
# openai SDK が接続エラー・429・5xx を指数バックオフ付きで再試行する回数。
DEFAULT_MAX_RETRIES: int = 2


def init(
    api_key: str | None = key,
    base_url: str | None = url,
    system_prompt: str | None = sys_pmt,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> None:
    """
    クライアント初期化
    Args:
        api_key (str): APIキー。ローカルサーバーなら適当で可
        base_url (str): APIのベースURL
        system_prompt (str|None): 初期の system プロンプト（任意）
        timeout (float): リクエスト全体のタイムアウト秒数
        max_retries (int): 一時的エラー時の再試行回数（SDK が指数バックオフで処理）
    """
    global client, _system_prompt
    if not base_url:
        # base_url が None/空だと OpenAI() は本番 (api.openai.com) へフォールバックする。
        # 本ライブラリはローカル OpenAI 互換サーバ前提のため、誤送信を防いで明示的に失敗させる。
        raise ValueError(
            "BASE_URL が未設定です。ローカル LLM のエンドポイント"
            "（例: http://127.0.0.1:1234/v1/）を .env の BASE_URL に設定するか、"
            "init(base_url=...) で明示してください。"
        )
    _system_prompt = system_prompt
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
    )


def set_system_prompt(prompt: str | None) -> None:
    """グローバルな system プロンプトを設定する。"""
    global _system_prompt
    _system_prompt = prompt


def get_system_prompt() -> str | None:
    """現在のグローバル system プロンプトを返す。"""
    return _system_prompt


def send_message(
    prompt: str,
    system_prompt: str | None = None,
    model_name: str | None = None,
    temperature: float = 0.0,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
) -> ChatCompletion:
    """
    メッセージを送信する。

    Args:
        prompt (str): ユーザーメッセージ
        system_prompt (str|None): 呼び出しごとに指定する system プロンプト（省略時はグローバルを使用）
        model_name (str|None): 使用するモデル名（省略時はモジュール変数 model = 環境変数 MODEL を使用）
        temperature (float): サンプリング温度。抽出タスクのため既定は 0.0（決定的）
        response_format (dict|None): OpenAI 互換の構造化出力指定（例: json_schema / json_object）。
            省略時は通常のテキスト応答。
        max_tokens (int|None): 応答の最大トークン数。省略時はサーバ既定。
    """
    if client is None:
        raise RuntimeError("connect.init() を先に呼んでください。")
    sp = system_prompt if system_prompt is not None else _system_prompt
    messages: list[dict[str, str]] = []
    if sp:
        messages.append({"role": "system", "content": sp})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, Any] = {
        # 既定引数で束縛せず実行時に解決することで、init 後の connect.model 変更も反映する。
        "model": model_name if model_name is not None else model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    return client.chat.completions.create(**kwargs)
