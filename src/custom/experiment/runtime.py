"""Private fixture copies and owned MCP services; unknown backends fail closed."""
import asyncio
from contextlib import contextmanager
from datetime import timedelta
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
import uuid

from .errors import ExecutionFailure, ToolMistake
from .selection import ROOT, digest, read_json, tree_hash

ALIASES = {"server-sequential-thinking": "@modelcontextprotocol/server-sequential-thinking",
           "mcp-server-time": "@guanxiong/mcp-server-time", "server-memory": "@guanxiong/server-memory",
           "pollinations/model-context-protocol": "@pollinations/model-context-protocol"}
BUILTIN_POLICIES = {
    "@modelcontextprotocol/server-filesystem": "filesystem",
    "@kazuph/mcp-taskmanager": "taskmanager",
    "@modelcontextprotocol/server-sequential-thinking": "process_local",
    "@guanxiong/mcp-server-time": "process_local",
}


def process_identity(pid):
    if os.name == "nt":
        return None  # Windows Job Objects provide lifetime ownership instead.
    try:
        start = subprocess.check_output(["ps", "-p", str(pid), "-o", "lstart="], text=True).strip()
        command = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True).strip()
        return {"start": start, "command": digest(command)} if start and command else None
    except subprocess.CalledProcessError:
        return None


def reap_orphans(events, episode=None):
    """Only reclaim registered POSIX groups whose process identity still matches."""
    if os.name == "nt":
        return
    owned = {}
    for event in events:
        if episode and event.get("episode") != episode:
            continue
        if event.get("kind") == "runtime_started":
            owned[event["runtime_id"]] = event
        elif event.get("kind") == "runtime_stopped":
            owned.pop(event["runtime_id"], None)
    for event in owned.values():
        pid = event["pid"]
        if event.get("process_identity") and process_identity(pid) == event["process_identity"]:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


class OwnedJob:
    """Windows kill-on-close Job Object owns descendants even after worker death."""
    def __init__(self):
        self.handle = None
        if os.name != "nt":
            return
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [("process_time", c.c_longlong), ("job_time", c.c_longlong), ("flags", w.DWORD),
                        ("minimum", c.c_size_t), ("maximum", c.c_size_t), ("active", w.DWORD),
                        ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
        class Extended(c.Structure):
            _fields_ = [("basic", Basic), ("io", c.c_ulonglong * 6), ("process_memory", c.c_size_t),
                        ("job_memory", c.c_size_t), ("peak_process", c.c_size_t), ("peak_job", c.c_size_t)]
        self.kernel = c.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = w.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        self.kernel.SetInformationJobObject.restype = w.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = w.BOOL
        self.kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel.OpenProcess.restype = w.HANDLE
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.CloseHandle.restype = w.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits)):
            self.close()
            raise ExecutionFailure("Unable to establish Windows process ownership")

    def assign(self, pid):
        if self.handle is None:
            return
        handle = self.kernel.OpenProcess(0x0100 | 0x0001, False, pid)
        try:
            if not handle or not self.kernel.AssignProcessToJobObject(self.handle, handle):
                raise ExecutionFailure("Unable to assign owned process tree")
        finally:
            if handle:
                self.kernel.CloseHandle(handle)

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def policy_for(server, config):
    server = ALIASES.get(server, server)
    if server in BUILTIN_POLICIES:
        return {"kind": BUILTIN_POLICIES[server]}
    policy = config["runtime"].get("policies", {}).get(server)
    if not isinstance(policy, dict) or not policy.get("reviewed") or not policy.get("reason"):
        raise ExecutionFailure(f"Backend state isolation has not been reviewed: {server}")
    if policy.get("kind") not in ("stateless", "process_local", "workspace"):
        raise ExecutionFailure(f"Unsupported reset policy: {server}")
    return policy


