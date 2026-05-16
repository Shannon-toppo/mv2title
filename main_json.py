"""
構造化出力 (JSON) を用いてタイトル変換を行うモジュール
main_list.py を参考にしつつ、LLM の出力を JSON 配列として受け取り処理します。
"""
import json
import ast

try:
	from . import connect
	from . import utils
except ImportError:
	import connect  # type: ignore
	import utils    # type: ignore


def _make_json_prompt(batch):
	items = "\n".join(batch)
	p = (
		"以下は番号付きのタイトル一覧です。\n"
		"各入力に対して、次の形式のJSON配列を返してください。"
		"配列の各要素はオブジェクトで、少なくともキー `index` (整数)、`original` (元の文字列)、`title` (変換後タイトル) を持ってください。\n"
		"出力は純粋な JSON の配列のみとし、余分な説明文は含めないでください。\n\n"
		"入力:\n"
		f"{items}\n"
	)
	return p


def _send_batch_raw(batch):
	response = connect.send_message(_make_json_prompt(batch))
	return response.choices[0].message.content


def _extract_json_substring(s):
	start = s.find("[")
	end = s.rfind("]")
	if start != -1 and end != -1 and end > start:
		return s[start:end+1]
	return None


def _parse_json_response(raw, debug=False):
	if raw is None:
		return None
	s = raw.strip()
	try:
		data = json.loads(s)
		return data
	except Exception:
		sub = _extract_json_substring(s)
		if sub:
			try:
				data = json.loads(sub)
				return data
			except Exception:
				if debug:
					print("[DEBUG] JSON parsing failed even after extracting substring")
		# フォールバック: Python リテラル風やカンマ区切りの文字列リストを処理
		try:
			parsed = ast.literal_eval(s)
			return parsed
		except Exception:
			# 最後の手段: カンマで分割して文字列リストにする
			if s.startswith("[") and s.endswith("]"):
				s_inner = s[1:-1]
			else:
				s_inner = s
			parts = [p.strip().strip('\"\'') for p in s_inner.split(",") if p.strip()]
			return parts


def send_batches_json(prompts, batch_size=10, debug=False):
	all_objs = []
	for batch in utils.chunk_list(prompts, batch_size):
		raw = _send_batch_raw(batch)
		parsed = _parse_json_response(raw, debug=debug)

		if parsed is None:
			continue

		# parsed がリストか辞書か文字列リストかを判定して正規化
		if isinstance(parsed, dict):
			items = [parsed]
		else:
			items = list(parsed)

		normalized = []
		for idx, item in enumerate(items):
			if isinstance(item, dict):
				obj = item.copy()
				if "index" not in obj:
					obj["index"] = idx + 1
				if "original" not in obj:
					# try to recover from batch using index
					obj["original"] = batch[obj["index"] - 1] if 0 <= obj["index"] - 1 < len(batch) else ""
				if "title" not in obj:
					# try other possible keys
					for k in ("new_title", "name", "video_title"):
						if k in obj:
							obj["title"] = obj[k]
							break
					else:
						obj["title"] = ""
				normalized.append(obj)
			else:
				# 文字列の場合は batch の対応する元タイトルと組にする
				orig = batch[idx] if idx < len(batch) else ""
				normalized.append({"index": idx + 1, "original": orig, "title": str(item)})

		all_objs.extend(normalized)
		if debug:
			print(f"[DEBUG] raw: {raw}")
			print(f"[DEBUG] parsed items: {normalized}")

	return all_objs


def res_check_json(input_text, response, debug=False):
	if len(input_text) != len(response):
		if debug:
			print("Error: The number of input titles does not match the number of output items.")
			print(f"Input length: {len(input_text)}, Output length: {len(response)}")
		return False

	ok_list = []
	for i, obj in enumerate(response):
		orig = obj.get("original", "")
		# 比較: 少なくとも一方が他方を含む形で一致していることを期待する
		if input_text[i] in orig or orig in input_text[i]:
			ok_list.append(True)
		else:
			ok_list.append(False)

	if all(ok_list):
		return True

	for idx, ok in enumerate(ok_list):
		if not ok and debug:
			print(f"Error: Input title not found in output at index {idx}: {input_text[idx]} vs {response[idx].get('original')}")
	return False


def main(text, batch_size=10, bypass_check=False, debug_mode=False):
	connect.init()
	prompts = utils.edit_title(text)
	responses = send_batches_json(prompts, batch_size=batch_size, debug=debug_mode)
	if bypass_check:
		return responses
	result = res_check_json(text, responses, debug_mode)
	if result:
		return responses
	else:
		if debug_mode:
			print("Failure: The output items are not valid or do not match the input titles.")
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
		"「ヒューマとニズム」-Hata",
		"月詠み『花と散る』Music Video"
	]

	out = main(test_list_2, batch_size=10, bypass_check=False, debug_mode=False)
	print(json.dumps(out, ensure_ascii=False, indent=2))
