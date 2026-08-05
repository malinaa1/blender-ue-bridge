"""原子命令处理器 — 精确、可验证、无裸代码生成

所有 handler 签名: def handler(params: dict) -> dict
在主线程 (bpy.app.timers) 中执行, 大操作在专用线程 (需持有 bpy 数据锁)。

返回约定: {"status": "success"|"error", "result": {...} | "message": ...}
本模块返回 result dict 或抛异常; server._dispatch 负责包装 status。
"""

import math
import os

import bpy
from mathutils import Vector, Matrix


# ─────────────────────────────────────────────────────────────
# 辅助
# ─────────────────────────────────────────────────────────────

def _get_object(name):
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"对象不存在: {name}")
    return obj


def _vec3(v, default=(0.0, 0.0, 0.0)):
    if v is None:
        return Vector(default)
    v = list(v)
    while len(v) < 3:
        v.append(0.0)
    return Vector(v[:3])


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _deselect_all():
    bpy.ops.object.select_all(action="DESELECT")


def _select_only(obj):
    _deselect_all()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _mesh_quality_report(obj):
    """返回网格质量报告 (主线程执行)"""
    mesh = obj.data
    bm = obj.data  # 使用 bmesh 更准确
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    try:
        non_manifold = [e for e in bm.edges if not e.is_manifold]
        loose_verts = [v for v in bm.verts if not v.link_edges]
        zero_area = [f for f in bm.faces if abs(f.calc_area()) < 1e-9]
        duplicate_verts = 0
        seen = set()
        for v in bm.verts:
            key = (round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5))
            if key in seen:
                duplicate_verts += 1
            seen.add(key)
        tri_faces = sum(1 for f in bm.faces if len(f.verts) == 3)
        quad_faces = sum(1 for f in bm.faces if len(f.verts) == 4)
        n_edges = len(bm.edges)
        total_faces = len(bm.faces)

        issues = []
        if non_manifold:
            issues.append(f"{len(non_manifold)} 条非流形边")
        if loose_verts:
            issues.append(f"{len(loose_verts)} 个孤立顶点")
        if zero_area:
            issues.append(f"{len(zero_area)} 个零面积面")
        if duplicate_verts:
            issues.append(f"{len(duplicate_verts)} 个重复顶点")

        quad_ratio = quad_faces / total_faces if total_faces else 1.0
        # 生产就绪度评分
        score = 100
        score -= len(non_manifold) * 5
        score -= len(loose_verts) * 3
        score -= len(zero_area) * 8
        score -= duplicate_verts * 2
        if total_faces and tri_faces / total_faces > 0.5:
            score -= 15  # 三角形过多
        score = _clamp(score, 0, 100)

        return {
            "vertices": len(bm.verts),
            "edges": n_edges,
            "faces": total_faces,
            "tri_faces": tri_faces,
            "quad_faces": quad_faces,
            "quad_ratio": round(quad_ratio, 3),
            "non_manifold_edges": len(non_manifold),
            "loose_vertices": len(loose_verts),
            "zero_area_faces": len(zero_area),
            "duplicate_vertices": duplicate_verts,
            "issues": issues,
            "quality_score": score,
        }
    finally:
        bm.free()


def _list_materials(obj):
    return [m.name for m in obj.data.materials] if obj.data.materials else []


def _set_pbr_material(obj, name, base_color=(0.8, 0.8, 0.8, 1.0),
                      metallic=0.0, roughness=0.5, emission=(0, 0, 0),
                      emission_strength=0.0):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = tuple(base_color)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
        if emission_strength > 0:
            bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return mat


# ─────────────────────────────────────────────────────────────
# 场景 / 对象信息
# ─────────────────────────────────────────────────────────────

def scene_info(params):
    scene = bpy.context.scene
    objects = []
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            objects.append({
                "name": obj.name,
                "type": obj.type,
                "location": list(obj.location),
                "mesh": _mesh_quality_report(obj) if obj.data else None,
            })
        else:
            objects.append({
                "name": obj.name,
                "type": obj.type,
                "location": list(obj.location),
            })
    return {
        "name": scene.name,
        "object_count": len(bpy.data.objects),
        "objects": objects,
        "units": scene.unit_settings.length_unit,
        "frame": scene.frame_current,
    }


def list_objects(params):
    objs = []
    for obj in bpy.data.objects:
        objs.append({
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
        })
    return {"objects": objs, "count": len(objs)}


def object_info(params):
    obj = _get_object(params["name"])
    info = {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "parent": obj.parent.name if obj.parent else None,
        "materials": _list_materials(obj),
        "visible": obj.visible_get(),
    }
    if obj.type == "MESH":
        info["dimensions"] = list(obj.dimensions)
        info["quality"] = _mesh_quality_report(obj)
    return info


# ─────────────────────────────────────────────────────────────
# 精确创建
# ─────────────────────────────────────────────────────────────

_PRIMITIVES = {
    "cube": "primitive_cube_add",
    "sphere": "primitive_uv_sphere_add",
    "cylinder": "primitive_cylinder_add",
    "cone": "primitive_cone_add",
    "plane": "primitive_plane_add",
    "torus": "primitive_torus_add",
    "monkey": "primitive_monkey_add",
    "circle": "primitive_circle_add",
    "empty": None,
}


def create_object(params):
    """按真实尺寸 (米) 创建对象 — 精确定位原点在底面中心

    params:
        type: cube|sphere|cylinder|cone|plane|torus|monkey|empty
        name: 可选
        size: 总体尺寸 [x, y, z] (米) — cube/plane/empty 用
        radius: 半径 (米) — sphere/cylinder/cone/torus 用
        depth: 深度 (米) — cylinder/cone 用
        location: [x, y, z]
        rotation: [rx, ry, rz] 弧度 (可选)
        material: dict 可选 PBR 参数
    """
    ptype = params.get("type", "cube")
    name = params.get("name", "")
    location = _vec3(params.get("location"))
    rotation = _vec3(params.get("rotation"))
    size = params.get("size") or [1.0, 1.0, 1.0]
    radius = params.get("radius", 0.5)
    depth = params.get("depth", 1.0)

    _deselect_all()

    if ptype == "empty":
        bpy.ops.object.empty_add(type="PLAIN_AXES", location=tuple(location))
    elif ptype == "cube":
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=tuple(location))
        obj = bpy.context.active_object
        obj.scale = size
        obj.location = location
    elif ptype == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=tuple(location))
    elif ptype == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(
            radius=radius, depth=depth, location=tuple(location))
    elif ptype == "cone":
        bpy.ops.mesh.primitive_cone_add(
            radius1=radius, radius2=0.0, depth=depth, location=tuple(location))
    elif ptype == "plane":
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=tuple(location))
        obj = bpy.context.active_object
        obj.scale = (size[0], size[1], 1.0)
    elif ptype == "torus":
        bpy.ops.mesh.primitive_torus_add(
            major_radius=radius, minor_radius=depth * 0.2,
            location=tuple(location))
    elif ptype == "monkey":
        bpy.ops.mesh.primitive_monkey_add(size=radius, location=tuple(location))
    elif ptype == "circle":
        bpy.ops.mesh.primitive_circle_add(radius=radius, location=tuple(location))
    else:
        raise ValueError(f"不支持的几何体: {ptype}")

    obj = bpy.context.active_object
    if name:
        obj.name = name
    if any(rotation):
        obj.rotation_euler = tuple(rotation)

    mat_params = params.get("material")
    if mat_params:
        _set_pbr_material(obj, mat_params.get("name") or f"{obj.name}_mat",
                          base_color=mat_params.get("base_color", [0.8, 0.8, 0.8, 1.0]),
                          metallic=mat_params.get("metallic", 0.0),
                          roughness=mat_params.get("roughness", 0.5),
                          emission=mat_params.get("emission", [0, 0, 0]),
                          emission_strength=mat_params.get("emission_strength", 0.0))

    return {
        "name": obj.name,
        "location": list(obj.location),
        "dimensions": list(obj.dimensions),
    }


