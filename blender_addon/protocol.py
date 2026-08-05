"""TCP 协议 — 4 字节大端长度头 + UTF-8 JSON"""

import json
import struct

HEADER = struct.Struct(">I")
MAX_MESSAGE = 64 * 1024 * 1024  # 64 MiB


def recv_message(sock):
    """从 socket 读取一条完整消息，返回 (type, params) 或 None (连接关闭)"""
    header = _recv_exact(sock, HEADER.size)
    if header is None:
        return None
    (length,) = HEADER.unpack(header)
    if length > MAX_MESSAGE:
        raise ValueError(f"消息过大: {length} bytes")
    payload = _recv_exact(sock, length)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))


def send_message(sock, data: dict):
    """发送一条 JSON 消息"""
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    sock.sendall(HEADER.pack(len(payload)) + payload)


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf
