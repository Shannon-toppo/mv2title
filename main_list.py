"""旧実装（非推奨）。main_json を使用してください。

LLM の出力をプレーンなリスト文字列として受け取るレガシーパスです。
将来のリリースで削除予定のため、バグ修正以外の変更は行いません。
"""

import ast
import warnings

try:
	from . import connect, utils
except ImportError:
	import connect  # type: ignore
	import utils  # type: ignore


def _send_batch_raw(batch: list[str]) -> str | None:
	"""connect モジュールに生のメッセージを送り、raw response を返す（内部用）。"""
	response = connect.send_message(" ".join(batch))
	return response.choices[0].message.content


def send_batches(prompts: list[str], batch_size: int = 10, debug: bool = False) -> list[str]:
	"""prompts (list of str) を batch_size ごとに送信し、すべての応答を平坦なリストとして返す。

	応答が Python リテラルのリスト表現なら ast.literal_eval でパースし、そうでなければカンマ区切りで分割して補正します。
	"""
	all_responses: list[str] = []
	raw: str | None = ""
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
		s = (raw or "").strip()
		if s.startswith("[") and s.endswith("]"):
			s = s[1:-1]
		parts = [p.strip().strip("'\"") for p in s.split(",") if p.strip()]
		all_responses.extend(parts)
	if debug:
		print(f"[DEBUG],send_batches: all_responses: {all_responses}")
		print(f"[DEBUG],send_batches: raw responses: {raw}")
	return all_responses


def res_check(input_text: list[str], response: list[str], debug: bool) -> bool:
	"""input_text（元タイトルリスト）と response（出力タイトルリスト）を位置ごとに比較して妥当性を返す。"""
	if len(input_text) != len(response):
		if debug:
			print("Error: The number of input titles does not match the number of output titles.")
			print(f"Input length: {len(input_text)}, Output length: {len(response)}")
		return False

	# 位置対応で比較: i 番目の入力と i 番目の出力のどちらかが他方を含むこと
	result_list = [(response[i] in input_text[i]) or (input_text[i] in response[i]) for i in range(len(input_text))]
	if all(result_list):
		return True

	for idx, ok in enumerate(result_list):
		if not ok:
			if debug:
				print(f"Error: Input title not found in output at index {idx}: {input_text[idx]} vs {response[idx]}")
	return False


def main(
	text: list[str],
	batch_size: int = 10,
	bypass_check: bool = False,
	debug_mode: bool = False,
) -> list[str]:
	"""text: list of original titles. 戻り値: 応答タイトルのリスト。検証失敗時は ValueError を送出する。

	.. deprecated:: 0.1.0
		main_json.main() を使用してください。このモジュールは将来のリリースで削除されます。
	"""
	warnings.warn(
		"main_list.main() は非推奨です。main_json.main() を使用してください（将来のリリースで削除予定）。",
		DeprecationWarning,
		stacklevel=2,
	)
	prompts = utils.edit_title(text)
	responses = send_batches(prompts, batch_size=batch_size, debug=debug_mode)
	if bypass_check:
		return responses
	if res_check(text, responses, debug_mode):
		return responses
	if debug_mode:
		print("Failure: The output titles are not valid or do not match the input titles.")
	raise ValueError("Output does not match input titles.")


if __name__ == "__main__":
	import os

	# デモ用の入力はリポジトリ管理外の test.txt（1 行 1 タイトル）から読み込む。
	_test_file = os.path.join(os.path.dirname(__file__), "test.txt")
	test_list_2 = utils.read_titles(_test_file)

	connect.init()
	print(main(test_list_2, batch_size=10, bypass_check=False, debug_mode=False))
