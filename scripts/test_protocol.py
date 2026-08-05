"""协议层端到端测试 — 模拟 addon 服务器, 验证排队/轮询/大操作

不需要 Blender, 纯 Python 可运行:
    python scripts/test_protocol.py
"""

import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "blender_addon"))

import protocol as proto  # noqa: E402


class MockAddonServer:
    """模拟 blender_addon/server.py 的行为 (排队 → 轮询 → 大操作直连)"""

    def __init__(self, port=9887):
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(4)
        self.sock.settimeout(0.2)
        self.queue = []
        self.pending = {}
        self.next_id = 0
        self.running = True
        self.lock = threading.Lock()
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()

    def _accept_loop(self):
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            msg = proto.recv_message(conn)
            if msg is None:
                return
            t = msg.get("type")
            p = msg.get("params", {})
            if t == "ping":
                proto.send_message(conn, {"status": "success", "result": {"pong": True}})
            elif p.get("large") or msg.get("large"):
                # 大操作: 同步执行, 直接回写 (与真实 addon 的 _run_large 一致)
                time.sleep(0.05)
                proto.send_message(conn, {"status": "success",
                                          "result": {"echo": t, "params": p, "large": True}})
            elif t == "poll_result":
                cid = p.get("id")
                with self.lock:
                    if cid in self.pending:
                        r = self.pending.pop(cid)
                        proto.send_message(conn, r)
                    else:
                        proto.send_message(conn, {"status": "pending"})
            else:
                with self.lock:
                    self.next_id += 1
                    cid = self.next_id
                    self.queue.append((cid, t, p))
                proto.send_message(conn, {"status": "queued", "result": {"id": cid}})
        except Exception as e:
            try:
                proto.send_message(conn, {"status": "error", "message": str(e)})
            except OSError:
                pass
        finally:
            conn.close()

    def _worker(self):
        """模拟主线程 timer: 每 50ms 处理一条"""
        while self.running:
            item = None
            with self.lock:
                if self.queue:
                    item = self.queue.pop(0)
            if item:
                cid, t, p = item
                time.sleep(0.05)  # 模拟执行耗时
                with self.lock:
                    self.pending[cid] = {"status": "success",
                                         "result": {"echo": t, "params": p}}
            else:
                time.sleep(0.01)

    def close(self):
        self.running = False
        self.sock.close()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    server = MockAddonServer()
    time.sleep(0.2)

    from mcp_server.blender_client import BlenderClient
    c = BlenderClient(port=server.port, poll_interval=0.02)

    results = []
    results.append(("ping", c.ping() is True))

    r = c.send_command("create_wall", {"length": 4.0})
    results.append(("排队命令返回 queued → 自动轮询到结果",
                    r.get("status") == "success" and r.get("result", {}).get("echo") == "create_wall"))

    r = c.create_wall(5.0, 2.8, 0.2, name="WallX")
    results.append(("宏方法封装 (create_wall)", r.get("status") == "success"))

    r = c.send_command("export_fbx", {"filepath": "x.fbx"}, large=True)
    results.append(("大操作直连 (large=True)", r.get("status") == "success"))

    # 顺序保证: 两个排队命令按序执行
    r1 = c.send_command("cmd_a")
    r2 = c.send_command("cmd_b")
    results.append(("命令顺序保证", r1.get("result", {}).get("echo") == "cmd_a"
                    and r2.get("result", {}).get("echo") == "cmd_b"))

    # 断连重试: 服务器关闭后重连 (模拟 addon 刚启动)
    server.close()
    time.sleep(0.1)
    server2 = MockAddonServer()
    time.sleep(0.2)
    r = c.send_command("create_object", {"type": "cube"}, retries=2)
    results.append(("重连后恢复工作", r.get("status") == "success"))
    server2.close()

    print("=" * 60)
    print("协议层测试")
    print("=" * 60)
    passed = 0
    for label, ok in results:
        print(f"  {'✅' if ok else '❌'} {label}")
        passed += ok
    print(f"\n{passed}/{len(results)} 通过")
    server.close()
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
