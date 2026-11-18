"""Request-scoped guest workspaces; the browser owns their durable state.

Only JSON rows from our schema are restored, never client-supplied SQLite/SQL.
Planning uses an in-memory database; uploaded files live in a temporary directory
which is removed after the response (including streaming Agent runs) finishes.
"""
import asyncio
import base64
import binascii
import json
import tempfile
from pathlib import Path, PurePosixPath
from time import monotonic
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.exceptions import ExceptionMiddleware

from .database import Base
from .runtime import guest_context

router = APIRouter(prefix="/api/guest", tags=["Browser guest"])
MAX_BYTES = 128 * 1024 * 1024
MAX_ROWS = 20_000
active_workspaces = {}
request_slots = asyncio.Semaphore(2)


def decode_bytes(value):
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError, binascii.Error):
        raise HTTPException(422, "访客文件编码无效。") from None


class GuestWorkspace:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="daymark-guest-")
        self.directory = Path(self.temporary.name)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.api_key = ""
        self.key_supplied = False
        self.service = None
        self.stop_requested = False
        self.file_versions = {}

    def restore(self, state):
        if not isinstance(state, dict) or state.get("version", 1) != 1:
            raise HTTPException(422, "访客记录格式不支持，请保留浏览器数据并更新网站。")
        tables, files = state.get("tables", {}), state.get("files", {})
        key = state.get("api_key", "")
        if not isinstance(tables, dict) or not isinstance(files, dict) or not isinstance(key, str):
            raise HTTPException(422, "访客记录格式无效。")
        if len(key) > 1000 or "\n" in key or "\r" in key:
            raise HTTPException(422, "API Key 格式无效。")
        self.api_key = key
        self.key_supplied = "api_key" in state
        count = 0
        try:
            with self.engine.begin() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
                for name, rows in tables.items():
                    table = Base.metadata.tables.get(name)
                    if table is None or not isinstance(rows, list):
                        raise HTTPException(422, "访客记录包含未知的数据表。")
                    count += len(rows)
                    if count > MAX_ROWS:
                        raise HTTPException(413, "访客记录超过 20000 条，请导出备份后使用账号模式。")
                    for row in rows:
                        if not isinstance(row, dict) or set(row) - set(table.columns.keys()):
                            raise HTTPException(422, "访客记录包含无效字段。")
                        connection.execute(table.insert().values(**row))
        except (SQLAlchemyError, TypeError, ValueError):
            raise HTTPException(422, "访客记录无法读取，请保留浏览器数据和备份。") from None
        for name, content in files.items():
            if not isinstance(name, str):
                raise HTTPException(422, "访客文件路径无效。")
            path = PurePosixPath(name)
            if (path.is_absolute() or "\\" in name or ":" in name or ".." in path.parts
                    or len(path.parts) < 2 or path.parts[0] not in {"uploads", "knowledge"}
                    or ".tmp" in path.parts):
                raise HTTPException(422, "访客文件路径无效。")
            destination = self.directory.joinpath(*path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(decode_bytes(content))
        self.file_versions = self._file_versions()

    def _file_versions(self):
        return {path.relative_to(self.directory).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
                for path in self.directory.rglob("*") if path.is_file() and ".tmp" not in path.parts}

    def snapshot(self):
        with self.engine.connect() as connection:
            tables = {table.name: [dict(row) for row in connection.execute(select(table)).mappings()]
                      for table in Base.metadata.tables.values()}
        state = {"version": 1, "tables": tables}
        if self.key_supplied:
            state["api_key"] = self.api_key
        versions = self._file_versions()
        # Unchanged files stay in IndexedDB; do not resend them on each chat token.
        if versions != self.file_versions:
            state["files"] = {name: base64.b64encode((self.directory / name).read_bytes()).decode()
                              for name in versions}
            self.file_versions = versions
        return state

    async def stop(self):
        self.stop_requested = True
        if self.service is not None and self.service.active is not None:
            await self.service.stop(self.service.active.conversation_id)

    def close(self):
        self.engine.dispose()
        self.temporary.cleanup()


async def read_payload(request, limit=MAX_BYTES):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > min(limit, MAX_BYTES):
            raise HTTPException(413, "访客数据包超过 128 MB，请先导出备份。")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        raise HTTPException(422, "访客请求格式无效。") from None
    if not isinstance(data, dict):
        raise HTTPException(422, "访客请求格式无效。")
    return data


def request_scope(request, data):
    method, path = data.get("method", "GET"), data.get("path", "")
    if not isinstance(path, str) or not isinstance(method, str):
        raise HTTPException(422, "访客请求路径无效。")
    parsed = urlsplit(path)
    if (parsed.scheme or parsed.netloc or parsed.fragment or not parsed.path.startswith("/api/")
            or parsed.path.split("/")[2] in {"auth", "guest"}
            or any(part in {".", "..", ""} for part in parsed.path.split("/")[1:])
            or "\\" in parsed.path or "%" in parsed.path
            or method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}):
        raise HTTPException(403, "访客模式不能访问此接口。")
    content_type = data.get("content_type", "application/json")
    if not isinstance(content_type, str) or len(content_type) > 200 or any(c in content_type for c in "\r\n"):
        raise HTTPException(422, "访客请求类型无效。")
    try:
        query = parsed.query.encode("ascii")
        content_type_bytes = content_type.encode("latin-1")
    except UnicodeError:
        raise HTTPException(422, "访客请求编码无效。") from None
    scope = dict(request.scope)
    scope.update(method=method, path=parsed.path, raw_path=parsed.path.encode(),
                 query_string=query, root_path="",
                 headers=[(b"content-type", content_type_bytes)],
                 asgi={"version": "3.0", "spec_version": "2.4"}, extensions={})
    return scope