def prepare_config(config, stage, servers, directory):
    base = read_json(ROOT / config["runtime"]["configs"][stage])["mcpServers"]
    workspace = directory / "workspace"
    fixtures = ROOT / config["fixtures"]
    shutil.copytree(fixtures, workspace)
    if tree_hash(fixtures) != tree_hash(workspace):
        raise ExecutionFailure("Fixture copy verification failed")
    home = directory / "home"
    home.mkdir()
    temp = directory / "tmp"
    temp.mkdir()
    prepared = {}
    for original in servers:
        server = ALIASES.get(original, original)
        policy = policy_for(server, config)
        if server not in base:
            raise ExecutionFailure(f"Missing server configuration: {server}")
        entry = json.loads(json.dumps(base[server]))
        command = Path(entry["command"]).name.lower()
        args = entry.get("args", [])
        if command in ("npx", "npx.cmd", "npm", "npm.cmd", "uvx", "uvx.exe"):
            raise ExecutionFailure(f"Server uses an unverified downloading launcher: {server}")
        if policy["kind"] == "filesystem":
            # Keep the frozen executable; replace only its allowed workspace argument.
            if not args or not Path(args[0]).is_file():
                raise ExecutionFailure(f"Missing frozen filesystem executable: {server}")
            entry["args"] = [args[0], workspace.as_posix()]
        elif command in ("node", "node.exe") and (not args or not Path(args[0]).is_file()):
            raise ExecutionFailure(f"Missing frozen executable: {server}")
        if os.name == "nt" and command in ("node", "node.exe"):
            entry["args"] = ["--import", (ROOT / "src/custom/experiment/windows-loader.mjs").as_uri(),
                             *entry["args"]]
        entry["cwd"] = workspace.as_posix()
        environment = entry.setdefault("env", {})
        environment.update(HOME=home.as_posix(), USERPROFILE=home.as_posix(),
                           XDG_CONFIG_HOME=(home / ".config").as_posix(),
                           XDG_DATA_HOME=(home / ".local/share").as_posix(),
                           TMPDIR=temp.as_posix(), TMP=temp.as_posix(), TEMP=temp.as_posix())
        if policy["kind"] == "taskmanager":
            environment["TASK_MANAGER_FILE_PATH"] = (workspace / "tasks.json").as_posix()
        for variable, relative in policy.get("env_paths", {}).items():
            target = (directory / relative).resolve()
            if not target.is_relative_to(directory.resolve()):
                raise ExecutionFailure("State path escapes the private runtime")
            target.parent.mkdir(parents=True, exist_ok=True)
            environment[variable] = target.as_posix()
        prepared[server] = entry
    path = directory / "mcp.json"
    path.write_text(json.dumps({"mcpServers": prepared}, indent=2), encoding="utf-8")
    return path, workspace


