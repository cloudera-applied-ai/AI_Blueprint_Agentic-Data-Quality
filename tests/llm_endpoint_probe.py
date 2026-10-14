
from openai import OpenAI
import json


# If running from workbench use /tmp/jwt. Otherwise provide your CDP_TOKEN
API_KEY = json.load(open("/tmp/jwt"))["access_token"]

MODEL_ID = "meta/llama-3.2-3b-instruct"

client = OpenAI(
	base_url="https://ml-64288d82-5dd.go01-dem.ylcu-atmi.cloudera.site/namespaces/serving-default/endpoints/demo---data-quality---gainwell/v1",
	api_key=API_KEY,
)

completion = client.chat.completions.create(
	model=MODEL_ID,
	messages=[{"role": "user", "content": "Write a one-sentence definition of GenAI."}],
	temperature=0.2,
	top_p=0.7,
	max_tokens=1024,
	stream=True
)

for chunk in completion:
	if chunk.choices[0].delta.content is not None:
		print(chunk.choices[0].delta.content, end="")