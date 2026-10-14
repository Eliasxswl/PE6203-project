"""One explicit, small model request after the user sets environment variables."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from custom.utils import model_config
from openai import OpenAI

parser = argparse.ArgumentParser()
parser.add_argument('--tool-call', action='store_true', help='Test function calling instead of simple text')
args = parser.parse_args()
client = OpenAI(api_key=model_config.api_key(), base_url=model_config.base_url(), max_retries=0, timeout=60)
request = dict(model=model_config.model_name(), max_tokens=256, temperature=0.2)
if args.tool_call:
    request['messages'] = [{'role':'user','content':'Call add with a=1 and b=2. Do not answer in plain text.'}]
    request['tools'] = [{'type':'function','function':{'name':'add','description':'Add two numbers','parameters':{'type':'object','properties':{'a':{'type':'number'},'b':{'type':'number'}},'required':['a','b']}}}]
else:
    request['messages'] = [{'role':'user','content':'Reply exactly OK.'}]
response = client.chat.completions.create(**request)
print(response.choices[0].message.model_dump_json())
if response.usage:
    print(response.usage.model_dump_json())
if args.tool_call and not response.choices[0].message.tool_calls:
    raise RuntimeError('No tool call returned; verify model support and settings before running the benchmark.')
