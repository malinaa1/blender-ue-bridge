"""
Blender↔UE Bridge Addon — Blender 端 TCP 服务器

零依赖 (仅 bpy + stdlib)，在 Blender 内运行：
- 后台线程接受 TCP 连接 (端口 9876)
- 命令通过 bpy.app.timers 排队到主线程执行 (线程安全)
- 协议: 4 字节大端长度头 + UTF-8 JSON

安装: 将本目录复制到 Blender 的 addons 目录，
      或运行 python scripts/install_addon.py
"""

bl_info = {
    "name": "BlenderUE Bridge",
    "author": "tandu",
    "version": (2, 0, 0),
    "blender": (4, 0, 0),
    "location": "3D View > Sidebar > Bridge",
    "description": "MCP 桥接 TCP 服务器 — AI 驱动的精确建模",
    "category": "Development",
}

import bpy
import bpy.utils

from . import server
from .ui import BRIDGE_PT_Panel

_MODULE_CLASSES = (BRIDGE_PT_Panel,)  # 仅面板 (状态显示; Blender 5.2 operator kwargs 兼容问题)


def register():
    server.ensure_running()
    for cls in _MODULE_CLASSES:
        bpy.utils.register_class(cls)
    print("[Bridge] addon registered, TCP server listening on 127.0.0.1:9876")


def unregister():
    for cls in reversed(_MODULE_CLASSES):
        bpy.utils.unregister_class(cls)
    server.shutdown()
    print("[Bridge] addon unregistered")


if __name__ == "__main__":
    register()
