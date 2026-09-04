import asyncio
import copy
import json
import re
from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from ...config import Settings
from ...files import (
    delete_chat_files,
    discover_chat_files,
    discover_session_files,
    read_session_messages,
    resolve_chat_file,
)
from ...pi_rpc import ActiveTurn, PiRpcError, PiRuntimeManager
from ...store import Store, now_iso, pi_terminal_failure

SSE_KEEPALIVE_SECONDS = 20.0
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class ChatCreate(BaseModel):
    agent_id: str


class ChatUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100000)


def title_for(content: str) -> str:
    return " ".join(content.split())[:48] or "New conversation"


SKILL_BLOCK_RE = re.compile(
    r'^<skill name="(?P<name>[^"]+)" location="(?P<location>[^"]+)">\n'
    r"[\s\S]*?\n</skill>(?:\n\n(?P<user_message>[\s\S]+))?$"
)


def _text_message_content(message: dict) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict) or not isinstance(part.get("text"), str):
            return None
        parts.append(part["text"])
    return "".join(parts) if parts else None


def _compact_skill_invocation(message: dict) -> dict | None:
    if message.get("role") != "user":
        return None
    text = _text_message_content(message)
    match = SKILL_BLOCK_RE.fullmatch(text) if text is not None else None
    if not match:
        return None
    name = match.group("name")
    user_message = (match.group("user_message") or "").strip()
    command = f"/skill:{name}"
    display_content = command + (f" {user_message}" if user_message else "")
    message["display_content"] = display_content
    message["_skill_invocation"] = {
        "name": name,
        "command": command,
        "user_message": user_message,
    }
    message["content"] = [{"type": "text", "text": display_content}]
    return message["_skill_invocation"]


def visible_messages(messages: list[dict], mode: str = "production") -> list[dict]:
    """Attach web activity results to calls while hiding raw process results."""
    results = {
        message.get("toolCallId"): message
        for message in messages
        if message.get("role") == "toolResult"
        and message.get("toolName") in {"web_search", "web_fetch"}
    }
    visible: list[dict] = []
    for original in messages:
        if original.get("role") == "toolResult" and original.get("toolName") in {
            "web_search",
            "web_fetch",
        }:
            continue
        message = copy.deepcopy(original)
        if message.get("role") == "assistant":
            for part in message.get("content") or []:
                if part.get("type") != "toolCall" or part.get("name") not in {
                    "web_search",
                    "web_fetch",
                }:
                    continue
                result = results.get(part.get("id"))
                if result:
                    part["webResult"] = result
                    arguments = part.get("arguments")
                    if isinstance(arguments, dict):
                        arguments["_webResult"] = result
                if message.get("timestamp") is not None:
                    part["_timestamp"] = message["timestamp"]
        _compact_skill_invocation(message)
        if mode != "development" and message.get("role") == "toolResult":
            continue
        visible.append(message)
    return visible


