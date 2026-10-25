"""Minimal official agent-loop adapter. MCP, isolation and research strategies stay external."""
from copy import deepcopy
from importlib.metadata import version
import json
import threading
import time
from types import SimpleNamespace

from custom.agents.SimpleOpenAIAgent import SINGLE_SERVER_INTERATION_SYSTEM_PROMPT
from custom.agents.tool_results import raw_result, visible_result
from custom.experiment.errors import ExecutionFailure
from custom.experiment.results import safe_error
from custom.utils import model_config
from custom.utils.test_utils import offset_date


class ChatModel:
    """Keep the experiment contract while delegating the entire loop to create_agent."""
    def __init__(self, model_name, client, tools, max_round=15, tool_caller=None,
                 event_callback=None, workspace_root=None, file_exists='', prompt_time=None,
                 temperature=0.2, max_new_tokens=4096, thinking=None, **unused):
        self.client, self.tool_caller = client, tool_caller
        self.model_name, self.max_round = model_name, max_round
        self.event_callback = event_callback or (lambda *args: None)
        self.request_count, self.elapsed_seconds = 0, 0.0
        self.raw_tool_trace, self.model_usage = [], []
        self.execution_error, self.stop_reason, self.last_finish_reason = None, None, None
        self.dependency_versions = {n: version(n) for n in ('langchain', 'langchain-openai', 'langgraph')}
        self.system_prompt = SINGLE_SERVER_INTERATION_SYSTEM_PROMPT.format(
            SET_TIME=prompt_time or str(offset_date(0)),
            WORKSPACE_ROOT=(workspace_root or model_config.workspace_dir()).as_posix(), FILE_EXISTS=file_exists)
        self.messages = [{'role': 'system', 'content': self.system_prompt}]
        self.recovery = None
        self.tool_definitions = deepcopy(tools)
        self.temperature, self.max_new_tokens, self.thinking = temperature, max_new_tokens, thinking

    @property
    def with_raw_response(self):
        def create(**kwargs):
            response = self.create(**kwargs)
            return SimpleNamespace(parse=lambda: response.model_dump(mode='json'))
        return SimpleNamespace(create=create)

    def create(self, **kwargs):
        # The official middleware enforces the cap; this boundary also protects
        # every actual provider dispatch, including unforeseen framework paths.
        if self.request_count >= self.max_round:
            raise RuntimeError('Official agent exceeded its fixed provider request budget')
        self.messages = deepcopy(kwargs['messages'])
        self.event_callback('model_start', {'round': self.request_count, 'messages': self.messages})
        self.request_count += 1
        try:
            response = self.client.chat.completions.create(**kwargs)
            if response.usage:
                self.model_usage.append(response.usage.model_dump())
            self.last_finish_reason = response.choices[0].finish_reason
            self.event_callback('model_completed', response.model_dump(mode='json'))
            return response
        except Exception as exc:
            self.event_callback('model_failed', safe_error(exc))
            raise

    def run_with_server(self, query, fschat_flag=False):
        from langchain.agents import create_agent
        from langchain.agents.middleware import ModelCallLimitMiddleware, before_model, wrap_model_call, wrap_tool_call
        from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
        from langchain_core.messages import SystemMessage, ToolMessage, convert_to_openai_messages
        from langchain_core.tools import StructuredTool
        from langchain_openai import ChatOpenAI

        started = time.perf_counter()
        definitions = {t['name']: t for t in self.tool_definitions}
        lock = threading.RLock()

        @before_model
        def snapshot(state, runtime):
            self.messages = convert_to_openai_messages(state['messages'])

        @wrap_model_call
        def repair_reference(request, handler):
            context = self.recovery.take() if self.recovery is not None else ''
            if context:
                base = request.system_message.content if request.system_message is not None else self.system_prompt
                request = request.override(system_message=SystemMessage(content=base + context))
            return handler(request)

        @wrap_tool_call
        def mcp_transport(request, handler):
            # Serial tools within one trajectory; independent trajectories can run in parallel.
            with lock:
                call = request.tool_call
                self.messages = convert_to_openai_messages(request.state['messages'])
                args = json.dumps(call['args'], ensure_ascii=False)
                self.event_callback('tool_start', {'messages': deepcopy(self.messages),
                    'tool_call_id': call['id'], 'name': call['name'], 'arguments': args})
                definition = definitions.get(call['name'])
                meta = (definition or {}).get('meta', {})
                protocol_error = None
                try:
                    if definition is None:
                        response = {'isError': True, 'content': [{'type': 'text',
                            'text': 'Unknown exposed tool: ' + call['name']}]}
                    else:
                        response = raw_result(self.tool_caller(meta['benchmark_remote_name'], call['args']))
                except ExecutionFailure as exc:
                    self.event_callback('tool_failed', safe_error(exc))
                    raise
                except Exception as exc:
                    protocol_error = getattr(exc, 'raw_response', None)
                    response = {'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]}
                self.raw_tool_trace.append({'tool_call_id': call['id'], 'name': call['name'],
                    'semantic_identity': meta.get('benchmark_semantic_identity'), 'arguments': args,
                    'response': response, 'protocol_error': protocol_error})
                if self.recovery is not None:
                    self.recovery.observe(self.raw_tool_trace[-1])
                content = visible_result(response)
                self.messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': content})
                self.event_callback('tool_completed', {'messages': deepcopy(self.messages),
                                                      'raw_tool_trace': deepcopy(self.raw_tool_trace)})
                return ToolMessage(content=content, tool_call_id=call['id'], name=call['name'],
                                   status='error' if response.get('isError') else 'success')

        def transport_only(**kwargs):
            raise RuntimeError('MCP tools must dispatch through the observed transport middleware')

        tools = [StructuredTool(name=t['name'], description=t['description'],
                                args_schema=t['inputSchema'], func=transport_only) for t in self.tool_definitions]
        model = ChatOpenAI(model=self.model_name, client=self, use_responses_api=False,
            api_key=getattr(self.client, 'api_key', 'unused-client-credential'),
            base_url=str(getattr(self.client, 'base_url', model_config.base_url())),
            max_retries=0, temperature=self.temperature, max_tokens=self.max_new_tokens,
            extra_body={'thinking': {'type': self.thinking}} if self.thinking else None)
        self.system_prompt = self.messages[0]['content']
        agent = create_agent(model=model, tools=tools,
            system_prompt=self.system_prompt,
            middleware=[snapshot, ModelCallLimitMiddleware(run_limit=self.max_round, exit_behavior='error'), repair_reference, mcp_transport])
        answer = ''
        exceeded = False
        try:
            result = agent.invoke({'messages': [{'role': 'user', 'content': query}]},
                                  config={'max_concurrency': 1, 'recursion_limit': self.max_round * 10 + 20})
            self.messages = convert_to_openai_messages(result['messages'])
            if self.messages and self.messages[-1]['role'] == 'assistant':
                answer = self.messages[-1].get('content') or ''
            self.stop_reason = 'model_length_limit' if self.last_finish_reason == 'length' else 'final_response'
        except ModelCallLimitExceededError:
            exceeded = True
            self.stop_reason = 'model_request_limit'
        except Exception as exc:
            self.execution_error = safe_error(exc)
            self.stop_reason = 'execution_error'
        finally:
            self.elapsed_seconds = time.perf_counter() - started
        # Match the benchmark trajectory convention: system prompt, user, then execution.
        if not self.messages or self.messages[0].get('role') != 'system':
            self.messages.insert(0, {'role': 'system', 'content': self.system_prompt})
        return answer, self.messages, bool(answer), exceeded
