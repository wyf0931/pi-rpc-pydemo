import asyncio
import json
import os
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from .resources import discover_resources
from .store import PLATFORM_TOOLS


class PiRpcError(RuntimeError):
    pass


class PiRpcClient:
    STREAM_LIMIT = 16 * 1024 * 1024

    def __init__(
        self,
        command: list[str],
        cwd: str,
        timeout: float = 120.0,
        cleanup_paths: list[Path] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.command, self.cwd, self.timeout = command, cwd, timeout
        self.cleanup_paths = cleanup_paths or []
        self.env = env
        self.process: asyncio.subprocess.Process | None = None
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.responses: dict[str, asyncio.Future[dict]] = {}
        self.reader_task: asyncio.Task | None = None
        self.stderr_task: asyncio.Task | None = None
        self._counter = 0
        self.is_settled = True
        self.settled_event = asyncio.Event()
        self.settled_event.set()

    async def start(self) -> dict:
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                cwd=self.cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
                limit=self.STREAM_LIMIT,
            )
        except OSError as exc:
            raise PiRpcError(f"Unable to start Pi: {exc}") from exc
        self.reader_task = asyncio.create_task(self._read_stdout())
        self.stderr_task = asyncio.create_task(self._drain_stderr())
        return await self.request("get_state")

    async def _drain_stderr(self) -> None:
        """Forward Pi stderr to the process log instead of discarding it."""
        if not self.process or not self.process.stderr:
            return
        while True:
            raw = await self.process.stderr.readline()
            if not raw:
                break
            print(f"[pi rpc] {raw.decode(errors='replace').rstrip()}", file=sys.stderr, flush=True)

    async def _read_stdout(self) -> None:
        assert self.process and self.process.stdout
        while True:
            raw = await self.process.stdout.readline()
            if not raw:
                break
            try:
                record = json.loads(raw.decode("utf-8").rstrip("\r\n"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if record.get("type") in {"agent_start", "turn_start"}:
                self.is_settled = False
                self.settled_event.clear()
            elif record.get("type") == "agent_settled":
                self.is_settled = True
                self.settled_event.set()
            request_id = record.get("id")
            if record.get("type") == "response" and request_id in self.responses:
                future = self.responses.pop(request_id)
                if not future.done():
                    future.set_result(record)
            else:
                await self.events.put(record)
        for future in self.responses.values():
            if not future.done():
                future.set_exception(PiRpcError("Pi RPC process exited"))

    async def request(self, command: str, **payload) -> dict:
        if not self.process or not self.process.stdin:
            raise PiRpcError("Pi RPC process is not running")
        self._counter += 1
        request_id = f"platform-{self._counter}"
        future = asyncio.get_running_loop().create_future()
        self.responses[request_id] = future
        body = {"id": request_id, "type": command, **payload}
        self.process.stdin.write((json.dumps(body) + "\n").encode())
        await self.process.stdin.drain()
        response = await asyncio.wait_for(future, timeout=self.timeout)
        if not response.get("success", False):
            raise PiRpcError(response.get("error", f"Pi rejected {command}"))
        return response

    async def prompt(self, message: str) -> dict:
        result = {"text": "", "tools": [], "event": None}
        async for event in self.stream_prompt(message):
            if event["type"] == "delta":
                result["text"] += event["delta"]
            elif event["type"] == "tool":
                result["tools"].append(event)
            elif event["type"] == "done":
                result["event"] = event.get("event")
        return result

    async def stream_prompt(self, message: str) -> AsyncIterator[dict[str, Any]]:
        await self.request("prompt", message=message)
        agent_finished = False
        while True:
            event = await asyncio.wait_for(self.events.get(), timeout=self.timeout)
            event_type = event.get("type")
            if event_type == "message_update":
                assistant_event = event.get("assistantMessageEvent", {})
                if assistant_event.get("type") == "text_delta":
                    yield {"type": "delta", "delta": assistant_event.get("delta", "")}
                elif assistant_event.get("type") == "thinking_delta":
                    yield {
                        "type": "thinking_delta",
                        "delta": assistant_event.get("delta", ""),
                    }
            elif event_type == "message_end":
                end_message = event.get("message", {})
                if end_message.get("role") == "assistant":
                    final_text = "".join(
                        part.get("text", "")
                        for part in end_message.get("content", [])
                        if part.get("type") == "text"
                    )
                    yield {"type": "final", "text": final_text}
            elif event_type == "tool_execution_start":
                yield {
                    "type": "tool",
                    "phase": "start",
                    "tool_name": event.get("toolName"),
                }
            elif event_type == "tool_execution_end":
                yield {
                    "type": "tool",
                    "phase": "end",
                    "tool_name": event.get("toolName"),
                    "is_error": event.get("isError", False),
                }
            elif event_type == "agent_end":
                yield {"type": "done", "event": event}
                agent_finished = True
            elif event_type == "agent_settled" and agent_finished:
                yield {"type": "settled"}
                return

    async def abort(self) -> None:
        if self.process and self.process.returncode is None:
            try:
                await self.request("abort")
            except (PiRpcError, TimeoutError):
                pass

    async def close(self) -> None:
        if not self.process:
            return
        if self.process.returncode is None:
            await self.abort()
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self.reader_task:
            self.reader_task.cancel()
        if self.stderr_task:
            self.stderr_task.cancel()
        for path in self.cleanup_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


class PiRuntimeManager:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.clients: dict[str, PiRpcClient] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    def _command(self, agent: dict, session_id: str, create: bool = False) -> list[str]:
        command = [
            self.settings.pi_cli_path,
            "--mode",
            "rpc",
            "--session-dir",
            str(self.settings.pi_session_dir),
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
        ]
        command += ["--session-id" if create else "--session", session_id]
        command += ["--system-prompt", agent["instruction"]]
        provider = agent.get("provider") or self.settings.pi_provider
        model = agent.get("model") or self.settings.pi_model
        if provider:
            command += ["--provider", provider]
        if model:
            command += ["--model", model]
        command += [
            "--thinking",
            agent.get("thinking_level") or self.settings.pi_thinking_level,
        ]
        command += ["--no-tools"]
        tools = list(agent.get("tools") or [])
        if any(tool in tools for tool in PLATFORM_TOOLS):
            extension = Path(__file__).parent.parent / "extensions" / "oma-web-tools.ts"
            command += ["--extension", str(extension)]
        if any("pi-mcp-adapter" in path for path in agent.get("extensions", [])):
            for tool in ("mcp", "mcpScript"):
                if tool not in tools:
                    tools.append(tool)
        if tools:
            command += ["--tools", ",".join(tools)]
        for path in agent.get("extensions", []):
            command += ["--extension", path]
        for path in agent.get("skills", []):
            command += ["--skill", path]
        return command

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        for name, value in {
            "JINA_API_KEY": getattr(self.settings, "jina_api_key", None),
            "BAIDU_SEARCH_API_KEY": getattr(self.settings, "baidu_search_api_key", None),
            "BAIDU_SEARCH_BASE_URL": getattr(self.settings, "baidu_search_base_url", None),
        }.items():
            if value:
                environment[name] = value
        return environment

    def _mcp_override(self, agent: dict) -> tuple[str | None, list[Path]]:
        if not any("pi-mcp-adapter" in path for path in agent.get("extensions", [])):
            return None, []
        discovered = discover_resources(self.settings.pi_home, self.settings.pi_cwd)[
            "mcp_servers"
        ]
        selected = set(agent.get("mcp_servers") or [])
        if not discovered:
            return None, []
        fd, raw_path = tempfile.mkstemp(prefix="pi-agent-mcp-", suffix=".json")
        path = Path(raw_path)
        os.close(fd)
        config = {
            "mcpServers": {
                item["id"]: {"disabled": item["id"] not in selected}
                for item in discovered
            }
        }
        path.write_text(json.dumps(config), encoding="utf-8")
        return str(path), [path]

    async def _start(self, chat: dict, create: bool = False) -> PiRpcClient:
        agent = self.store.get_agent(chat["agent_id"])
        if not agent:
            raise PiRpcError("Agent no longer exists")
        mcp_config, cleanup_paths = self._mcp_override(agent)
        command = self._command(agent, chat["session_id"], create)
        if mcp_config:
            command += ["--mcp-config", mcp_config]
        client = PiRpcClient(
            command,
            str(self.settings.pi_cwd),
            cleanup_paths=cleanup_paths,
            env=self._environment(),
        )
        state = await client.start()
        actual_id = state.get("data", {}).get("sessionId") or chat.get("session_id")
        self.clients[chat["id"]] = client
        self.locks.setdefault(chat["id"], asyncio.Lock())
        self.store.update_chat(chat["id"], {"session_id": actual_id, "status": "ready"})
        return client

    async def send(self, chat: dict, message: str) -> dict:
        client = await self._start(chat, create=True)
        lock = self.locks.setdefault(chat["id"], asyncio.Lock())
        if lock.locked():
            raise PiRpcError("Chat is busy")
        async with lock:
            try:
                return await client.prompt(message)
            finally:
                await client.close()
                self.clients.pop(chat["id"], None)

    async def stream(self, chat: dict, message: str, session_name: str | None = None):
        client = await self._start(chat, create=True)
        lock = self.locks.setdefault(chat["id"], asyncio.Lock())
        if lock.locked():
            raise PiRpcError("Chat is busy")
        async with lock:
            try:
                if session_name:
                    await client.request("set_session_name", name=session_name)
                async for event in client.stream_prompt(message):
                    yield event
            finally:
                await client.close()
                self.clients.pop(chat["id"], None)

    async def messages(self, chat: dict) -> list:
        client = await self._start(chat)
        try:
            response = await client.request("get_messages")
            return response.get("data", {}).get("messages", [])
        finally:
            await client.close()
            self.clients.pop(chat["id"], None)

    async def abort(self, chat_id: str) -> None:
        client = self.clients.get(chat_id)
        if client:
            await client.abort()
            self.store.update_chat(chat_id, {"status": "stopped"})

    async def close_chat(self, chat_id: str) -> None:
        client = self.clients.get(chat_id)
        if client:
            await client.close()
            self.clients.pop(chat_id, None)

    async def _close_client(self, chat_id: str) -> None:
        client = self.clients.get(chat_id)
        if client:
            await client.close()
            self.clients.pop(chat_id, None)

    async def close(self) -> None:
        await asyncio.gather(
            *(self._close_client(chat_id) for chat_id in list(self.clients)),
            return_exceptions=True,
        )
