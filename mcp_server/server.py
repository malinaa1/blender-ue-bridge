"""
Blender↔UE 桥接 MCP 服务器 v2

通过 MCP 协议将 Blender 和 Unreal Engine 统一到一个 AI 可控的接口中。
v2 特性:
- Blender: 分层工具 (宏层优先) + 网格质量检查 + 测量验证 + 快速截图 + 专家提示词
- UE: 结构化 Actor/Blueprint/材质操作
- 线程安全 addon 通信 (长度前缀协议 + 轮询)
"""

import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from .blender_client import BlenderClient
from .ue_client import UEClient
from .asset_pipeline import AssetPipeline
from .vision_feedback import VisionFeedback
from . import blender_tools, prompts

# ── 路径 ────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
LOG_PATH = os.path.join(PROJECT_ROOT, "bridge.log")
SHARED_DIR = os.path.join(PROJECT_ROOT, "shared_assets")

# ── 日志配置 ────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger("BlenderUEBridge")


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = {}
    # 环境变量覆盖 (多项目支持)
    env_ue_content = os.environ.get("UE_CONTENT_DIR")
    if env_ue_content:
        cfg.setdefault("unreal", {})["content_dir"] = env_ue_content
    env_shared = os.environ.get("BRIDGE_SHARED_DIR")
    if env_shared:
        cfg.setdefault("shared_assets", {})["base_dir"] = env_shared
    return cfg


config = load_config()

# 共享目录 (相对项目根, 可被环境变量覆盖)
shared_base = config.get("shared_assets", {}).get("base_dir", "") or SHARED_DIR
screenshot_dir = os.path.join(shared_base, "screenshots")

# ── 客户端初始化 ────────────────────────────────────────────

blender = BlenderClient(
    host=config.get("blender", {}).get("host", "127.0.0.1"),
    port=config.get("blender", {}).get("port", 9876),
    timeout=config.get("blender", {}).get("timeout", 30),
)

ue = UEClient(
    host=config.get("unreal", {}).get("host", "127.0.0.1"),
    port=config.get("unreal", {}).get("port", 55557),
    timeout=config.get("unreal", {}).get("timeout", 30),
    large_timeout=config.get("unreal", {}).get("large_timeout", 300),
)

pipeline = AssetPipeline(blender=blender, ue=ue, shared_dir=shared_base)

vision = VisionFeedback(blender=blender, ue=ue, screenshot_dir=screenshot_dir)

# ── MCP 服务器 ──────────────────────────────────────────────

mcp = FastMCP("BlenderUEBridge")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 连接与状态
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
def bridge_status() -> dict:
    """检查 Blender 和 Unreal Engine 的连接状态"""
    blender_ok = blender.check_connection()
    ue_ok = ue.check_connection()
    return {
        "blender": {"connected": blender_ok, "host": blender.host, "port": blender.port},
        "unreal": {"connected": ue_ok, "host": ue.host, "port": ue.port},
        "both_ready": blender_ok and ue_ok,
    }


