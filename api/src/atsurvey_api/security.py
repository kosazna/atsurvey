"""Security middleware and computation guards for the engine API.

* ``SecurityHeadersMiddleware`` — nosniff, referrer policy, CORP, no-store on /v1/*.
* ``BodySizeLimitMiddleware`` — rejects oversized bodies early (Content-Length) and while
  streaming (chunked uploads), before the framework buffers them.
* ``RateLimitMiddleware`` — token buckets per verified user id, else per client IP; a
  stricter bucket for /v1/export and /v1/parse. 429 + Retry-After.
* ``run_guarded`` — runs CPU work in a thread under a concurrency semaphore with a timeout.
* ``run_killable`` — runs CPU work in a child process that is killed on timeout (for
  algorithms whose run time is input-dependent, e.g. traverse suggestions).

All middleware is pure ASGI so it also covers streaming bodies and error responses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import multiprocessing as mp
import threading
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings

log = logging.getLogger("atsurvey.security")

HEAVY_PATHS = ("/v1/export", "/v1/parse")


# --------------------------------------------------------------------------- helpers


async def _send_json(
    send: Send, status: int, body: dict, headers: tuple[tuple[bytes, bytes], ...] = ()
):
    payload = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                *headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


def _header(scope: Scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == name:
            return v.decode("latin-1")
    return None


# ------------------------------------------------------------------- security headers


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        api_path = scope["path"].startswith("/v1/")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cross-origin-resource-policy", b"cross-origin"),
                    (b"x-frame-options", b"DENY"),
                    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
                ]
                if api_path:
                    extra.append((b"cache-control", b"no-store"))
                headers += [(k, v) for k, v in extra if k not in present]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ------------------------------------------------------------------- body size limit


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Limit request bodies: JSON bodies to ``max_body_mb``, multipart uploads to
    ``max_upload_mb`` (+1 MB for multipart framing)."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.json_limit = settings.max_body_mb * 1024 * 1024
        self.upload_limit = (settings.max_upload_mb + 1) * 1024 * 1024

    def limit_for(self, scope: Scope) -> int:
        ctype = (_header(scope, b"content-type") or "").lower()
        return self.upload_limit if ctype.startswith("multipart/") else self.json_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope)
        declared = _header(scope, b"content-length")
        if declared is not None:
            try:
                too_big = int(declared) > limit
            except ValueError:
                await _send_json(send, 400, {"detail": "Invalid Content-Length"})
                return
            if too_big:
                await _send_json(send, 413, {"detail": "Request body too large"})
                return

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            if not started:
                await _send_json(send, 413, {"detail": "Request body too large"})


# -------------------------------------------------------------- JSON number safety

#: No surveying quantity comes near this (coordinates ~1e7 m); larger values only overflow.
MAX_ABS_NUMBER = 1e12


class _BadNumber(ValueError):
    pass


def _reject_constant(name: str):
    raise _BadNumber(f"{name} is not allowed")


def _checked_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value) or abs(value) > MAX_ABS_NUMBER:
        raise _BadNumber(f"number {text[:32]} out of range")
    return value


def _checked_int(text: str) -> int:
    if len(text) > 15:
        raise _BadNumber("integer out of range")
    value = int(text)
    if abs(value) > MAX_ABS_NUMBER:
        raise _BadNumber("integer out of range")
    return value


def validate_json_numbers(body: bytes) -> None:
    """Reject NaN / Infinity literals (non-standard JSON that Python accepts) and absurd
    magnitudes. Non-finite values would otherwise become ``null`` coordinates and make
    different inputs hash identically."""
    json.loads(
        body,
        parse_constant=_reject_constant,
        parse_float=_checked_float,
        parse_int=_checked_int,
    )


class JsonNumberSafetyMiddleware:
    """Validates numbers in JSON request bodies before the framework parses them.
    Bodies are already bounded by BodySizeLimitMiddleware (outer)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        ctype = (_header(scope, b"content-type") or "").lower() if scope["type"] == "http" else ""
        if scope["type"] != "http" or scope["method"] != "POST" or "json" not in ctype:
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        try:
            validate_json_numbers(body)
        except _BadNumber as exc:
            await _send_json(send, 422, {"detail": f"Invalid number in request: {exc}"})
            return
        except RecursionError:
            await _send_json(send, 422, {"detail": "JSON nested too deeply"})
            return
        except ValueError:
            pass  # malformed JSON: let the framework produce its normal 422

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