# ─────────────────────────────────────────────────────────────
# 变换
# ─────────────────────────────────────────────────────────────

def set_transform(params):
    obj = _get_object(params["name"])
    if "location" in params:
        obj.location = _vec3(params["location"])
    if "rotation" in params:
        obj.rotation_euler = _vec3(params["rotation"])
    if "scale" in params:
        obj.scale = _vec3(params["scale"], (1, 1, 1))
    return {"name": obj.name, "location": list(obj.location),
            "rotation": list(obj.rotation_euler), "scale": list(obj.scale)}


def get_transform(params):
    obj = _get_object(params["name"])
    return {"name": obj.name, "location": list(obj.location),
            "rotation": list(obj.rotation_euler), "scale": list(obj.scale),
            "dimensions": list(obj.dimensions)}


def apply_transform(params):
    obj = _get_object(params["name"])
    _select_only(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return {"name": obj.name, "dimensions": list(obj.dimensions)}


def set_origin(params):
    """设置对象原点: bottom|center|top (Z 轴), 或指定位置"""
    obj = _get_object(params["name"])
    mode = params.get("mode", "bottom")
    _select_only(obj)
    if mode == "bottom":
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        # 将原点移到包围盒底面中心
        min_z = obj.bound_box[0][2] * obj.scale.z + obj.location.z
        obj.location.z -= min_z
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR", center="MEDIAN")
        bpy.context.scene.cursor.location = (0, 0, 0)
    elif mode == "center":
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    elif mode == "top":
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        max_z = obj.bound_box[7][2] * obj.scale.z + obj.location.z
        obj.location.z -= max_z
    else:
        raise ValueError(f"不支持的原点模式: {mode}")
    return {"name": obj.name, "location": list(obj.location)}


# ─────────────────────────────────────────────────────────────
# 对象操作
# ─────────────────────────────────────────────────────────────

def duplicate_object(params):
    obj = _get_object(params["name"])
    _select_only(obj)
    bpy.ops.object.duplicate_move()
    dup = bpy.context.active_object
    offset = params.get("offset")
    if offset:
        dup.location = obj.location + Vector(offset)
    if params.get("new_name"):
        dup.name = params["new_name"]
    return {"name": dup.name, "location": list(dup.location)}


def delete_object(params):
    names = params.get("names") or [params.get("name")]
    removed = []
    for n in names:
        obj = bpy.data.objects.get(n)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed.append(n)
    return {"removed": removed}


def join_objects(params):
    """合并多个对象为一个 (保留第一个的名称)"""
    names = params.get("names") or []
    if not names:
        raise ValueError("需要 names 列表")
    target = _get_object(names[0])
    _deselect_all()
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    for n in names[1:]:
        obj = bpy.data.objects.get(n)
        if obj and obj.name != target.name:
            obj.select_set(True)
    bpy.ops.object.join()
    new_name = params.get("new_name")
    if new_name:
        target.name = new_name
    return {"name": target.name, "objects": len(names)}


def parent_object(params):
    child = _get_object(params["child"])
    parent = _get_object(params["parent"])
    child.parent = parent
    return {"child": child.name, "parent": parent.name}


# ─────────────────────────────────────────────────────────────
# 修改器
# ─────────────────────────────────────────────────────────────

_MODIFIERS = {
    "bevel": "BEVEL",
    "solidify": "SOLIDIFY",
    "subdivision": "SUBSURF",
    "mirror": "MIRROR",
    "array": "ARRAY",
    "displace": "DISPLACE",
    "boolean": "BOOLEAN",
    "screw": "SCREW",
    "skin": "SKIN",
    "wireframe": "WIREFRAME",
}


def add_modifier(params):
    """添加修改器

    params:
        name: 对象名
        modifier: bevel|solidify|subdivision|mirror|array|boolean|screw|skin|wireframe
        settings: dict — 修改器专用参数
    """
    obj = _get_object(params["name"])
    mtype = _MODIFIERS.get(params.get("modifier", ""))
    if mtype is None:
        raise ValueError(f"不支持的修改器: {params.get('modifier')}")
    mod = obj.modifiers.new(name=params.get("modifier_name", params["modifier"]), type=mtype)

    s = params.get("settings", {})
    if mtype == "BEVEL":
        mod.width = s.get("width", 0.02)
        mod.segments = s.get("segments", 1)
        mod.limit_method = s.get("limit_method", "ANGLE")
        mod.angle_limit = s.get("angle_limit", math.radians(30))
    elif mtype == "SOLIDIFY":
        mod.thickness = s.get("thickness", 0.05)
        mod.offset = s.get("offset", -1.0)
    elif mtype == "SUBSURF":
        mod.levels = s.get("levels", 2)
        mod.render_levels = s.get("render_levels", mod.levels)
        mod.subdivision_type = s.get("subdivision_type", "CATMULL_CLARK")
    elif mtype == "MIRROR":
        mod.use_axis = (s.get("use_x", True), s.get("use_y", False), s.get("use_z", False))
        mod.use_mirror_merge = s.get("merge", True)
        mod.merge_threshold = s.get("merge_threshold", 0.001)
    elif mtype == "ARRAY":
        mod.count = s.get("count", 4)
        mod.relative_offset_displace = _vec3(s.get("offset", [1, 0, 0]))
    elif mtype == "BOOLEAN":
        op_obj = bpy.data.objects.get(s.get("object", ""))
        if op_obj is None:
            raise ValueError(f"布尔操作对象不存在: {s.get('object')}")
        mod.object = op_obj
        mod.operation = s.get("operation", "DIFFERENCE")
        mod.solver = "FAST"
    elif mtype == "SCREW":
        mod.angle = s.get("angle", math.radians(360))
        mod.steps = s.get("steps", 32)
        mod.axis = s.get("axis", "Z")
    elif mtype == "SKIN":
        pass
    elif mtype == "WIREFRAME":
        mod.thickness = s.get("thickness", 0.02)

    return {"name": obj.name, "modifiers": [m.name for m in obj.modifiers]}


def apply_modifier(params):
    obj = _get_object(params["name"])
    mod_name = params.get("modifier")
    if mod_name:
        mod = obj.modifiers.get(mod_name)
        if mod is None:
            raise ValueError(f"修改器不存在: {mod_name}")
        _select_only(obj)
        bpy.ops.object.modifier_apply(modifier=mod_name)
    else:
        _select_only(obj)
        for m in list(obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=m.name)
    return {"name": obj.name, "modifiers": [m.name for m in obj.modifiers]}


def remove_modifier(params):
    obj = _get_object(params["name"])
    mod = obj.modifiers.get(params.get("modifier", ""))
    if mod:
        obj.modifiers.remove(mod)
    return {"name": obj.name, "modifiers": [m.name for m in obj.modifiers]}


# ─────────────────────────────────────────────────────────────
# 网格编辑 (bmesh)
# ─────────────────────────────────────────────────────────────

def _edit_mesh(obj, edit_fn):
    """在编辑模式下执行 bmesh 操作, 自动恢复模式"""
    if obj.type != "MESH":
        raise ValueError(f"不是网格对象: {obj.name}")
    original = bpy.context.object
    original_mode = original.mode if original else "OBJECT"
    _select_only(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    import bmesh
    bm = bmesh.from_edit_mesh(obj.data)
    bm.normal_update()
    result = edit_fn(bm, obj.data)
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode="OBJECT")
    return result


def _ensure_faces_selected(bm, face_indices):
    if face_indices is None:
        sel = [f for f in bm.faces if f.select]
        if not sel:
            raise ValueError("没有选中的面 (请传入 face_indices)")
        return sel
    faces = []
    for fi in face_indices:
        if fi >= len(bm.faces):
            raise ValueError(f"面索引越界: {fi} (共 {len(bm.faces)} 面)")
        faces.append(bm.faces[fi])
    return faces


def extrude_face(params):
    """沿法线挤出指定面 (真实的挤出 — 保持拓扑)

    params:
        name, face_indices: [int] 或省略 (用当前选中)
        value: 挤出距离 (米)
    """
    obj = _get_object(params["name"])
    value = params.get("value", 0.1)

    def edit(bm, mesh):
        faces = _ensure_faces_selected(bm, params.get("face_indices"))
        import bmesh
        result = bmesh.ops.extrude_face_region(bm, geom=faces)
        for v in result["geom"]:
            if isinstance(v, bmesh.types.BMVert):
                v.co += v.normal * value
        return {"extruded": len(result["geom"])}

    return _edit_mesh(obj, edit)


def inset_face(params):
    """内缩面 (生成窗框/门框的内框)

    params:
        name, face_indices, thickness: 内缩距离
    """
    obj = _get_object(params["name"])
    thickness = params.get("thickness", 0.05)

    def edit(bm, mesh):
        import bmesh
        faces = _ensure_faces_selected(bm, params.get("face_indices"))
        bmesh.ops.inset_region(bm, faces=faces, thickness=thickness, depth=0)
        return {"inset": len(faces)}

    return _edit_mesh(obj, edit)


def loop_cut(params):
    """环切: name, axis: x|y|z, position: 0-1 (相对包围盒), 或 count 均分"""
    obj = _get_object(params["name"])
    axis = params.get("axis", "x").lower()
    position = params.get("position")
    count = params.get("count", 1)

    def edit(bm, mesh):
        dims = mesh.calc_bbox().get("dims", None)
        # 计算切割位置
        verts = list(bm.verts)
        if axis == "x":
            lo, hi = min(v.co.x for v in verts), max(v.co.x for v in verts)
        elif axis == "y":
            lo, hi = min(v.co.y for v in verts), max(v.co.y for v in verts)
        else:
            lo, hi = min(v.co.z for v in verts), max(v.co.z for v in verts)
        positions = []
        if position is not None:
            positions.append(lo + (hi - lo) * _clamp(position, 0.0, 1.0))
        else:
            for i in range(1, count + 1):
                positions.append(lo + (hi - lo) * (i / (count + 1)))
        cuts = 0
        for p in positions:
            import bmesh
            r = bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                                       plane_co=(p if axis == "x" else 0.0,
                                                 p if axis == "y" else 0.0,
                                                 p if axis == "z" else 0.0),
                                       plane_no=(1, 0, 0) if axis == "x" else
                                                ((0, 1, 0) if axis == "y" else (0, 0, 1)),
                                       clear_inner=False, clear_outer=False,
                                       dist=1e-6)
            cuts += 1
        return {"cuts": cuts, "positions": positions}

    return _edit_mesh(obj, edit)


