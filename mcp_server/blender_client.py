"""
Blender MCP 客户端 — 与 blender_addon 插件通信

协议: 4 字节大端长度头 + UTF-8 JSON
命令: {type, params} → {status: queued, result: {id}} → 轮询 {type: poll_result, params: {id}}
大操作: params.large=true → 直接回写结果 (保持连接)
端口: 9876
"""

import socket
import json
import struct
import logging
import time

logger = logging.getLogger(__name__)

HEADER = struct.Struct(">I")
MAX_MESSAGE = 64 * 1024 * 1024


class BlenderClient:
    """与 Blender Addon 通信的 TCP 客户端"""

    def __init__(self, host: str = "127.0.0.1", port: int = 9876,
                 timeout: int = 30, poll_interval: float = 0.02):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.poll_interval = poll_interval

    # ── 传输层 ──────────────────────────────────────────────

    def _connect(self, timeout: float):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((self.host, self.port))
        return sock

    @staticmethod
    def _send(sock, data: dict):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        sock.sendall(HEADER.pack(len(payload)) + payload)

    @staticmethod
    def _recv(sock) -> dict:
        buf = b""
        while len(buf) < HEADER.size:
            chunk = sock.recv(HEADER.size - len(buf))
            if not chunk:
                raise ConnectionError("连接被关闭")
            buf += chunk
        (length,) = HEADER.unpack(buf)
        if length > MAX_MESSAGE:
            raise ValueError(f"消息过大: {length} bytes")
        buf = b""
        while len(buf) < length:
            chunk = sock.recv(length - len(buf))
            if not chunk:
                raise ConnectionError("连接被关闭")
            buf += chunk
        return json.loads(buf.decode("utf-8"))

    def send_command(self, command_type: str, params: dict | None = None,
                     large: bool = False, retries: int = 1) -> dict:
        """发送命令并等待结果

        large=True 时直接回写; 否则入队后轮询结果。
        连接失败重试 retries 次 (addon 可能刚启动)。
        """
        last_error = None
        for attempt in range(retries + 1):
            sock = None
            try:
                sock = self._connect(self.timeout if not large else 300)
                self._send(sock, {"type": command_type, "params": params or {},
                                  "large": large})
                if large:
                    return self._recv(sock)
                # 常规: 等排号 → 轮询结果
                resp = self._recv(sock)
                if resp.get("status") == "queued":
                    cmd_id = resp.get("result", {}).get("id")
                    return self._poll(cmd_id)
                return resp
            except (ConnectionRefusedError, ConnectionError, OSError) as e:
                last_error = e
                if attempt < retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
            finally:
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass
        return {"status": "error", "message": f"Blender 连接失败: {last_error}"}

    def _poll(self, cmd_id: int, max_wait: float = 60.0) -> dict:
        """轮询命令结果 (addon 在主线程执行)"""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                sock = self._connect(self.timeout)
                self._send(sock, {"type": "poll_result", "params": {"id": cmd_id}})
                resp = self._recv(sock)
                sock.close()
                if resp.get("status") == "pending":
                    time.sleep(self.poll_interval)
                    continue
                return resp
            except (ConnectionRefusedError, ConnectionError, OSError):
                time.sleep(0.2)
        return {"status": "error", "message": f"命令 {cmd_id} 等待超时"}

    def ping(self) -> bool:
        resp = self.send_command("ping")
        return resp.get("status") == "success"

    def check_connection(self) -> bool:
        return self.ping()

    # ── 场景 / 对象 ─────────────────────────────────────────

    def get_scene_info(self) -> dict:
        return self.send_command("scene_info")

    def list_objects(self) -> dict:
        return self.send_command("list_objects")

    def get_object_info(self, name: str) -> dict:
        return self.send_command("object_info", {"name": name})

    def create_object(self, primitive: str, name: str = "",
                      size=None, radius: float = 0.5, depth: float = 1.0,
                      location=None, rotation=None, material: dict | None = None) -> dict:
        params = {"type": primitive, "size": size or [1, 1, 1],
                  "radius": radius, "depth": depth}
        if name:
            params["name"] = name
        if location:
            params["location"] = list(location)
        if rotation:
            params["rotation"] = list(rotation)
        if material:
            params["material"] = material
        return self.send_command("create_object", params)

    # ── 变换 ────────────────────────────────────────────────

    def set_transform(self, name: str, location=None, rotation=None, scale=None) -> dict:
        params = {"name": name}
        if location:
            params["location"] = list(location)
        if rotation:
            params["rotation"] = list(rotation)
        if scale:
            params["scale"] = list(scale)
        return self.send_command("set_transform", params)

    def get_transform(self, name: str) -> dict:
        return self.send_command("get_transform", {"name": name})

    def apply_transform(self, name: str) -> dict:
        return self.send_command("apply_transform", {"name": name})

    def set_origin(self, name: str, mode: str = "bottom") -> dict:
        return self.send_command("set_origin", {"name": name, "mode": mode})

    # ── 对象操作 ────────────────────────────────────────────

    def duplicate_object(self, name: str, offset=None, new_name: str = "") -> dict:
        params = {"name": name}
        if offset:
            params["offset"] = list(offset)
        if new_name:
            params["new_name"] = new_name
        return self.send_command("duplicate_object", params)

    def delete_object(self, names) -> dict:
        if isinstance(names, str):
            names = [names]
        return self.send_command("delete_object", {"names": names})

    def join_objects(self, names, new_name: str = "") -> dict:
        params = {"names": names}
        if new_name:
            params["new_name"] = new_name
        return self.send_command("join_objects", params)

    def parent_object(self, child: str, parent: str) -> dict:
        return self.send_command("parent_object", {"child": child, "parent": parent})

    # ── 修改器 ──────────────────────────────────────────────

    def add_modifier(self, name: str, modifier: str, settings: dict | None = None,
                     modifier_name: str = "") -> dict:
        params = {"name": name, "modifier": modifier, "settings": settings or {}}
        if modifier_name:
            params["modifier_name"] = modifier_name
        return self.send_command("add_modifier", params)

    def apply_modifier(self, name: str, modifier: str = "") -> dict:
        params = {"name": name}
        if modifier:
            params["modifier"] = modifier
        return self.send_command("apply_modifier", params)

    def remove_modifier(self, name: str, modifier: str) -> dict:
        return self.send_command("remove_modifier", {"name": name, "modifier": modifier})

    # ── 网格编辑 ────────────────────────────────────────────

    def extrude_face(self, name: str, value: float, face_indices=None) -> dict:
        params = {"name": name, "value": value}
        if face_indices:
            params["face_indices"] = list(face_indices)
        return self.send_command("extrude_face", params)

    def inset_face(self, name: str, thickness: float, face_indices=None) -> dict:
        params = {"name": name, "thickness": thickness}
        if face_indices:
            params["face_indices"] = list(face_indices)
        return self.send_command("inset_face", params)

    def loop_cut(self, name: str, axis: str = "x", position: float = None,
                 count: int = 1) -> dict:
        params = {"name": name, "axis": axis, "count": count}
        if position is not None:
            params["position"] = position
        return self.send_command("loop_cut", params)

    def bevel_edges(self, name: str, width: float = 0.02, segments: int = 1) -> dict:
        return self.send_command("bevel_edges", {"name": name, "width": width,
                                                 "segments": segments})

    def subdivide_edges(self, name: str, cuts: int = 1) -> dict:
        return self.send_command("subdivide_edges", {"name": name, "cuts": cuts})

    def bridge_edge_loops(self, name: str, a=None, b=None) -> dict:
        params = {"name": name}
        if a:
            params["a"] = list(a)
        if b:
            params["b"] = list(b)
        return self.send_command("bridge_edge_loops", params)

    def boolean_operation(self, name: str, object_name: str,
                          operation: str = "difference",
                          apply: bool = True, cleanup_tool: bool = True) -> dict:
        return self.send_command("boolean_operation", {
            "name": name, "object": object_name, "operation": operation,
            "apply": apply, "cleanup_tool": cleanup_tool})

    # ── 材质 ────────────────────────────────────────────────

    def set_material(self, name: str, material_name: str = "",
                     base_color=(0.8, 0.8, 0.8, 1.0), metallic: float = 0.0,
                     roughness: float = 0.5, emission=(0, 0, 0),
                     emission_strength: float = 0.0) -> dict:
        return self.send_command("set_material", {
            "name": name, "material_name": material_name or f"{name}_mat",
            "base_color": list(base_color), "metallic": metallic,
            "roughness": roughness, "emission": list(emission),
            "emission_strength": emission_strength})

    def assign_material(self, name: str, material: str) -> dict:
        return self.send_command("assign_material", {"name": name, "material": material})

    def list_materials(self) -> dict:
        return self.send_command("list_materials")

    # ── 测量 / 验证 ─────────────────────────────────────────

    def measure_distance(self, a=None, b=None, object_a=None, object_b=None) -> dict:
        params = {}
        if a and b:
            params.update(a=list(a), b=list(b))
        if object_a and object_b:
            params.update(object_a=object_a, object_b=object_b)
        return self.send_command("measure_distance", params)

    def measure_dimensions(self, name: str) -> dict:
        return self.send_command("measure_dimensions", {"name": name})

    def measure_gap(self, object_a: str, object_b: str) -> dict:
        return self.send_command("measure_gap", {"object_a": object_a, "object_b": object_b})

    def measure_alignment(self, object_a: str, object_b: str, axis: str = "z",
                          tolerance: float = 0.01) -> dict:
        return self.send_command("measure_alignment", {
            "object_a": object_a, "object_b": object_b,
            "axis": axis, "tolerance": tolerance})

    def assert_dimensions(self, name: str, dimensions, tolerance: float = 0.01) -> dict:
        return self.send_command("assert_dimensions", {
            "name": name, "dimensions": list(dimensions), "tolerance": tolerance})

    def assert_contact(self, object_a: str, object_b: str, tolerance: float = 0.01) -> dict:
        return self.send_command("assert_contact", {
            "object_a": object_a, "object_b": object_b, "tolerance": tolerance})

    def check_mesh_quality(self, name: str) -> dict:
        return self.send_command("check_mesh_quality", {"name": name})

    def check_scene_quality(self) -> dict:
        return self.send_command("check_scene_quality")

    # ── 截图 ────────────────────────────────────────────────

    def get_screenshot(self, filepath: str, width: int = 800, height: int = 600) -> dict:
        return self.send_command("capture_viewport", {
            "filepath": filepath, "width": width, "height": height})

    # ── 宏 ──────────────────────────────────────────────────

    def create_wall(self, length: float, height: float, thickness: float,
                    openings=None, name: str = "Wall", material=None) -> dict:
        return self.send_command("create_wall", {
            "length": length, "height": height, "thickness": thickness,
            "openings": openings or [], "name": name, "material": material})

    def create_floor(self, length: float, width: float, thickness: float = 0.2,
                     name: str = "Floor", material=None) -> dict:
        return self.send_command("create_floor", {
            "length": length, "width": width, "thickness": thickness,
            "name": name, "material": material})

    def create_roof(self, length: float, width: float, height: float,
                    style: str = "gable", eave: float = 0.3,
                    name: str = "Roof", material=None) -> dict:
        return self.send_command("create_roof", {
            "length": length, "width": width, "height": height,
            "style": style, "eave": eave, "name": name, "material": material})

    def create_door(self, width: float, height: float, thickness: float = 0.06,
                    name: str = "Door", style: str = "plank",
                    base_color=None) -> dict:
        return self.send_command("create_door", {
            "width": width, "height": height, "thickness": thickness,
            "name": name, "style": style,
            "base_color": list(base_color) if base_color else None})

    def create_window(self, width: float, height: float, sill_height: float = 0.9,
                      thickness: float = 0.06, name: str = "Window",
                      base_color=None) -> dict:
        return self.send_command("create_window", {
            "width": width, "height": height, "sill_height": sill_height,
            "thickness": thickness, "name": name,
            "base_color": list(base_color) if base_color else None})

    def create_staircase(self, width: float, height: float, run: float,
                         steps: int = 12, name: str = "Staircase") -> dict:
        return self.send_command("create_staircase", {
            "width": width, "height": height, "run": run,
            "steps": steps, "name": name})

    def create_table(self, length: float = 1.8, width: float = 0.9,
                     height: float = 0.75, name: str = "Table") -> dict:
        return self.send_command("create_table", {
            "length": length, "width": width, "height": height, "name": name})

    def create_chair(self, width: float = 0.45, depth: float = 0.45,
                     seat_height: float = 0.45, back_height: float = 0.9,
                     name: str = "Chair") -> dict:
        return self.send_command("create_chair", {
            "width": width, "depth": depth, "seat_height": seat_height,
            "back_height": back_height, "name": name})

    def create_crate(self, length: float = 0.6, width: float = 0.6,
                     height: float = 0.5, name: str = "Crate") -> dict:
        return self.send_command("create_crate", {
            "length": length, "width": width, "height": height, "name": name})

    def create_column(self, height: float = 3.0, radius: float = 0.2,
                      name: str = "Column") -> dict:
        return self.send_command("create_column", {
            "height": height, "radius": radius, "name": name})

    def create_tree(self, height: float = 4.0, trunk_radius: float = 0.2,
                    canopy_radius: float = 1.2, style: str = "oak",
                    name: str = "Tree", seed: int = 42) -> dict:
        return self.send_command("create_tree", {
            "height": height, "trunk_radius": trunk_radius,
            "canopy_radius": canopy_radius, "style": style,
            "name": name, "seed": seed})

    def create_rock(self, radius: float = 0.6, name: str = "Rock",
                    seed: int = 0) -> dict:
        return self.send_command("create_rock", {
            "radius": radius, "name": name, "seed": seed})

    def build_medieval_house(self, length: float = 6.0, depth: float = 5.0,
                             height: float = 3.0, door=None, windows=None,
                             roof_style: str = "gable", name: str = "MedievalHouse") -> dict:
        params = {"length": length, "depth": depth, "height": height,
                  "roof_style": roof_style, "name": name}
        if door:
            params["door"] = door
        if windows:
            params["windows"] = windows
        return self.send_command("build_medieval_house", params)

    # ── 导出 (大操作) ───────────────────────────────────────

    def export_fbx(self, object_name: str, export_path: str,
                   use_triangles: bool = False) -> dict:
        return self.send_command("export_fbx", {
            "object_name": object_name, "filepath": export_path,
            "use_triangles": use_triangles}, large=True)

    def bake_textures(self, object_name: str, output_dir: str,
                      resolution: int = 2048, channels=None) -> dict:
        """烘焙材质纹理 (Cycles)"""
        params = {"name": object_name, "output_dir": output_dir,
                  "resolution": resolution}
        if channels:
            params["channels"] = channels
        return self.send_command("bake_textures", params, large=True)

    def export_gltf(self, object_name: str, export_path: str) -> dict:
        return self.send_command("export_gltf", {
            "object_name": object_name, "filepath": export_path}, large=True)

    # ── 兼容旧接口 ──────────────────────────────────────────

    def execute_code(self, code: str) -> dict:
        """执行 Blender Python 代码 (逃生通道, 不推荐)"""
        return self.send_command("execute_code", {"code": code})