# ---------------------------------------------------------------------- rate limiting


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class TokenBucketLimiter:
    """Thread-safe in-memory token buckets with periodic cleanup of idle keys."""

    def __init__(self, per_minute: int, burst: int, idle_ttl: float = 600.0) -> None:
        self.rate = per_minute / 60.0
        self.capacity = float(max(1, burst))
        self.idle_ttl = idle_ttl
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def take(self, key: str, now: float | None = None) -> float:
        """Consume one token. Returns 0 if allowed, else seconds until a token is available."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if now - self._last_sweep > 60:
                self._sweep(now)
            b = self._buckets.get(key)
            if b is None:
                b = self._buckets[key] = _Bucket(self.capacity, now)
            else:
                b.tokens = min(self.capacity, b.tokens + (now - b.updated) * self.rate)
                b.updated = now
            if b.tokens >= 1.0:
                b.tokens -= 1.0
                return 0.0
            return (1.0 - b.tokens) / self.rate if self.rate > 0 else 60.0

    def _sweep(self, now: float) -> None:
        stale = [k for k, b in self._buckets.items() if now - b.updated > self.idle_ttl]
        for k in stale:
            del self._buckets[k]
        self._last_sweep = now

    def __len__(self) -> int:
        return len(self._buckets)


class RateLimiter:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.rate_limit_enabled
        self.trusted_proxy = settings.trusted_proxy
        self.general = TokenBucketLimiter(settings.rate_limit_per_minute, settings.rate_limit_burst)
        self.heavy = TokenBucketLimiter(
            settings.rate_limit_heavy_per_minute, settings.rate_limit_heavy_burst
        )
        self.settings = settings

    def client_key(self, scope: Scope) -> str:
        auth = _header(scope, b"authorization")
        if auth and auth.lower().startswith("bearer "):
            from .auth import verify_token  # local import: avoid a cycle

            try:
                sub = verify_token(auth[7:].strip(), self.settings).get("sub")
                if sub:
                    return f"user:{sub}"
            except HTTPException:
                pass  # invalid tokens are limited by IP (and rejected later)
        return f"ip:{self.client_ip(scope)}"

    def client_ip(self, scope: Scope) -> str:
        if self.trusted_proxy:
            xff = _header(scope, b"x-forwarded-for")
            if xff:
                first = xff.split(",")[0].strip()
                if first:
                    return first
        client = scope.get("client")
        return client[0] if client else "unknown"


class RateLimitMiddleware:
    """Reads the limiter from ``app.state.rate_limiter`` so it can be swapped at runtime."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        limiter: RateLimiter | None = getattr(scope["app"].state, "rate_limiter", None)
        if limiter is None or not limiter.enabled or not path.startswith("/v1/"):
            await self.app(scope, receive, send)
            return
        key = await asyncio.to_thread(limiter.client_key, scope)
        wait = limiter.general.take(key)
        if not wait and path.startswith(HEAVY_PATHS):
            wait = limiter.heavy.take(key)
        if wait:
            retry = str(max(1, math.ceil(wait)))
            await _send_json(
                send,
                429,
                {"detail": "Too many requests", "retry_after": int(retry)},
                ((b"retry-after", retry.encode()),),
            )
            return
        await self.app(scope, receive, send)


# ------------------------------------------------------------------ computation guards

_slots: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


def _semaphore(n: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _slots.get(loop)
    if sem is None:
        sem = _slots[loop] = asyncio.Semaphore(n)
    return sem


async def _acquire(settings: Settings) -> asyncio.Semaphore:
    sem = _semaphore(settings.concurrency)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=settings.compute_queue_timeout_s)
    except TimeoutError as exc:
        raise HTTPException(
            503, "Server busy, try again shortly", headers={"Retry-After": "5"}
        ) from exc
    return sem


async def run_guarded(
    settings: Settings, fn: Callable[..., Any], *args: Any, timeout: float
) -> Any:
    """Run ``fn`` in a worker thread, holding a computation slot until the thread finishes
    (a timed-out thread keeps running, so its slot stays taken until it really ends)."""
    sem = await _acquire(settings)
    fut = asyncio.ensure_future(asyncio.to_thread(fn, *args))
    fut.add_done_callback(lambda _: sem.release())
    try:
        return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
    except TimeoutError as exc:
        raise HTTPException(504, "Computation timed out") from exc


def _child(conn, fn, args) -> None:  # pragma: no cover - runs in the child process
    try:
        conn.send((True, fn(*args)))
    except BaseException as exc:
        try:
            conn.send((False, exc))
        except Exception:  # unpicklable exception
            conn.send((False, RuntimeError(type(exc).__name__)))
    finally:
        conn.close()


_ctx = None


def _mp_context():
    global _ctx
    if _ctx is None:
        if "forkserver" in mp.get_all_start_methods():
            _ctx = mp.get_context("forkserver")
            _ctx.set_forkserver_preload(["atsurvey", "atsurvey.core.suggest"])
        else:  # pragma: no cover - non-Linux
            _ctx = mp.get_context("spawn")
    return _ctx


async def run_killable(
    settings: Settings, fn: Callable[..., Any], *args: Any, timeout: float
) -> Any:
    """Run ``fn(*args)`` in a child process that is killed on timeout (→ 504).

    Threads cannot be stopped, so input-dependent algorithms (e.g. route enumeration) run
    here: a pathological request costs at most ``timeout`` seconds of one CPU.
    """
    sem = await _acquire(settings)
    ctx = _mp_context()
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(child, fn, args), daemon=True)
    try:
        proc.start()
        child.close()

        def wait() -> tuple[bool, Any] | None:
            if parent.poll(timeout):
                try:
                    return parent.recv()
                except EOFError:
                    return (False, RuntimeError("worker exited"))
            return None

        result = await asyncio.to_thread(wait)
        if result is None:
            raise HTTPException(504, "Computation timed out")
        ok, value = result
        if ok:
            return value
        if isinstance(value, ValueError):
            raise value
        log.error("killable worker failed: %r", value)
        raise HTTPException(500, "Internal error")
    finally:
        if proc.pid is not None:
            if proc.is_alive():
                proc.kill()
            proc.join(1)
        parent.close()
        sem.release()
