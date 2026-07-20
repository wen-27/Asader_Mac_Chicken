"""Tiny local Redis-compatible server for emergency development.

It implements the subset used by this project: PING, GET, SET with EX/NX,
DEL, SELECT, EXPIRE, TTL and EVAL for lock release.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass
class Entry:
    value: str
    expires_at: float | None = None


STORE: dict[str, Entry] = {}


def _purge(key: str) -> None:
    entry = STORE.get(key)
    if entry and entry.expires_at is not None and entry.expires_at <= time.time():
        STORE.pop(key, None)


async def _read_command(reader: asyncio.StreamReader) -> list[str] | None:
    first = await reader.readline()
    if not first:
        return None
    if first.startswith(b"*"):
        count = int(first[1:].strip() or b"0")
        parts: list[str] = []
        for _ in range(count):
            length_line = await reader.readline()
            if not length_line.startswith(b"$"):
                return None
            length = int(length_line[1:].strip() or b"0")
            data = await reader.readexactly(length)
            await reader.readexactly(2)
            parts.append(data.decode())
        return parts
    return first.decode().strip().split()


def _bulk(value: str | None) -> bytes:
    if value is None:
        return b"$-1\r\n"
    data = value.encode()
    return b"$" + str(len(data)).encode() + b"\r\n" + data + b"\r\n"


def _simple(value: str) -> bytes:
    return f"+{value}\r\n".encode()


def _integer(value: int) -> bytes:
    return f":{value}\r\n".encode()


def _error(value: str) -> bytes:
    return f"-ERR {value}\r\n".encode()


def _handle(parts: list[str]) -> bytes:
    if not parts:
        return _error("empty command")
    cmd = parts[0].upper()
    if cmd == "PING":
        return _simple("PONG")
    if cmd == "SELECT":
        return _simple("OK")
    if cmd == "GET" and len(parts) >= 2:
        key = parts[1]
        _purge(key)
        entry = STORE.get(key)
        return _bulk(entry.value if entry else None)
    if cmd == "SET" and len(parts) >= 3:
        key, value = parts[1], parts[2]
        opts = [part.upper() for part in parts[3:]]
        _purge(key)
        if "NX" in opts and key in STORE:
            return _bulk(None)
        expires_at = None
        if "EX" in opts:
            index = opts.index("EX")
            if index + 1 < len(parts[3:]):
                expires_at = time.time() + int(parts[3:][index + 1])
        STORE[key] = Entry(value=value, expires_at=expires_at)
        return _simple("OK")
    if cmd in {"DEL", "UNLINK"} and len(parts) >= 2:
        removed = 0
        for key in parts[1:]:
            _purge(key)
            if key in STORE:
                removed += 1
                STORE.pop(key, None)
        return _integer(removed)
    if cmd == "EXPIRE" and len(parts) >= 3:
        key = parts[1]
        _purge(key)
        if key not in STORE:
            return _integer(0)
        STORE[key].expires_at = time.time() + int(parts[2])
        return _integer(1)
    if cmd == "TTL" and len(parts) >= 2:
        key = parts[1]
        _purge(key)
        entry = STORE.get(key)
        if entry is None:
            return _integer(-2)
        if entry.expires_at is None:
            return _integer(-1)
        return _integer(max(0, int(entry.expires_at - time.time())))
    if cmd == "EVAL" and len(parts) >= 6:
        key = parts[3]
        token = parts[4]
        _purge(key)
        entry = STORE.get(key)
        if entry and entry.value == token:
            STORE.pop(key, None)
            return _integer(1)
        return _integer(0)
    return _error(f"unsupported command {cmd}")


async def _client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            parts = await _read_command(reader)
            if parts is None:
                break
            writer.write(_handle(parts))
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def main() -> None:
    server = await asyncio.start_server(_client, "127.0.0.1", 6379)
    print("Redis dev stub listening on 127.0.0.1:6379", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