class LiveRuntime:
    def __init__(self, config, stage, servers, cancel=None, owner_callback=None):
        self.config, self.stage, self.servers, self.cancel = config, stage, list(servers), cancel
        # Short paths preserve long official fixture names on Windows.
        self.directory = ROOT / ".runtime/r" / uuid.uuid4().hex[:16]
        self.proc = None
        self.job = None
        self.log = None
        self.catalog = {}
        self.owner_callback = owner_callback or (lambda event: None)
        self.registered = False

    def __enter__(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=False)
            config_path, self.workspace = prepare_config(self.config, self.stage, self.servers, self.directory)
            node = shutil.which("node")
            executable = ROOT / ".runtime/node_modules/@1mcp/agent/build/index.js"
            if not node or not executable.is_file():
                raise ExecutionFailure("Prepared Node/1mcp installation is missing")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            self.url = f"http://127.0.0.1:{port}/mcp"
            command = [node, str(executable), "serve", "--host", "127.0.0.1", "--port", str(port),
                       "--config", str(config_path), "--config-dir", str(config_path.parent)]
            self.log = (self.directory / "service.log").open("wb")
            self.job = OwnedJob()
            self.proc = subprocess.Popen(command, cwd=self.directory, stdout=self.log, stderr=subprocess.STDOUT,
                                         env={k: v for k, v in os.environ.items() if not any(
                                             token in k.upper() for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD"))},
                                         start_new_session=os.name != "nt",
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.job.assign(self.proc.pid)
            self.owner_callback({"kind": "runtime_started", "runtime_id": self.directory.name,
                                 "pid": self.proc.pid, "process_identity": process_identity(self.proc.pid)})
            self.registered = True
            deadline = time.monotonic() + self.config["runtime"]["startup_timeout"]
            last_error = None
            while time.monotonic() < deadline:
                if self.cancel and self.cancel.is_set():
                    from .errors import Cancelled
                    raise Cancelled()
                if self.proc.poll() is not None:
                    raise ExecutionFailure(f"Owned MCP service exited with code {self.proc.returncode}")
                try:
                    self.catalog = asyncio.run(asyncio.wait_for(self._catalog(), min(3, max(.1, deadline - time.monotonic()))))
                    if all(any(tool["server"] == ALIASES.get(server, server) for tool in self.catalog.values())
                           for server in self.servers):
                        return self
                    last_error = ExecutionFailure("MCP catalog is incomplete")
                except Exception as exc:
                    last_error = exc
                time.sleep(.1)
            raise ExecutionFailure(f"MCP startup timeout ({type(last_error).__name__})")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    async def _session_request(self, function):
        import mcp
        from mcp.client.streamable_http import streamablehttp_client
        settings = self.config["runtime"]
        async with streamablehttp_client(self.url, timeout=settings["connect_timeout"],
                                        sse_read_timeout=settings["read_timeout"]) as (read, write, _):
            async with mcp.ClientSession(read, write, read_timeout_seconds=timedelta(seconds=settings["tool_timeout"])) as session:
                await session.initialize()
                return await function(session)

    async def _catalog(self):
        from custom.utils.mcp_utils import normalize_1mcp_tools
        result = await self._session_request(lambda session: session.list_tools())
        normalize_1mcp_tools(result)
        catalog = {}
        for tool in result.tools:
            for original in self.servers:
                server = ALIASES.get(original, original)
                prefix = server + "_1mcp_"
                if tool.name.startswith(prefix):
                    name = tool.name[len(prefix):]
                    catalog[server + "::" + name] = {
                        "server": server, "name": name, "description": tool.description or "",
                        "inputSchema": tool.inputSchema, "remote_name": (tool.meta or {}).get("benchmark_remote_name", tool.name)}
                    catalog[server + "::" + name]["outputSchema"] = tool.outputSchema
        return catalog

    def call(self, remote_name, arguments):
        from mcp.shared.exceptions import McpError
        if not isinstance(arguments, dict):
            raise ToolMistake("Tool arguments must be a JSON object")
        if remote_name.startswith("missing:"):
            from mcp.types import CallToolResult, TextContent
            return CallToolResult(isError=True, content=[TextContent(type="text", text="Unknown tool: " + remote_name[8:])])
        try:
            return asyncio.run(asyncio.wait_for(
                self._session_request(lambda session: session.call_tool(remote_name, arguments)),
                self.config["runtime"]["tool_timeout"]))
        except McpError as exc:
            if exc.error.code == -32602:
                raise ToolMistake(exc.error.message, exc.error.model_dump(mode="json")) from exc
            raise ExecutionFailure(f"MCP protocol failed (code {exc.error.code})") from exc
        except Exception as exc:
            raise ExecutionFailure(f"MCP transport failed ({type(exc).__name__})",
                                   unknown_outcome=getattr(exc, "response", None) is None) from exc

    def __exit__(self, *_):
        if self.proc:
            if os.name == "nt":
                if self.job:
                    self.job.close()
            else:
                try:
                    os.killpg(self.proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                self.proc.wait(timeout=self.config["runtime"]["shutdown_timeout"])
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    try:
                        os.killpg(self.proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self.job:
            self.job.close()
        if self.log:
            self.log.close()
        if self.registered:
            self.registered = False
            self.owner_callback({"kind": "runtime_stopped", "runtime_id": self.directory.name})
        # Keep owned logs/configs for diagnostics under the ignored runtime root.
