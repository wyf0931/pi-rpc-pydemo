import asyncio
import json
import logging
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from .resources import discover_resources
from .store import PLATFORM_TOOLS, pi_terminal_failure

logger = logging.getLogger(__name__)


class PiRpcError(RuntimeError):
    pass


class ActiveTurn:
    """One agent turn, tracked server-side independent of any SSE viewer.

    Events are recorded in a replay buffer and broadcast to subscriber
    queues, so viewers can disconnect, refresh, or attach from another tab
    without affecting the underlying pi run (mirrors the resumable-stream
    pattern used by LibreChat / the Vercel AI SDK).
    """

    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        self.events: list[dict] = []
        self.subscribers: set[asyncio.Queue] = set()
        self.final_event: dict = {}
        self.error: str | None = None
        self.finished = False
        self.task: asyncio.Task | None = None

    def subscribe(self) -> tuple[asyncio.Queue, list[dict]]:
        queue: asyncio.Queue = asyncio.Queue()
        replay = list(self.events)
        self.subscribers.add(queue)
        if self.finished:
            # The end sentinel was broadcast before this viewer attached;
            # deliver it directly so resumed streams terminate.
            queue.put_nowait(None)
        return queue, replay

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.discard(queue)

    def record(self, event: dict) -> None:
        if event.get("type") == "done":
            self.final_event = event.get("event", {})
        self.events.append(event)
        for queue in list(self.subscribers):
            queue.put_nowait(event)

    def close(self) -> None:
        self.finished = True
        for queue in list(self.subscribers):
            queue.put_nowait(None)


