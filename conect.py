from openai import OpenAI
def init():
    global client
    client = OpenAI(
        api_key="hogehoge", # ローカルサーバーなので適当なキーでOK
        base_url="http://127.0.0.1:1234/v1/"
    )

def send_message(prompt):
    global response
    response = client.chat.completions.create(
        model="gemma-4-e2b-it",
        messages=[{"role": "user", "content": prompt}]
    )

# init()
# print(send_message("Hello, world!"))
# print(response.choices[0].message.content)