def bevel_edges(params):
    """斜切边: name, width, segments, face_indices (可选, 斜切这些面的外边界)"""
    obj = _get_object(params["name"])
    width = params.get("width", 0.02)
    segments = params.get("segments", 1)

    def edit(bm, mesh):
        import bmesh
        edges = [e for e in bm.edges if e.select]
        if params.get("face_indices"):
            faces = _ensure_faces_selected(bm, params["face_indices"])
            edge_set = set()
            for f in faces:
                edge_set.update(f.edges)
            edges = [e for e in edge_set]
        if not edges:
            # 默认斜切所有锐利边
            edges = [e for e in bm.edges if e.is_boundary or
                     abs(e.calc_face_angle() or 0) > math.radians(25)]
        bmesh.ops.bevel(bm, geom=edges, offset=width,
                        segments=segments, profile=0.5)
        return {"beveled": len(edges)}

    return _edit_mesh(obj, edit)


def subdivide_edges(params):
    """细分: name, cuts (每边切割数)"""
    obj = _get_object(params["name"])
    cuts = params.get("cuts", 1)

    def edit(bm, mesh):
        import bmesh
        bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=cuts)
        return {"subdivided": len(bm.edges)}

    return _edit_mesh(obj, edit)


def bridge_edge_loops(params):
    """桥接边循环 (连接两个开口环)

    params:
        name, a: [顶点索引...] 或 face_indices 的边环, b: 同上
    """
    obj = _get_object(params["name"])

    def edit(bm, mesh):
        import bmesh
        edges_a = [e for e in bm.edges if e.select]
        if params.get("a") and params.get("b"):
            # 用面的边界环
            fa = _ensure_faces_selected(bm, params["a"])
            fb = _ensure_faces_selected(bm, params["b"])
            ea, eb = [], []
            for f in fa:
                ea.extend(e for e in f.edges if e.is_boundary)
            for f in fb:
                eb.extend(e for e in f.edges if e.is_boundary)
            bmesh.ops.bridge_loops(bm, edges=ea + eb)
            return {"bridged": True}
        if not edges_a:
            raise ValueError("需要选中边或提供 a/b 面索引")
        bmesh.ops.bridge_loops(bm, edges=edges_a)
        return {"bridged": True}

    return _edit_mesh(obj, edit)