@router.post("/stop")
async def stop_guest(request: Request):
    data = await read_payload(request, limit=2048)
    run_id = data.get("run_id")
    workspace = active_workspaces.get(run_id) if isinstance(run_id, str) else None
    if workspace is not None:
        await workspace.stop()
    return {"stopped": workspace is not None}


async def dispatch_guest(request: Request):
    data = await read_payload(request)
    scope = request_scope(request, data)
    body = decode_bytes(data.get("body", ""))
    run_id = data.get("run_id")
    try:
        if str(UUID(run_id)) != run_id:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "访客请求标识无效。") from None
    if run_id in active_workspaces:
        raise HTTPException(409, "该访客请求正在执行。")
    if len(active_workspaces) >= 2:
        raise HTTPException(429, "访客服务繁忙，请稍后重试。")
    workspace = GuestWorkspace()
    try:
        workspace.restore(data.get("state", {}))
    except BaseException:
        workspace.close()
        raise
    active_workspaces[run_id] = workspace

    async def frames():
        token = guest_context.set(workspace)
        queue = asyncio.Queue(maxsize=8)
        sent_request = False
        streaming, saved_at = False, monotonic()

        async def receive():
            nonlocal sent_request
            if not sent_request:
                sent_request = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Event().wait()

        async def checkpoint():
            nonlocal saved_at
            state = workspace.snapshot()
            encoded = json.dumps({"kind": "state", "state": state}, ensure_ascii=False).encode() + b"\n"
            if len(encoded) > MAX_BYTES:
                raise HTTPException(413, "访客数据包超过 128 MB，请先导出备份。")
            await queue.put(encoded)
            saved_at = monotonic()

        async def send(message):
            nonlocal streaming
            if message["type"] == "http.response.start":
                headers = {key.decode(): value.decode("latin-1") for key, value in message.get("headers", [])
                           if key.lower() in {b"content-type", b"content-disposition"}}
                streaming = "text/event-stream" in headers.get("content-type", "")
                if workspace.stop_requested:
                    await workspace.stop()
                await queue.put(json.dumps({"kind": "response", "status": message["status"], "headers": headers}).encode() + b"\n")
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if (not message.get("more_body") or (streaming and (
                        monotonic() - saved_at >= 2 or any(marker in chunk for marker in (
                            b'"event": "start"', b'"event": "tool_result"', b'"event": "done"', b'"event": "error"'))))):
                    await checkpoint()
                if chunk:
                    await queue.put(json.dumps({"kind": "body", "data": base64.b64encode(chunk).decode()}).encode() + b"\n")

        async def dispatch():
            try:
                handler = ExceptionMiddleware(request.app.router, handlers=request.app.exception_handlers)
                await asyncio.wait_for(handler(scope, receive, send), timeout=630)
            except Exception:
                await queue.put(b'{"kind":"error","detail":"Guest request failed. Your last browser save is preserved."}\n')
            await queue.put(None)

        task = asyncio.create_task(dispatch())
        try:
            while True:
                frame = await queue.get()
                if frame is None:
                    break
                yield frame
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await workspace.stop()
            active_workspaces.pop(run_id, None)
            workspace.close()
            guest_context.reset(token)

    class GuestResponse(StreamingResponse):
        async def __call__(self, scope, receive, send):
            try:
                await super().__call__(scope, receive, send)
            finally:
                try:
                    # Also covers a disconnect before the generator starts.
                    if active_workspaces.pop(run_id, None) is not None:
                        try:
                            await workspace.stop()
                        finally:
                            workspace.close()
                finally:
                    request_slots.release()

    return GuestResponse(frames(), media_type="application/x-ndjson",
                         headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("")
async def guest_request(request: Request):
    # Reserve capacity before reading large snapshots, without an unbounded queue.
    if request_slots.locked():
        raise HTTPException(429, "访客服务繁忙，请稍后重试。")
    await request_slots.acquire()
    try:
        return await dispatch_guest(request)
    except BaseException:
        request_slots.release()
        raise
