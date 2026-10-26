"""Deterministic offline providers; never connect to models or MCP endpoints."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import uuid

from .errors import Cancelled, ExecutionFailure
from .runtime import ALIASES
from .selection import ROOT


class Message:
    def __init__(self, content=None, tool_calls=None):
        self.content, self.tool_calls = content, tool_calls or []

    def model_dump(self, **_):
        result = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = [{"id": call.id, "type": "function",
                                     "function": {"name": call.function.name, "arguments": call.function.arguments}}
                                    for call in self.tool_calls]
        return result


class Response:
    def __init__(self, message):
        self.choices = [SimpleNamespace(message=message, finish_reason="stop")]
        self.usage = SimpleNamespace(model_dump=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

    def model_dump(self, **_):
        return {"choices": [{"message": self.choices[0].message.model_dump()}], "usage": self.usage.model_dump()}


def catalog_for(config, task_list, stage):
    catalog = {}
    for task in task_list:
        for original, names in task["servers"].items():
            server = ALIASES.get(original, original)
            for name in names:
                if stage != "original" and config.get("mock", {}).get("rename_tools", False):
                    name = "renamed_" + name
                catalog[server + "::" + name] = {"server": server, "name": name,
                    "description": f"Offline {stage} tool", "inputSchema": {"type": "object", "properties": {}},
                    "remote_name": "mock:" + server + "::" + name}
    return catalog


class OfflineRuntime:
    def __init__(self, config, stage, servers, cancel=None, task_list=None):
        self.config, self.stage = config, stage
        canonical = {ALIASES.get(s, s) for s in servers}
        self.catalog = {key: tool for key, tool in catalog_for(config, task_list, stage).items()
                        if tool["server"] in canonical}
        self.directory = ROOT / ".runtime/r" / uuid.uuid4().hex[:16]
        self.workspace = self.directory / "workspace"
        self.url = "offline://no-network"
        self.calls = 0

    def __enter__(self):
        self.directory.mkdir(parents=True)
        try:
            shutil.copytree(ROOT / self.config["fixtures"], self.workspace)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def call(self, remote, arguments):
        from mcp.types import CallToolResult, TextContent
        state = self.directory / "state.json"
        if self.calls == 0 and state.exists():
            raise AssertionError("Offline tool state leaked into a new trajectory")
        self.calls += 1
        state.write_text(json.dumps({"calls": self.calls, "arguments": arguments}), encoding="utf-8")
        text = "Unknown tool: " + remote[8:] if remote.startswith("missing:") else "Fresh fixture state. " + "x" * 900
        return CallToolResult(isError=remote.startswith("missing:"), content=[TextContent(type="text", text=text)])

    def __exit__(self, *_):
        # Offline runtimes are disposable; no real services are started.
        if self.directory.exists():
            assert self.directory.resolve().is_relative_to((ROOT / ".runtime/r").resolve())
            shutil.rmtree(self.directory)


class OfflineClient:
    def __init__(self, config, key):
        self.config, self.key, self.calls = config, key, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        from .results import SCORES
        self.calls += 1
        settings = self.config.get("mock", {})
        if self.key in settings.get("worker_crash_on", []):
            import os
            os._exit(23)
        if self.key in settings.get("fail_trajectories", []):
            raise ExecutionFailure("Injected provider failure")
        if self.key in settings.get("interrupt_trajectories", []):
            raise Cancelled()
        if "tools" not in kwargs:
            score = 3 if "Unknown tool:" in kwargs["messages"][0]["content"] else 8
            from .judge_output import REASONS
            return Response(Message(json.dumps({**{s: score for s in SCORES},
                **{s: "Deterministic offline judge" for s in REASONS}})))
        if self.calls == 1 and kwargs["tools"]:
            name = kwargs["tools"][0]["function"]["name"]
            return Response(Message(tool_calls=[SimpleNamespace(id="offline_call_1",
                function=SimpleNamespace(name=name, arguments="{}"))]))
        return Response(Message("[FINISH] Offline completion"))

    def close(self):
        pass


def rewrite_experience(entry, catalog):
    """Explicit offline fixture for evolution tests; never a live fallback."""
    result=deepcopy(entry)
    mapping={}
    for old in result['value']['tool_ids']:
        server,name=old.split('::',1)
        target=old if old in catalog else server+'::renamed_'+name
        if target not in catalog:
            result['adaptation']={'status':'unavailable','reason':'Offline fixture has no corresponding tool'}
            return result
        mapping[old]=target
    value=json.dumps(result['value'])
    for old,new in mapping.items():value=value.replace(old,new)
    result['value']=json.loads(value)
    result['adaptation']={'status':'active','reason':'Explicit deterministic offline contract fixture'}
    return result