def boolean_operation(params):
    """布尔运算: name (主体), object (刀具), operation: union|difference|intersect
    使用修改器方式 (可非破坏) 或应用 (destructive=True)"""
    obj = _get_object(params["name"])
    tool_name = params.get("object")
    tool = _get_object(tool_name)
    operation = params.get("operation", "difference")
    op_map = {"union": "UNION", "difference": "DIFFERENCE", "intersect": "INTERSECT"}
    mod = obj.modifiers.new(name="BooleanOp", type="BOOLEAN")
    mod.object = tool
    mod.operation = op_map.get(operation, "DIFFERENCE")
    mod.solver = "FAST"
    if params.get("apply", True):
        _select_only(obj)
        bpy.ops.object.modifier_apply(modifier="BooleanOp")
        # 清理刀具
        if params.get("cleanup_tool", True):
            bpy.data.objects.remove(tool, do_unlink=True)
    return {"name": obj.name, "operation": operation}


# ─────────────────────────────────────────────────────────────
# 材质
# ─────────────────────────────────────────────────────────────

def set_material(params):
    """设置 PBR 材质: name, base_color [r,g,b,a], metallic, roughness,
    emission [r,g,b], emission_strength"""
    obj = _get_object(params["name"])
    mat_name = params.get("material_name") or f"{obj.name}_mat"
    mat = _set_pbr_material(
        obj, mat_name,
        base_color=params.get("base_color", [0.8, 0.8, 0.8, 1.0]),
        metallic=params.get("metallic", 0.0),
        roughness=params.get("roughness", 0.5),
        emission=params.get("emission", [0, 0, 0]),
        emission_strength=params.get("emission_strength", 0.0))
    return {"name": obj.name, "material": mat.name}