class PiRpcClient:
    STREAM_LIMIT = 16 * 1024 * 1024

    def __init__(
        self,
        command: list[str],
        cwd: str,
        timeout: float = 120.0,
        stream_timeout: float = 600.0,
        cleanup_paths: list[Path] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.command, self.cwd = command, cwd
        # `timeout` bounds RPC request/response round-trips; `stream_timeout`
        # bounds the idle gap between streaming events. A model turn can stay
        # silent for minutes before its first delta (e.g. GLM on a ~30k-token
        # context), and aborting mid-generation throws the answer away.
        self.timeout, self.stream_timeout = timeout, stream_timeout
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
        logger.info(
            "starting Pi RPC process",
            extra={"event": "pi.rpc.start", "operation": "start"},
        )
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
            logger.exception(
                "unable to start Pi RPC process",
                extra={"event": "pi.rpc.start.failed", "operation": "start"},
            )
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
            logger.warning(
                "Pi RPC stderr",
                extra={
                    "event": "pi.rpc.stderr",
                    "operation": "stderr",
                    "pi_stderr": raw.decode(errors="replace").rstrip()[:2000],
                },
            )

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
            event = await asyncio.wait_for(
                self.events.get(), timeout=self.stream_timeout
            )
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
                    yield {"type": "assistant_message_end", "message": end_message}
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
        self.turns: dict[str, ActiveTurn] = {}

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
        extension_paths = [
            self._resource_path(path) for path in agent.get("extensions", [])
        ]
        if any("pi-mcp-adapter" in path for path in extension_paths):
            for tool in ("mcp", "mcpScript"):
                if tool not in tools:
                    tools.append(tool)
        if tools:
            command += ["--tools", ",".join(tools)]
        for path in extension_paths:
            command += ["--extension", path]
        for path in agent.get("skills", []):
            command += ["--skill", self._resource_path(path)]
        return command

    def _resource_path(self, value: str) -> str:
        """Map host Pi and agent-neutral paths to their container mounts."""
        for marker, root in (
            ("/.pi/agent", self.settings.pi_home),
            ("/.agents", self.settings.pi_agents_home),
        ):
            if marker in value:
                suffix = value.split(marker, 1)[1].lstrip("/")
                return str(Path(root) / suffix)
        return value

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        for name, value in {
            "JINA_API_KEY": getattr(self.settings, "jina_api_key", None),
            "BAIDU_SEARCH_API_KEY": getattr(
                self.settings, "baidu_search_api_key", None
            ),
            "BAIDU_SEARCH_BASE_URL": getattr(
                self.settings, "baidu_search_base_url", None
            ),
        }.items():
            if value:
                environment[name] = value
        return environment

    def _mcp_override(self, agent: dict) -> tuple[str | None, list[Path]]:
        if not any(
            "pi-mcp-adapter" in self._resource_path(path)
            for path in agent.get("extensions", [])
        ):
            return None, []
        discovered = discover_resources(
            self.settings.pi_home, self.settings.pi_cwd, self.settings.pi_agents_home
        )["mcp_servers"]
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

    async def _start(
        self, chat: dict, create: bool = False, register: bool = True
    ) -> PiRpcClient:
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
        if register:
            actual_id = state.get("data", {}).get("sessionId") or chat.get("session_id")
            self.clients[chat["id"]] = client
            self.locks.setdefault(chat["id"], asyncio.Lock())
            self.store.update_chat(chat["id"], {"session_id": actual_id})
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
        # Ephemeral client: never registered in self.clients and never
        # touches chat status, so it is safe while a turn is streaming.
        client = await self._start(chat, register=False)
        try:
            response = await client.request("get_messages")
            return response.get("data", {}).get("messages", [])
        finally:
            await client.close()

    def active_turn(self, chat_id: str) -> ActiveTurn | None:
        return self.turns.get(chat_id)

    def start_turn(
        self, chat: dict, message: str, session_name: str | None = None
    ) -> ActiveTurn:
        chat_id = chat["id"]
        lock = self.locks.setdefault(chat_id, asyncio.Lock())
        current = self.turns.get(chat_id)
        if lock.locked() or (current is not None and not current.finished):
            raise PiRpcError("Chat is busy")
        turn = ActiveTurn(chat_id)
        self.turns[chat_id] = turn
        turn.task = asyncio.create_task(
            self._run_turn(turn, chat, message, session_name, lock)
        )
        return turn

    async def _run_turn(
        self,
        turn: ActiveTurn,
        chat: dict,
        message: str,
        session_name: str | None,
        lock: asyncio.Lock,
    ) -> None:
        chat_id = chat["id"]
        await lock.acquire()
        try:
            client = await self._start(chat, create=True)
            try:
                if session_name:
                    await client.request("set_session_name", name=session_name)
                async for event in client.stream_prompt(message):
                    turn.record(event)
            finally:
                await client.close()
                self.clients.pop(chat_id, None)
        except asyncio.CancelledError:
            self.store.update_chat(chat_id, {"status": "stopped"})
            raise
        except (PiRpcError, TimeoutError, OSError) as exc:
            turn.error = str(exc)
            self.store.update_chat(chat_id, {"status": "error"})
        else:
            failure = pi_terminal_failure(turn.final_event.get("messages", []))
            if failure or turn.error:
                self.store.update_chat(chat_id, {"status": "error"})
            else:
                self.store.update_chat(chat_id, {"status": "ready"})
        finally:
            lock.release()
            turn.close()

    def newest_session_file(self, chat: dict) -> Path | None:
        """Newest transcript file for a chat (pi may roll files per turn)."""
        session_id = chat.get("session_id") or chat.get("id")
        if not session_id or not self.settings.pi_session_dir.is_dir():
            return None
        candidates = [
            path
            for path in self.settings.pi_session_dir.iterdir()
            if path.is_file() and path.name.endswith(f"_{session_id}.jsonl")
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime)

    async def abort(self, chat_id: str) -> None:
        client = self.clients.get(chat_id)
        if client:
            await client.abort()
            self.store.update_chat(chat_id, {"status": "stopped"})

    async def close_chat(self, chat_id: str) -> None:
        turn = self.turns.get(chat_id)
        if turn and turn.task and not turn.task.done():
            turn.task.cancel()
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
