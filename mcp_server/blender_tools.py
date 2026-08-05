"""分层 Blender 工具 — MCP 注册

工具分层 (LLM 优先使用宏层):
  宏层 (Preferred):   create_wall, create_roof, build_medieval_house ...
  原子层:             create_object, extrude_face, add_modifier ...
  验证层:             measure_*, assert_*, check_mesh_quality
  视觉层:             capture_blender_screenshot

所有工具转发到 blender_addon 执行 (主线程, 线程安全)。
"""

import os
from datetime import datetime

from .blender_client import BlenderClient


def register(mcp, blender: BlenderClient, screenshot_dir: str):
    """注册全部分层工具到 FastMCP"""

    # ═══════════════════════════════════════════════════════
    # 宏层 — 首选
    # ═══════════════════════════════════════════════════════

    @mcp.tool()
    def create_wall(length: float, height: float, thickness: float,
                    openings: list = None, name: str = "Wall",
                    material: dict = None) -> dict:
        """创建墙壁 (带真实门窗洞, 全四边面拓扑)

        Args:
            length: 墙长 (米)
            height: 墙高 (米)
            thickness: 墙厚 (米)
            openings: 开口列表 [{x: 中心X, width: 宽, z_bottom: 底高, z_top: 顶高}]
            material: {base_color, roughness} 可选
        """
        return blender.create_wall(length, height, thickness, openings or [], name, material)

    @mcp.tool()
    def create_floor(length: float, width: float, thickness: float = 0.2,
                     name: str = "Floor", material: dict = None) -> dict:
        """创建地面/楼板"""
        return blender.create_floor(length, width, thickness, name, material)

    @mcp.tool()
    def create_roof(length: float, width: float, height: float,
                    style: str = "gable", eave: float = 0.3,
                    name: str = "Roof", material: dict = None) -> dict:
        """创建屋顶 (真实几何)

        Args:
            length/width: 建筑外廓 (米)
            height: 屋脊高度 (米)
            style: gable(山墙)|hip(四坡)|flat(平顶)|pyramid(锥形)
            eave: 挑檐 (米)
        """
        return blender.create_roof(length, width, height, style, eave, name, material)

    @mcp.tool()
    def create_door(width: float, height: float, thickness: float = 0.06,
                    name: str = "Door", style: str = "plank") -> dict:
        """创建门 (门框+门扇+把手+装饰板)"""
        return blender.create_door(width, height, thickness, name, style)

    @mcp.tool()
    def create_window(width: float, height: float, sill_height: float = 0.9,
                      thickness: float = 0.06, name: str = "Window") -> dict:
        """创建窗 (窗框+玻璃+竖棂+窗台)"""
        return blender.create_window(width, height, sill_height, thickness, name)

    @mcp.tool()
    def create_staircase(width: float, height: float, run: float,
                         steps: int = 12, name: str = "Staircase") -> dict:
        """创建直线楼梯 (单一网格, 全四边面)"""
        return blender.create_staircase(width, height, run, steps, name)

    @mcp.tool()
    def create_table(length: float = 1.8, width: float = 0.9,
                     height: float = 0.75, name: str = "Table") -> dict:
        """创建桌子"""
        return blender.create_table(length, width, height, name)

    @mcp.tool()
    def create_chair(width: float = 0.45, depth: float = 0.45,
                     seat_height: float = 0.45, back_height: float = 0.9,
                     name: str = "Chair") -> dict:
        """创建椅子"""
        return blender.create_chair(width, depth, seat_height, back_height, name)

    @mcp.tool()
    def create_column(height: float = 3.0, radius: float = 0.2,
                      name: str = "Column") -> dict:
        """创建柱子 (柱身+柱头+柱基)"""
        return blender.create_column(height, radius, name)

    @mcp.tool()
    def create_tree(height: float = 4.0, trunk_radius: float = 0.2,
                    canopy_radius: float = 1.2, style: str = "oak",
                    name: str = "Tree") -> dict:
        """创建程序化树

        Args:
            style: oak(橡树球冠)|pine(松树锥层)
        """
        return blender.create_tree(height, trunk_radius, canopy_radius, style, name)

    @mcp.tool()
    def create_rock(radius: float = 0.6, name: str = "Rock") -> dict:
        """创建程序化岩石 (噪波变形)"""
        return blender.create_rock(radius, name)

    @mcp.tool()
    def build_medieval_house(length: float = 6.0, depth: float = 5.0,
                             height: float = 3.0, door: dict = None,
                             windows: list = None, roof_style: str = "gable",
                             name: str = "MedievalHouse") -> dict:
        """构建完整中世纪房屋 (墙面开洞+门+窗+屋顶+烟囱+斜切+材质)

        Args:
            door: {x, width, height} 门口位置
            windows: [{x, width, height, z_bottom}]
        """
        return blender.build_medieval_house(length, depth, height, door, windows,
                                            roof_style, name)

    # ═══════════════════════════════════════════════════════
    # 原子层
    # ═══════════════════════════════════════════════════════

    @mcp.tool()
    def create_blender_object(primitive: str, name: str = "",
                              size: list = None, radius: float = 0.5,
                              depth: float = 1.0, location: list = None,
                              rotation: list = None,
                              material: dict = None) -> dict:
        """创建基础几何体 (精确尺寸, 米)

        Args:
            primitive: cube|sphere|cylinder|cone|plane|torus|monkey|empty
            size: [x,y,z] 米 (cube/plane)
            radius: 半径 (sphere/cylinder/cone)
            depth: 深度 (cylinder/cone)
        """
        return blender.create_object(primitive, name, size, radius, depth,
                                     location, rotation, material)

    @mcp.tool()
    def set_blender_transform(name: str, location: list = None,
                              rotation: list = None, scale: list = None) -> dict:
        """设置对象变换 (精确位置/旋转/缩放)"""
        return blender.set_transform(name, location, rotation, scale)

    @mcp.tool()
    def get_blender_object(name: str) -> dict:
        """获取对象详细信息 (含网格质量报告)"""
        return blender.get_object_info(name)

    @mcp.tool()
    def get_blender_scene() -> dict:
        """获取场景信息 (所有对象 + 网格质量)"""
        return blender.get_scene_info()

    @mcp.tool()
    def duplicate_blender_object(name: str, offset: list = None,
                                 new_name: str = "") -> dict:
        """复制对象"""
        return blender.duplicate_object(name, offset, new_name)

    @mcp.tool()
    def delete_blender_object(names) -> dict:
        """删除对象 (名字或名字列表)"""
        return blender.delete_object(names)

    @mcp.tool()
    def join_blender_objects(names: list, new_name: str = "") -> dict:
        """合并多个对象为一个"""
        return blender.join_objects(names, new_name)

    @mcp.tool()
    def set_blender_origin(name: str, mode: str = "bottom") -> dict:
        """设置对象原点: bottom|center|top"""
        return blender.set_origin(name, mode)

    @mcp.tool()
    def add_blender_modifier(name: str, modifier: str,
                             settings: dict = None) -> dict:
        """添加修改器

        Args:
            modifier: bevel|solidify|subdivision|mirror|array|boolean|screw|skin|wireframe
            settings: {width, segments, thickness, levels, count, ...}
        """
        return blender.add_modifier(name, modifier, settings)

    @mcp.tool()
    def apply_blender_modifier(name: str, modifier: str = "") -> dict:
        """应用修改器 (空=全部应用)"""
        return blender.apply_modifier(name, modifier)

    @mcp.tool()
    def extrude_blender_face(name: str, value: float,
                             face_indices: list = None) -> dict:
        """沿法线挤出面 (真实挤出, 保持拓扑)"""
        return blender.extrude_face(name, value, face_indices)

    @mcp.tool()
    def inset_blender_face(name: str, thickness: float,
                           face_indices: list = None) -> dict:
        """内缩面 (窗框/门框内框)"""
        return blender.inset_face(name, thickness, face_indices)

    @mcp.tool()
    def loop_cut_blender(name: str, axis: str = "x",
                         position: float = None, count: int = 1) -> dict:
        """环切: axis x/y/z, position 0-1 或 count 均分"""
        return blender.loop_cut(name, axis, position, count)

    @mcp.tool()
    def bevel_blender_edges(name: str, width: float = 0.02,
                            segments: int = 1) -> dict:
        """斜切边 (硬边圆润)"""
        return blender.bevel_edges(name, width, segments)

    @mcp.tool()
    def boolean_blender(name: str, object_name: str,
                        operation: str = "difference",
                        apply: bool = True) -> dict:
        """布尔运算: union|difference|intersect"""
        return blender.boolean_operation(name, object_name, operation, apply)

    @mcp.tool()
    def set_blender_material(name: str, material_name: str = "",
                             base_color: list = None, metallic: float = 0.0,
                             roughness: float = 0.5, emission: list = None,
                             emission_strength: float = 0.0) -> dict:
        """设置 PBR 材质"""
        return blender.set_material(name, material_name,
                                    base_color or [0.8, 0.8, 0.8, 1.0],
                                    metallic, roughness,
                                    emission or [0, 0, 0], emission_strength)

    # ═══════════════════════════════════════════════════════
    # 验证层
    # ═══════════════════════════════════════════════════════

    @mcp.tool()
    def measure_distance(a: list = None, b: list = None,
                         object_a: str = "", object_b: str = "") -> dict:
        """测量两点或两对象间距离"""
        if object_a and object_b:
            return blender.measure_distance(object_a=object_a, object_b=object_b)
        return blender.measure_distance(a=a, b=b)

    @mcp.tool()
    def measure_gap(object_a: str, object_b: str) -> dict:
        """测量两对象最近间隙"""
        return blender.measure_gap(object_a, object_b)

    @mcp.tool()
    def measure_alignment(object_a: str, object_b: str, axis: str = "z") -> dict:
        """检查两对象是否对齐 (轴方向偏差)"""
        return blender.measure_alignment(object_a, object_b, axis)

    @mcp.tool()
    def assert_dimensions(name: str, dimensions: list,
                          tolerance: float = 0.01) -> dict:
        """断言对象尺寸符合要求"""
        return blender.assert_dimensions(name, dimensions, tolerance)

    @mcp.tool()
    def assert_contact(object_a: str, object_b: str,
                       tolerance: float = 0.01) -> dict:
        """断言两对象接触/贴合"""
        return blender.assert_contact(object_a, object_b, tolerance)

    @mcp.tool()
    def check_mesh_quality(name: str) -> dict:
        """网格质量检查: 非流形/孤立顶点/零面积面/重复顶点/质量分

        目标: quality_score >= 90
        """
        return blender.check_mesh_quality(name)

    @mcp.tool()
    def check_scene_quality() -> dict:
        """全场景网格质量检查 (平均分 + 最差对象)"""
        return blender.check_scene_quality()

    # ═══════════════════════════════════════════════════════
    # 视觉层
    # ═══════════════════════════════════════════════════════

    @mcp.tool()
    def capture_blender_screenshot(tag: str = "", width: int = 800,
                                   height: int = 600) -> dict:
        """快速截取 Blender 视口 (OpenGL, 毫秒级)"""
        os.makedirs(screenshot_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"blender_{tag}_{ts}.png" if tag else f"blender_{ts}.png"
        filepath = os.path.join(screenshot_dir, fname)
        result = blender.get_screenshot(filepath, width, height)
        if result.get("status") == "success":
            return {"success": True, "filepath": filepath,
                    "width": width, "height": height}
        return {"success": False, "error": result.get("message", "截图失败")}

    @mcp.tool()
    def export_blender_model(object_name: str, format: str = "fbx",
                             export_dir: str = "") -> dict:
        """从 Blender 导出模型 (FBX/GLB) 到共享资产目录

        Args:
            object_name: 对象名 (空 = 整个场景)
            format: fbx|glb
        """
        if not export_dir:
            export_dir = os.path.join(os.path.dirname(screenshot_dir),
                                      "models")
        os.makedirs(export_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "fbx" if format == "fbx" else "glb"
        fname = f"{object_name}_{ts}.{ext}" if object_name else f"scene_{ts}.{ext}"
        filepath = os.path.join(export_dir, fname)
        if format == "fbx":
            return blender.export_fbx(object_name, filepath)
        return blender.export_gltf(object_name, filepath)

    return {
        "create_wall": create_wall, "create_floor": create_floor,
        "create_roof": create_roof, "create_door": create_door,
        "create_window": create_window, "create_staircase": create_staircase,
        "create_table": create_table, "create_chair": create_chair,
        "create_column": create_column, "create_tree": create_tree,
        "create_rock": create_rock,
        "build_medieval_house": build_medieval_house,
    }