def assign_material(params):
    """给对象分配已有材质: name, material"""
    obj = _get_object(params["name"])
    mat = bpy.data.materials.get(params.get("material", ""))
    if mat is None:
        raise ValueError(f"材质不存在: {params.get('material')}")
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return {"name": obj.name, "material": mat.name}


def list_materials(params):
    return {"materials": [m.name for m in bpy.data.materials]}


# ─────────────────────────────────────────────────────────────
# 测量 / 验证
# ─────────────────────────────────────────────────────────────

def _obj_center(name):
    obj = _get_object(name)
    return obj.matrix_world @ Vector((0, 0, 0)) if False else obj.location.copy()


def measure_distance(params):
    """测量两点/两对象距离"""
    if "a" in params and "b" in params:
        a = Vector(params["a"])
        b = Vector(params["b"])
    elif "object_a" in params and "object_b" in params:
        a = _obj_center(params["object_a"])
        b = _obj_center(params["object_b"])
    else:
        raise ValueError("需要 a/b 点坐标或 object_a/object_b")
    dist = (a - b).length
    return {"distance": round(dist, 4), "a": list(a), "b": list(b)}


def measure_dimensions(params):
    obj = _get_object(params["name"])
    return {"name": obj.name, "dimensions": [round(d, 4) for d in obj.dimensions]}


