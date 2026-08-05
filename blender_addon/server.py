"""TCP 服务器 — 后台接受线程 + bpy.app.timers 主线程执行队列

线程模型:
  接受线程 (daemon)  : accept → recv → 命令入队, 返回排号
  Timer (主线程)     : 每 50ms 取一条命令执行, 结果通过新连接回写
  回写线程 (daemon)  : 客户端轮询时取结果

为避免长命令阻塞 timer, 每条命令独立建立连接:
  客户端: connect → send cmd → 等待响应连接 (或轮询)
简化: 命令执行在 timer 内同步完成 (Blender 操作通常 <100ms),
      长操作 (烘焙/导出) 单独标记 large=True, 由专用线程执行。
"""

import json
import socket
import threading

import bpy

from . import protocol

HOST = "127.0.0.1"
PORT = 9876

# 大操作专用锁: 同一时间只允许一个大操作在专用线程执行
_large_lock = threading.Lock()

# 状态
_server_sock = None
_accept_thread = None
_timer_registered = False
_queue = []  # [(id, type, params)]
_pending = {}  # id -> {"result": dict, "done": bool}
_next_id = 0
_id_lock = threading.Lock()


def ensure_running():
    global _server_sock, _accept_thread, _timer_registered
    if _server_sock is not None:
        return
    try:
        _server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _server_sock.bind((HOST, PORT))
        _server_sock.listen(8)
        _server_sock.settimeout(1.0)
    except OSError as e:
        print(f"[Bridge] 端口 {PORT} 启动失败: {e}")
        _server_sock = None
        return

    _accept_thread = threading.Thread(target=_accept_loop, daemon=True)
    _accept_thread.start()

    if not _timer_registered:
        bpy.app.timers.register(_tick, persistent=True)
        _timer_registered = True
    print(f"[Bridge] listening on {HOST}:{PORT}")


def shutdown():
    global _server_sock
    if _server_sock is not None:
        try:
            _server_sock.close()
        except OSError:
            pass
        _server_sock = None
    if _timer_registered:
        try:
            bpy.app.timers.unregister(_tick)
        except ValueError:
            pass


# ── 接受循环 ──────────────────────────────────────────────

def _accept_loop():
    while _server_sock is not None:
        try:
            conn, _addr = _server_sock.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        conn.settimeout(60)
        threading.Thread(target=_handle_connection, args=(conn,), daemon=True).start()


def _handle_connection(conn):
    try:
        msg = protocol.recv_message(conn)
        if msg is None:
            return
        ctype = msg.get("type", "")
        params = msg.get("params", {}) or {}

        if ctype == "ping":
            protocol.send_message(conn, {"status": "success", "result": {"pong": True}})
            return

        if ctype == "shutdown":
            protocol.send_message(conn, {"status": "success", "result": {"shutdown": True}})
            bpy.app.timers.register(_deferred_shutdown, first_interval=0.5)
            return

        if params.get("large") or msg.get("large"):
            # 大操作: 专用线程执行, 直接回写 (连接保持打开)
            _run_large(ctype, params, conn)
            return

        # 常规操作: 入队, 立即返回排号, 客户端轮询结果
        with _id_lock:
            global _next_id
            _next_id += 1
            cmd_id = _next_id
        _queue.append((cmd_id, ctype, params))
        protocol.send_message(conn, {"status": "queued", "result": {"id": cmd_id}})
    except Exception as e:
        try:
            protocol.send_message(conn, {"status": "error", "message": f"协议错误: {e}"})
        except OSError:
            pass
    finally:
        conn.close()


def _run_large(ctype, params, conn):
    """大操作在专用线程执行, 持锁避免并发大操作"""
    from . import commands
    if not _large_lock.acquire(blocking=False):
        protocol.send_message(conn, {"status": "error", "message": "另一个大操作正在执行"})
        return
    try:
        result = _dispatch(ctype, params)
        protocol.send_message(conn, result)
    except Exception as e:
        protocol.send_message(conn, {"status": "error", "message": f"{type(e).__name__}: {e}"})
    finally:
        _large_lock.release()


# ── 主线程 tick ───────────────────────────────────────────

def _tick():
    """bpy.app.timers 回调 — 在主线程执行队列命令"""
    while _queue:
        cmd_id, ctype, params = _queue.pop(0)
        try:
            result = _dispatch(ctype, params)
        except Exception as e:
            result = {"status": "error", "message": f"{type(e).__name__}: {e}"}
        _pending[cmd_id] = result
        # 清理过旧的结果
        if len(_pending) > 200:
            for k in list(_pending)[:100]:
                del _pending[k]
    return 0.05  # 每 50ms


def poll_result(conn):
    """客户端轮询: {type: poll_result, params: {id: N}}"""
    try:
        msg = protocol.recv_message(conn)
        if msg is None:
            return
        cmd_id = msg.get("params", {}).get("id")
        if cmd_id is not None and cmd_id in _pending:
            result = _pending.pop(cmd_id)
            protocol.send_message(conn, result)
        else:
            protocol.send_message(conn, {"status": "pending"})
    except Exception as e:
        try:
            protocol.send_message(conn, {"status": "error", "message": str(e)})
        except OSError:
            pass


def _deferred_shutdown():
    shutdown()
    return None


def _dispatch(ctype, params):
    """命令分发 — 所有命令处理器在 commands/macros 中"""
    from . import commands, macros

    handler = getattr(commands, ctype, None)
    if handler is None:
        handler = getattr(macros, ctype, None)
    if handler is None:
        return {"status": "error", "message": f"未知命令: {ctype}"}
    result = handler(params)
    return {"status": "success", "result": result}


# 供 commands 模块使用的工具函数
def to_list(v):
    return list(v) if v is not None else None