@mcp.tool()
def get_both_scenes() -> dict:
    """同时获取 Blender 和 UE 的场景信息"""
    blender_scene = blender.get_scene_info()
    ue_actors = ue.get_actors()
    return {"blender": blender_scene, "unreal": ue_actors}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Blender — 分层工具 + 专家提示词 (blender_tools.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

blender_tools.register(mcp, blender, screenshot_dir)
prompts.register_prompts(mcp)


@mcp.tool()
def execute_blender_code(code: str) -> dict:
    """执行任意 Blender Python 代码 — 逃生通道 (仅在宏/原子工具不足时使用)"""
    return blender.execute_code(code)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 资产传输
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
def transfer_model(object_name: str, ue_destination: str = "/Game/Assets/",
                   format: str = "fbx", bake_textures: bool = True,
                   texture_resolution: int = 2048) -> dict:
    """将 Blender 中的模型传输到 Unreal Engine (导出 → 烘焙 → 导入)

    Args:
        object_name: Blender 中的对象名称
        ue_destination: UE 中的目标路径 (如 /Game/Assets/Characters/)
        format: 导出格式 (fbx / glb)
        bake_textures: 是否烘焙材质纹理为 PNG
        texture_resolution: 烘焙纹理分辨率 (512/1024/2048/4096)
    """
    return pipeline.transfer_model(
        object_name, ue_destination, format, bake_textures, texture_resolution
    )


@mcp.tool()
def transfer_scene(ue_destination: str = "/Game/Assets/") -> dict:
    """将整个 Blender 场景导出并导入 UE"""
    return pipeline.transfer_all(ue_destination)


@mcp.tool()
def batch_transfer_models(object_names: list, ue_destination: str = "/Game/Assets/",
                          format: str = "fbx") -> dict:
    """批量传输多个 Blender 对象到 UE"""
    return pipeline.batch_transfer(object_names, ue_destination, format)


@mcp.tool()
def sync_material(object_name: str, ue_actor_name: str = "",
                  texture_resolution: int = 2048) -> dict:
    """同步 Blender 对象的材质到 UE (烘焙纹理)"""
    return pipeline.sync_material(object_name, ue_actor_name, texture_resolution)


@mcp.tool()
def list_shared_assets() -> dict:
    """列出共享资产目录中的所有文件"""
    return pipeline.list_shared_assets()


@mcp.tool()
def cleanup_shared_assets(max_age_hours: int = 24) -> dict:
    """清理超过指定时间的共享资产文件"""
    return pipeline.cleanup_shared(max_age_hours)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Unreal Engine 操作
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
def execute_ue_command(command_type: str, params: dict = None) -> dict:
    """向 Unreal Engine 发送自定义命令"""
    return ue.send_command(command_type, params)


@mcp.tool()
def get_ue_actors() -> dict:
    """获取 UE 当前关卡中的所有 Actor"""
    return ue.get_actors()


@mcp.tool()
def spawn_ue_actor(actor_class: str, actor_name: str = "",
                   location: list = None, rotation: list = None,
                   scale: list = None, static_mesh: str = "") -> dict:
    """在 UE 场景中生成 Actor

    Args:
        actor_class: StaticMeshActor, PointLight, DirectionalLight, etc.
        static_mesh: 静态网格路径 (如 /Game/Assets/MyMesh)
    """
    return ue.spawn_actor(actor_class, actor_name, location, rotation, scale,
                          static_mesh)


@mcp.tool()
def set_ue_actor_transform(actor_name: str, location: list = None,
                           rotation: list = None, scale: list = None) -> dict:
    """设置 UE Actor 的变换"""
    return ue.set_transform(actor_name, location, rotation, scale)


@mcp.tool()
def delete_ue_actor(actor_name: str) -> dict:
    """删除 UE 中的指定 Actor"""
    return ue.delete_actor(actor_name)


@mcp.tool()
def create_ue_blueprint(blueprint_name: str, parent_class: str = "Actor") -> dict:
    """在 UE 中创建新的 Blueprint 类"""
    return ue.create_blueprint(blueprint_name, parent_class)


@mcp.tool()
def add_ue_blueprint_component(blueprint_name: str, component_type: str,
                               component_name: str, **kwargs) -> dict:
    """为 Blueprint 添加组件 (StaticMesh/PointLight/BoxCollision 等)"""
    return ue.add_component(blueprint_name, component_type, component_name, **kwargs)


@mcp.tool()
def add_ue_blueprint_variable(blueprint_name: str, variable_name: str,
                              variable_type: str = "Boolean",
                              default_value=None) -> dict:
    """在 Blueprint 中创建变量"""
    kwargs = {}
    if default_value is not None:
        kwargs["default_value"] = default_value
    return ue.create_blueprint_variable(blueprint_name, variable_name,
                                        variable_type, **kwargs)


@mcp.tool()
def compile_ue_blueprint(blueprint_name: str) -> dict:
    """编译 UE Blueprint"""
    return ue.compile_blueprint(blueprint_name)


@mcp.tool()
def get_ue_materials() -> dict:
    """获取 UE 项目中可用的材质列表"""
    return ue.get_materials()


@mcp.tool()
def apply_ue_material(actor_name: str, material_path: str) -> dict:
    """为 UE Actor 应用材质"""
    return ue.apply_material(actor_name, material_path)


@mcp.tool()
def set_ue_material_color(actor_name: str, r: float, g: float, b: float,
                          a: float = 1.0) -> dict:
    """设置 UE Actor 材质颜色"""
    return ue.set_material_color(actor_name, r, g, b, a)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UE 场景构建（高级操作）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
def create_ue_town(name: str = "AITown", building_count: int = 10) -> dict:
    """在 UE 中生成一个完整城镇"""
    return ue.create_town(name=name, building_count=building_count)


@mcp.tool()
def create_ue_castle(name: str = "AICastle", style: str = "medieval") -> dict:
    """在 UE 中生成城堡"""
    return ue.create_castle(name=name, style=style)


@mcp.tool()
def create_ue_maze(width: int = 10, height: int = 10) -> dict:
    """在 UE 中生成迷宫"""
    return ue.create_maze(width=width, height=height)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 视觉反馈
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
def compare_engine_scenes() -> dict:
    """对比 Blender 和 UE 两个引擎的场景状态"""
    return vision.compare_scenes()


# ── 启动 ────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("启动 Blender↔UE 桥接 MCP 服务器 v2 (stdio)")
    mcp.run(transport="stdio")