def measure_gap(params):
    """测量两个对象间最近间隙 (沿指定轴或三维)"""
    a = _get_object(params["object_a"])
    b = _get_object(params["object_b"])
    import bmesh
    bma, bmb = bmesh.new(), bmesh.new()
    bma.from_mesh(a.data)
    bmb.from_mesh(b.data)
    bma.transform(a.matrix_world)
    bmb.transform(b.matrix_world)
    try:
        min_dist = float("inf")
        for va in bma.verts:
            for vb in bmb.verts:
                d = (va.co - vb.co).length
                if d < min_dist:
                    min_dist = d
        return {"gap": round(min_dist, 4)}
    finally:
        bma.free()
        bmb.free()


def measure_alignment(params):
    """检查两对象对齐: axis: x|y|z, 返回偏差"""
    a = _get_object(params["object_a"])
    b = _get_object(params["object_b"])
    axis = params.get("axis", "z")
    idx = {"x": 0, "y": 1, "z": 2}[axis]
    av = a.location[idx]
    bv = b.location[idx]
    # 用包围盒边缘对齐检查 (若对象尺寸已知)
    diff = abs(av - bv)
    return {
        "axis": axis,
        "delta": round(diff, 4),
        "aligned": diff < params.get("tolerance", 0.01),
        "a_value": round(av, 4),
        "b_value": round(bv, 4),
    }


def assert_dimensions(params):
    """断言对象尺寸: name, dimensions [x,y,z], tolerance"""
    obj = _get_object(params["name"])
    target = params.get("dimensions")
    tol = params.get("tolerance", 0.01)
    actual = obj.dimensions
    if target:
        diffs = [abs(actual[i] - target[i]) for i in range(min(3, len(target)))]
        ok = all(d <= tol for d in diffs)
        return {"pass": ok, "actual": [round(d, 4) for d in actual],
                "target": target, "max_delta": round(max(diffs), 4) if diffs else 0.0}
    return {"pass": True, "actual": [round(d, 4) for d in actual]}


def assert_contact(params):
    """断言两对象接触: object_a, object_b, tolerance"""
    a = _get_object(params["object_a"])
    b = _get_object(params["object_b"])
    tol = params.get("tolerance", 0.01)
    gap = measure_gap({"object_a": a.name, "object_b": b.name})["gap"]
    # 检查是否重叠 (间隙为负即重叠)
    bbox_a = [a.matrix_world @ Vector(c) for c in a.bound_box]
    bbox_b = [b.matrix_world @ Vector(c) for c in b.bound_box]
    overlap = (min(v.x for v in bbox_a) <= max(v.x for v in bbox_b) and
               max(v.x for v in bbox_a) >= min(v.x for v in bbox_b) and
               min(v.y for v in bbox_a) <= max(v.y for v in bbox_b) and
               max(v.y for v in bbox_a) >= min(v.y for v in bbox_b) and
               min(v.z for v in bbox_a) <= max(v.z for v in bbox_b) and
               max(v.z for v in bbox_a) >= min(v.z for v in bbox_b))
    return {"contact": overlap or gap <= tol, "gap": round(gap, 4), "overlap": overlap}


def check_mesh_quality(params):
    """网格质量检查: name — 非流形/孤立顶点/零面积面/重复顶点/质量评分"""
    obj = _get_object(params["name"])
    report = _mesh_quality_report(obj)
    report["name"] = obj.name
    return report


def check_scene_quality(params):
    """全场景网格质量检查"""
    report = {"objects": [], "worst": None, "average_score": 0}
    scores = []
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.data:
            q = _mesh_quality_report(obj)
            q["name"] = obj.name
            report["objects"].append(q)
            scores.append(q["quality_score"])
    if scores:
        report["average_score"] = round(sum(scores) / len(scores), 1)
        worst = min(scores)
        for o in report["objects"]:
            if o["quality_score"] == worst:
                report["worst"] = o
    report["object_count"] = len(scores)
    return report


# ─────────────────────────────────────────────────────────────
# 纹理烘焙 (Cycles, 大操作 — 在专用线程执行需谨慎, 标记 large)
# ─────────────────────────────────────────────────────────────

