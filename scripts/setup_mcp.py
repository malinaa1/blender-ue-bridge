"""
MCP 配置安装脚本 — 自动配置 Claude Code 的 Blender↔UE Bridge MCP 服务器
"""

import json
import os
import sys


def get_claude_config_path() -> str:
    """获取 Claude 配置文件路径"""
    home = os.path.expanduser("~")
    return os.path.join(home, ".claude", "settings.json")


def get_project_config_path() -> str:
    """获取项目级 Claude 配置路径"""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), ".claude", "settings.json")


def load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  已保存: {path}")


def setup_mcp(target: str = "project"):
    """配置 MCP 服务器"""
    bridge_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_path = os.path.join(bridge_dir, "mcp_server", "server.py")

    mcp_config = {
        "blender-ue-bridge": {
            "command": "python",
            "args": ["-m", "mcp_server.server"],
            "cwd": bridge_dir
        }
    }

    if target == "project":
        config_path = get_project_config_path()
    else:
        config_path = get_claude_config_path()

    config = load_json(config_path)
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    config["mcpServers"].update(mcp_config)
    save_json(config_path, config)

    print(f"\n✅ MCP 配置完成 ({target} 级别)")
    print(f"   服务器: blender-ue-bridge")
    print(f"   命令: python -m mcp_server.server")
    print(f"   工作目录: {bridge_dir}")
    print(f"   配置文件: {config_path}")


def uninstall_mcp(target: str = "project"):
    """移除 MCP 配置"""
    if target == "project":
        config_path = get_project_config_path()
    else:
        config_path = get_claude_config_path()

    config = load_json(config_path)
    if "mcpServers" in config and "blender-ue-bridge" in config["mcpServers"]:
        del config["mcpServers"]["blender-ue-bridge"]
        save_json(config_path, config)
        print(f"\n✅ 已移除 MCP 配置: {config_path}")
    else:
        print(f"\n⚠️ 未找到 blender-ue-bridge 配置")


def test_connection():
    """测试与 Blender 和 UE 的连接"""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from mcp_server.blender_client import BlenderClient
    from mcp_server.ue_client import UEClient

    print("\n🔍 测试 Blender 连接...")
    blender = BlenderClient()
    if blender.check_connection():
        print("  ✅ Blender MCP 连接成功")
        info = blender.get_scene_info()
        if info.get("status") == "success":
            result = info.get("result", {})
            print(f"     场景: {result.get('name', '未知')}")
            print(f"     对象数: {result.get('object_count', 0)}")
    else:
        print("  ❌ Blender MCP 连接失败 — 请确保 Blender 已打开且 MCP 插件已启用")

    print("\n🔍 测试 UE 连接...")
    ue = UEClient()
    if ue.check_connection():
        print("  ✅ UE MCP 连接成功")
    else:
        print("  ❌ UE MCP 连接失败 — 请确保 UE 已打开且 UnrealMCP 插件已启用")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python setup_mcp.py install [project|user]  — 安装 MCP 配置")
        print("  python setup_mcp.py uninstall [project|user] — 移除 MCP 配置")
        print("  python setup_mcp.py test                     — 测试连接")
        sys.exit(0)

    action = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else "project"

    if action == "install":
        setup_mcp(target)
    elif action == "uninstall":
        uninstall_mcp(target)
    elif action == "test":
        test_connection()
    else:
        print(f"未知操作: {action}")
