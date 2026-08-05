"""
Unreal Engine MCP 客户端 — 通过 TCP Socket 与 UE 插件通信

协议: JSON over TCP, 命令格式 {type, params}, 响应格式 {status, result/error}
端口: 55557 (默认)
"""

import socket
import json
import logging

logger = logging.getLogger(__name__)


class UEClient:
    """与 Unreal Engine MCP 插件通信的 TCP 客户端"""

    def __init__(self, host: str = "127.0.0.1", port: int = 55557,
                 timeout: int = 30, large_timeout: int = 300):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.large_timeout = large_timeout

    def send_command(self, command_type: str, params: dict | None = None,
                     large: bool = False) -> dict:
        """向 UE 发送命令并返回响应"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.large_timeout if large else self.timeout)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.connect((self.host, self.port))
            message = json.dumps({
                "type": command_type,
                "params": params or {}
            })
            sock.sendall(message.encode("utf-8"))

            # 读取响应
            response_data = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                response_data += chunk
                try:
                    result = json.loads(response_data.decode("utf-8"))
                    return result
                except json.JSONDecodeError:
                    continue

            return json.loads(response_data.decode("utf-8"))
        except socket.timeout:
            return {"status": "error", "message": f"UE 连接超时 ({self.timeout}s)"}
        except ConnectionRefusedError:
            return {"status": "error", "message": "UE MCP 未运行，请确保 UE 已打开且 UnrealMCP 插件已启用"}
        except Exception as e:
            return {"status": "error", "message": f"UE 通信错误: {e}"}
        finally:
            sock.close()

    # ── Actor 管理 ──────────────────────────────────────────────

    def get_actors(self) -> dict:
        """获取当前关卡中所有 Actor"""
        return self.send_command("get_actors_in_level")

    def find_actors(self, name_pattern: str) -> dict:
        """按名称搜索 Actor"""
        return self.send_command("find_actors_by_name", {"name": name_pattern})

    def delete_actor(self, actor_name: str) -> dict:
        """删除指定 Actor"""
        return self.send_command("delete_actor", {"actor_name": actor_name})

    def set_transform(self, actor_name: str, location=None, rotation=None,
                      scale=None) -> dict:
        """设置 Actor 变换"""
        params = {"actor_name": actor_name}
        if location:
            params["location"] = list(location)
        if rotation:
            params["rotation"] = list(rotation)
        if scale:
            params["scale"] = list(scale)
        return self.send_command("set_actor_transform", params)

    # ── 资产导入 ──────────────────────────────────────────────

    def import_asset(self, file_path: str, destination: str = "/Game/Assets/") -> dict:
        """导入资产文件（FBX/glTF 等）到 UE 项目"""
        return self.send_command("import_asset", {
            "file_path": file_path,
            "destination": destination
        })

    def spawn_actor(self, actor_class: str, actor_name: str = "",
                    location=None, rotation=None, scale=None,
                    static_mesh: str = "") -> dict:
        """在场景中生成 Actor

        Args:
            actor_class: Actor 类型 (StaticMeshActor, PointLight, SpotLight, etc.)
            actor_name: Actor 名称
            location: 位置 [x, y, z]
            rotation: 旋转 [pitch, yaw, roll]
            scale: 缩放 [x, y, z]
            static_mesh: 静态网格路径 (如 /Game/Meshes/MyMesh)
        """
        params = {"type": actor_class, "name": actor_name or actor_class}
        if location:
            params["location"] = list(location)
        if rotation:
            params["rotation"] = list(rotation)
        if scale:
            params["scale"] = list(scale)
        if static_mesh:
            params["static_mesh"] = static_mesh
        return self.send_command("spawn_actor", params)

    # ── 材质 ──────────────────────────────────────────────────

    def get_materials(self) -> dict:
        """获取项目中可用的材质列表"""
        return self.send_command("get_available_materials")

    def apply_material(self, actor_name: str, material_path: str) -> dict:
        """为 Actor 应用材质"""
        return self.send_command("apply_material_to_actor", {
            "actor_name": actor_name,
            "material_path": material_path
        })

    def set_material_color(self, actor_name: str, r: float, g: float,
                           b: float, a: float = 1.0) -> dict:
        """设置 Actor 材质颜色"""
        return self.send_command("set_mesh_material_color", {
            "actor_name": actor_name,
            "r": r, "g": g, "b": b, "a": a
        })

    def get_actor_material_info(self, actor_name: str) -> dict:
        """获取 Actor 的材质信息"""
        return self.send_command("get_actor_material_info", {
            "actor_name": actor_name
        })

    # ── Blueprint ─────────────────────────────────────────────

    def create_blueprint(self, blueprint_name: str, parent_class: str = "Actor") -> dict:
        """创建新的 Blueprint 类"""
        return self.send_command("create_blueprint", {
            "blueprint_name": blueprint_name,
            "parent_class": parent_class
        })

    def add_component(self, blueprint_name: str, component_type: str,
                      component_name: str, **kwargs) -> dict:
        """为 Blueprint 添加组件"""
        params = {
            "blueprint_name": blueprint_name,
            "component_type": component_type,
            "component_name": component_name
        }
        params.update(kwargs)
        return self.send_command("add_component_to_blueprint", params)

    def compile_blueprint(self, blueprint_name: str) -> dict:
        """编译 Blueprint"""
        return self.send_command("compile_blueprint", {
            "blueprint_name": blueprint_name
        })

    # ── 场景构建 ──────────────────────────────────────────────

    def create_town(self, **kwargs) -> dict:
        """生成完整城镇（大型操作）"""
        return self.send_command("create_town", kwargs, large=True)

    def create_castle(self, **kwargs) -> dict:
        """生成城堡（大型操作）"""
        return self.send_command("create_castle_fortress", kwargs, large=True)

    def create_maze(self, **kwargs) -> dict:
        """生成迷宫"""
        return self.send_command("create_maze", kwargs, large=True)

    # ── 蓝图节点图 ────────────────────────────────────────────

    def add_blueprint_node(self, blueprint_name: str, node_type: str,
                           **kwargs) -> dict:
        """在蓝图中添加节点"""
        params = {
            "blueprint_name": blueprint_name,
            "node_type": node_type
        }
        params.update(kwargs)
        return self.send_command("add_node", params)

    def connect_blueprint_nodes(self, blueprint_name: str, from_node: str,
                                from_pin: str, to_node: str, to_pin: str) -> dict:
        """连接蓝图节点"""
        return self.send_command("connect_nodes", {
            "blueprint_name": blueprint_name,
            "from_node": from_node,
            "from_pin": from_pin,
            "to_node": to_node,
            "to_pin": to_pin
        })

    def create_blueprint_variable(self, blueprint_name: str, var_name: str,
                                   var_type: str = "Boolean", **kwargs) -> dict:
        """在蓝图中创建变量"""
        params = {
            "blueprint_name": blueprint_name,
            "variable_name": var_name,
            "variable_type": var_type
        }
        params.update(kwargs)
        return self.send_command("create_variable", params)

    # ── 工具 ──────────────────────────────────────────────────

    def check_connection(self) -> bool:
        """检查 UE MCP 是否可达"""
        result = self.get_actors()
        return "error" not in str(result).lower() and "not running" not in str(result).lower()