def bake_textures(params):
    """烘焙对象材质为 PNG 纹理贴图 (供 UE 使用)

    params:
        name: 对象名
        output_dir: 输出目录
        resolution: 分辨率 (512/1024/2048/4096)
        channels: [basecolor, roughness, metallic] 可选
    """
    import bpy  # noqa: F811 (已在模块顶部)
    obj = _get_object(params["name"])
    output_dir = params.get("output_dir", "")
    resolution = int(params.get("resolution", 2048))
    if not output_dir:
        raise ValueError("需要 output_dir")
    os.makedirs(output_dir, exist_ok=True)

    mat = obj.active_material
    if not mat or not mat.use_nodes:
        raise ValueError(f"对象 {obj.name} 没有基于节点的材质")

    # 保存原设置
    scene = bpy.context.scene
    prev_engine = scene.render.engine
    prev_samples = scene.cycles.samples
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution

    # 选择对象
    _deselect_all()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    channels = params.get("channels") or ["basecolor"]
    result_files = {}

    # 为每个通道创建 image 和临时 tex node
    bake_types = {"basecolor": "COMBINED", "roughness": "ROUGHNESS",
                  "metallic": "METALLIC"}
    for ch in channels:
        bake_type = bake_types.get(ch, "COMBINED")
        img = bpy.data.images.new(f"bake_{ch}", resolution, resolution, alpha=True)
        img.filepath_raw = os.path.join(output_dir, f"{ch}.png")
        img.file_format = "PNG"
        tex_node = mat.node_tree.nodes.new(type="ShaderNodeTexImage")
        tex_node.image = img
        mat.node_tree.nodes.active = tex_node
        bpy.ops.object.bake(type=bake_type)
        img.save()
        mat.node_tree.nodes.remove(tex_node)
        bpy.data.images.remove(img)
        result_files[ch] = os.path.join(output_dir, f"{ch}.png")

    # 恢复
    scene.render.engine = prev_engine
    scene.cycles.samples = prev_samples
    return {"output_dir": output_dir, "files": result_files}


# ─────────────────────────────────────────────────────────────
# 逃生通道 (不推荐常规使用)
# ─────────────────────────────────────────────────────────────

def execute_code(params):
    """执行任意 Blender Python 代码 — 仅作为逃生通道"""
    code = params.get("code", "")
    if not code:
        raise ValueError("需要 code 参数")
    ns = {"__name__": "__bridge_exec__"}
    # 收集 stdout 输出
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<bridge_exec>", "exec"), ns)
    return {"output": buf.getvalue()}


# ─────────────────────────────────────────────────────────────
# 视口截图 (OpenGL 快速截图, 主线程)
# ─────────────────────────────────────────────────────────────

def capture_viewport(params):
    """快速视口截图 — 输出 PNG 到 filepath"""
    filepath = params.get("filepath", "")
    if not filepath:
        raise ValueError("需要 filepath")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    w = params.get("width", 800)
    h = params.get("height", 600)
    try:
        import gpu
        import bgl  # noqa: F401  (兼容引用)
        from gpu_extras.presets import draw_texture_2d  # noqa: F401
        offscreen = gpu.types.GPUOffScreen(w, h)
        with offscreen.bind():
            bpy.ops.view3d.draw_viewport()  # 绘制视口
            buffer = offscreen.read_color(0, 0, w, h, 4, 0, "UBYTE")
        # 保存 PNG
        pixels = buffer.to_image().pixels
        img = bpy.data.images.new("viewport_cap", w, h)
        img.pixels[:] = pixels
        img.filepath_raw = filepath
        img.file_format = "PNG"
        img.save()
        bpy.data.images.remove(img)
        offscreen.free()
    except Exception as e:
        # 回退: 用 Python PIL 路径或直接 viewport 截图
        try:
            bpy.context.scene.render.resolution_x = w
            bpy.context.scene.render.resolution_y = h
            bpy.ops.render.opengl(write_still=True)
            rendered = bpy.data.images["Render Result"]
            rendered.save_render(filepath)
            return {"filepath": filepath, "width": w, "height": h,
                    "engine": "opengl_render"}
        except Exception as e2:
            raise ValueError(f"视口截图失败: {e}; fallback: {e2}")
    return {"filepath": filepath, "width": w, "height": h, "engine": "offscreen"}