def _sse_data(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _absorb_turn_event(
    event: dict, text: str, tools: list[dict]
) -> tuple[str, list[dict]]:
    if event["type"] == "delta":
        text += event["delta"]
    elif event["type"] == "final":
        text = event["text"]
    elif event["type"] == "tool":
        tools.append(event)
    return text, tools


def _pump_failure_reason(turn: ActiveTurn) -> str | None:
    task = turn.task
    if task is None or not task.done() or task.cancelled():
        return None
    exc = task.exception()
    if exc is None or turn.finished:
        return None
    return str(exc)


def create_router(
    settings: Settings,
    store: Store,
    runtime: PiRuntimeManager,
    visible_or_404: Callable[[dict | None, Request, str], dict],
    visible_records: Callable[[list[dict], Request], list[dict]],
    user_id: Callable[[Request], str],
    has_session_file: Callable[[dict], bool],
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["chats"])

    async def turn_event_stream(
        turn: ActiveTurn, queue: asyncio.Queue, replay: list[dict]
    ) -> AsyncIterator[str]:
        text = ""
        tools: list[dict] = []
        try:
            for event in replay:
                text, tools = _absorb_turn_event(event, text, tools)
                yield _sse_data(event)
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=SSE_KEEPALIVE_SECONDS
                    )
                except TimeoutError:
                    failure = _pump_failure_reason(turn)
                    if failure is not None:
                        store.update_chat(turn.chat_id, {"status": "error"})
                        yield _sse_data({"type": "error", "error": failure})
                        return
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    break
                text, tools = _absorb_turn_event(event, text, tools)
                yield _sse_data(event)
            failure = pi_terminal_failure(turn.final_event.get("messages", []))
            error = failure or turn.error
            if error:
                yield _sse_data({"type": "error", "error": error})
                return
            updated = store.get_chat(turn.chat_id)
            if not updated:
                return
            turn_messages = visible_messages(
                [
                    message
                    for message in turn.final_event.get("messages", [])
                    if message.get("role") in {"assistant", "toolResult"}
                ],
                "development",
            )
            yield _sse_data(
                {
                    "type": "complete",
                    "chat": updated,
                    "assistant": text,
                    "tools": tools,
                    "messages": turn_messages,
                }
            )
        finally:
            turn.unsubscribe(queue)

    @router.get("/chats")
    async def list_chats(request: Request):
        chats = [
            chat
            for chat in visible_records(store.list_chats(), request)
            if chat.get("title") != "New conversation" or has_session_file(chat)
        ]
        return {"chats": chats}

    @router.post("/chats", status_code=201)
    async def create_chat(payload: ChatCreate, request: Request):
        agent = visible_or_404(store.get_agent(payload.agent_id), request, "Agent")
        return store.create_chat(
            payload.agent_id,
            status="created",
            user_id=agent.get("user_id") or user_id(request),
        )

    @router.patch("/chats/{chat_id}")
    async def update_chat(chat_id: str, payload: ChatUpdate, request: Request):
        if not payload.title.strip():
            raise HTTPException(422, "Chat title cannot be empty")
        visible_or_404(store.get_chat(chat_id), request, "Chat")
        return store.update_chat(chat_id, {"title": payload.title.strip()})

    @router.get("/chats/{chat_id}")
    async def get_chat(chat_id: str, request: Request):
        chat = visible_or_404(store.get_chat(chat_id), request, "Chat")
        if chat.get("title") == "New conversation" and not has_session_file(chat):
            raise HTTPException(404, "Chat has not started")
        return chat

    @router.delete("/chats/{chat_id}")
    async def delete_chat(chat_id: str, request: Request):
        chat = visible_or_404(store.get_chat(chat_id), request, "Chat")
        await runtime.close_chat(chat_id)
        session_id = chat.get("session_id") or chat_id
        session_paths = [
            path
            for path in settings.pi_session_dir.iterdir()
            if path.is_file() and path.name.endswith(f"_{session_id}.jsonl")
        ]
        if not session_paths:
            store.delete_chat(chat_id)
            return {"ok": True, "deleted_files": [], "deleted_sessions": []}
        try:
            messages = await runtime.messages(chat)
        except PiRpcError:
            messages = []
        protected_paths: set[str] = set()
        for other_chat in visible_records(store.list_chats(), request):
            if other_chat["id"] == chat_id:
                continue
            try:
                other_messages = await runtime.messages(other_chat)
            except PiRpcError:
                continue
            protected_paths.update(
                item["path"]
                for item in discover_chat_files(other_messages, settings.pi_cwd)
            )
        deleted_files = delete_chat_files(messages, settings.pi_cwd, protected_paths)
        deleted_sessions = []
        for session_path in session_paths:
            try:
                session_path.unlink()
                deleted_sessions.append(session_path.name)
            except OSError:
                continue
        store.delete_chat(chat_id)
        return {
            "ok": True,
            "deleted_files": deleted_files,
            "deleted_sessions": deleted_sessions,
        }

    @router.get("/chats/{chat_id}/messages")
    async def get_messages(chat_id: str, request: Request, mode: str = "production"):
        chat = visible_or_404(store.get_chat(chat_id), request, "Chat")
        if chat["status"] == "created":
            return {"messages": []}
        if not has_session_file(chat):
            raise HTTPException(404, "Pi session not found for this chat")
        if runtime.active_turn(chat_id) is not None:
            session_file = runtime.newest_session_file(chat)
            messages = read_session_messages(session_file) if session_file else []
            return {"messages": visible_messages(messages, mode)}
        try:
            return {"messages": visible_messages(await runtime.messages(chat), mode)}
        except PiRpcError as exc:
            store.update_chat(chat_id, {"status": "error"})
            raise HTTPException(503, str(exc)) from exc

    @router.get("/chats/{chat_id}/files")
    async def list_chat_files(chat_id: str, request: Request):
        chat = visible_or_404(store.get_chat(chat_id), request, "Chat")
        if not has_session_file(chat):
            return {"files": []}
        try:
            files = discover_chat_files(await runtime.messages(chat), settings.pi_cwd)
            return {"files": [{**file, "chat_id": chat_id} for file in files]}
        except PiRpcError as exc:
            raise HTTPException(503, str(exc)) from exc

    @router.get("/chats/{chat_id}/files/content")
    async def get_chat_file(chat_id: str, path: str, request: Request):
        chat = visible_or_404(store.get_chat(chat_id), request, "Chat")
        if not has_session_file(chat):
            raise HTTPException(404, "Pi session not found for this chat")
        try:
            file_path = resolve_chat_file(
                await runtime.messages(chat), settings.pi_cwd, path
            )
        except PiRpcError as exc:
            raise HTTPException(503, str(exc)) from exc
        if not file_path:
            raise HTTPException(404, "File not found or not generated by this chat")
        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise HTTPException(415, "File is not a readable UTF-8 text file") from exc
        return {"content": content}

    @router.get("/library/files")
    async def list_library_files(
        request: Request,
        search: str = "",
        agent_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ):
        page = max(1, page)
        page_size = min(max(1, page_size), 100)

        def files_for_chat(chat: dict) -> list[dict]:
            session_id = chat.get("session_id") or chat["id"]
            session_paths = list(settings.pi_session_dir.glob(f"*_{session_id}.jsonl"))
            if not session_paths:
                return []
            files = discover_session_files(session_paths[0], settings.pi_cwd)
            agent = store.get_agent(chat["agent_id"]) or {}
            return [
                {
                    **file,
                    "chat_id": chat["id"],
                    "agent_id": chat["agent_id"],
                    "agent_name": agent.get("name", "unknown agent"),
                }
                for file in files
            ]

        files = [
            file
            for chat in visible_records(store.list_chats(), request)
            for file in files_for_chat(chat)
        ]
        query = search.strip().casefold()
        if agent_id:
            files = [file for file in files if file["agent_id"] == agent_id]
        if query:
            files = [
                file
                for file in files
                if query in file["name"].casefold() or query in file["path"].casefold()
            ]
        files.sort(key=lambda file: file["generated_at"], reverse=True)
        total = len(files)
        start = (page - 1) * page_size
        return {
            "files": files[start : start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    @router.get("/chats/{chat_id}/files/download")
    async def download_chat_file(chat_id: str, path: str, request: Request):
        chat = visible_or_404(store.get_chat(chat_id), request, "Chat")
        try:
            file_path = resolve_chat_file(
                await runtime.messages(chat), settings.pi_cwd, path
            )
        except PiRpcError as exc:
            raise HTTPException(503, str(exc)) from exc
        if not file_path:
            raise HTTPException(404, "File not found or not generated by this chat")
        return FileResponse(
            file_path, filename=file_path.name, media_type="application/octet-stream"
        )

    @router.post("/chats/{chat_id}/messages")
    async def send_message(
        chat_id: str, payload: MessageCreate, request: Request, mode: str = "production"
    ):
        chat = visible_or_404(store.get_chat(chat_id), request, "Chat")
        store.update_chat(
            chat_id,
            {
                "status": "running",
                "last_activity_at": now_iso(),
                "title": title_for(payload.content)
                if chat["title"] == "New conversation"
                else chat["title"],
            },
        )
        try:
            turn = runtime.start_turn(
                chat,
                payload.content,
                session_name=title_for(payload.content)
                if chat["title"] == "New conversation"
                else None,
            )
        except PiRpcError as exc:
            if "busy" not in str(exc).casefold():
                store.update_chat(chat_id, {"status": "error"})
            raise HTTPException(503, str(exc)) from exc
        queue, replay = turn.subscribe()
        return StreamingResponse(
            turn_event_stream(turn, queue, replay),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    @router.get("/chats/{chat_id}/stream")
    async def resume_chat_stream(chat_id: str, request: Request):
        visible_or_404(store.get_chat(chat_id), request, "Chat")
        turn = runtime.active_turn(chat_id)
        if turn is None:
            return Response(status_code=204)
        queue, replay = turn.subscribe()
        return StreamingResponse(
            turn_event_stream(turn, queue, replay),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    @router.post("/chats/{chat_id}/abort")
    async def abort_chat(chat_id: str, request: Request):
        visible_or_404(store.get_chat(chat_id), request, "Chat")
        await runtime.abort(chat_id)
        return {"ok": True}

    return router
