"""3D View Sidebar 面板 — 显示服务器状态 + 一键启停"""

import bpy


class BRIDGE_PT_Panel(bpy.types.Panel):
    bl_label = "BlenderUE Bridge"
    bl_idname = "BRIDGE_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Bridge"

    def draw(self, context):
        layout = self.layout
        from . import server
        if server._server_sock is not None:
            row = layout.row()
            row.label(text="● 服务器运行中", icon="CHECKMARK")
            row = layout.row()
            row.label(text=f"127.0.0.1:{server.PORT}")
        else:
            layout.label(text="○ 服务器未运行", icon="ERROR")
        op = layout.operator("bridge.toggle_server")
        op.text = "停止服务器" if server._server_sock is not None else "启动服务器"


class BRIDGE_OT_ToggleServer(bpy.types.Operator):
    bl_idname = "bridge.toggle_server"
    bl_label = "Toggle Bridge Server"
    bl_description = "启动或停止 MCP 桥接服务器"

    def execute(self, context):
        from . import server
        if server._server_sock is not None:
            server.shutdown()
        else:
            server.ensure_running()
        return {"FINISHED"}


CLASSES = (BRIDGE_OT_ToggleServer, BRIDGE_PT_Panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
