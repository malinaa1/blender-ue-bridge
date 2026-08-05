"""宏命令处理器 — 任务级建模操作, 精确尺寸 + 良好拓扑

核心思想:
- 墙壁/屋顶/楼梯等用 bmesh 逐顶点构造, 全部四边面 (quad) 拓扑
- 门窗洞是真实开口 (不是贴方块), 带内框面
- 所有对象原点在底部中心, 便于精确放置
- 全部带 PBR 材质

handler 签名同 commands: def handler(params) -> dict
"""

import math
import os

import bpy
import bmesh
from mathutils import Vector

# ─────────────────────────────────────────────────────────────
# 通用辅助
# ─────────────────────────────────────────────────────────────

def _new_mesh_obj(name, verts, faces, normal_hint=None):
    """从顶点/面列表创建网格对象"""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for v in verts:
        bm.verts.new(v)
    bm.verts.ensure_lookup_table()
    for f in faces:
        try:
            bm.faces.new([bm.verts[i] for i in f])
        except ValueError:
            pass  # 退化面
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _face(bm, verts, normal):
    """创建面并保证法线朝向 normal"""
    f = bm.faces.new([bm.verts[i] for i in verts])
    f.normal_update()
    if f.normal.dot(normal) < 0:
        f.normal_flip()
    return f


def _set_bottom_origin(obj):
    """原点移动到包围盒底面中心"""
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    min_z = min(v[2] for v in obj.bound_box) * obj.scale.z + obj.location.z
    obj.location.z -= min_z


def _pbr(obj, mat_name, base=(0.8, 0.8, 0.8, 1.0), metallic=0.0,
         roughness=0.5, emission=(0, 0, 0), emission_strength=0.0):
    """设置 PBR 材质 (复用已有材质)"""
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = tuple(base)
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


def _bevel(obj, width=0.015, segments=1):
    mod = obj.modifiers.new(name="Bevel", type="BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(35)
    return mod


def _apply_modifiers(obj):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def _result(name, **extra):
    r = {"name": name, "location": list(bpy.data.objects[name].location),
         "dimensions": [round(d, 4) for d in bpy.data.objects[name].dimensions]}
    r.update(extra)
    return r


def _select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


# ─────────────────────────────────────────────────────────────
# 墙壁 — 带真实门窗洞, 全四边面拓扑
# ─────────────────────────────────────────────────────────────

def _wall_mesh(length, height, thickness, openings):
    """构造带开口的墙壁网格

    openings: [{x: 中心X, width: 宽, z_bottom: 底高, z_top: 顶高}]
    坐标: 墙壁沿 X (长度), Y (厚度), Z (高度), 原点在底面前中心
    """
    xs = sorted(set(round(v, 5) for v in [0.0, length] +
                    [o["x"] - o["width"] / 2 for o in openings] +
                    [o["x"] + o["width"] / 2 for o in openings]))
    zs = sorted(set(round(v, 5) for v in [0.0, height] +
                    [o["z_bottom"] for o in openings] +
                    [o["z_top"] for o in openings]))
    t2 = thickness / 2
    x_idx = {x: i for i, x in enumerate(xs)}
    z_idx = {z: j for j, z in enumerate(zs)}

    def cell_open(i, j):
        x0, x1, z0, z1 = xs[i], xs[i + 1], zs[j], zs[j + 1]
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        for o in openings:
            if (o["x"] - o["width"] / 2 - 1e-6 <= cx <= o["x"] + o["width"] / 2 + 1e-6 and
                    o["z_bottom"] - 1e-6 <= cz <= o["z_top"] + 1e-6):
                return True
        return False

    verts = []
    front, back = {}, {}
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            front[(i, j)] = len(verts)
            verts.append((x, -t2, z))
            back[(i, j)] = len(verts)
            verts.append((x, t2, z))

    mesh = bpy.data.meshes.new("wall_mesh")
    bm = bmesh.new()
    for v in verts:
        bm.verts.new(v)
    bm.verts.ensure_lookup_table()

    # 前后表面
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            if cell_open(i, j):
                continue
            _face(bm, [front[(i, j)], front[(i + 1, j)], front[(i + 1, j + 1)], front[(i, j + 1)]],
                  (0, -1, 0))  # 前 (朝向 -Y)
            _face(bm, [back[(i, j)], back[(i, j + 1)], back[(i + 1, j + 1)], back[(i + 1, j)]],
                  (0, 1, 0))   # 后 (朝向 +Y)

    # 顶部和底部封盖
    nx, nz = len(xs) - 1, len(zs) - 1
    _face(bm, [front[(0, nz)], front[(nx, nz)], back[(nx, nz)], back[(0, nz)]], (0, 0, 1))
    _face(bm, [front[(0, 0)], back[(0, 0)], back[(nx, 0)], front[(nx, 0)]], (0, 0, -1))

    # 开口内框 (门窗洞的真实厚度面)
    for o in openings:
        li, ri = x_idx[round(o["x"] - o["width"] / 2, 5)], x_idx[round(o["x"] + o["width"] / 2, 5)]
        bi, ti = z_idx[round(o["z_bottom"], 5)], z_idx[round(o["z_top"], 5)]
        # 左右侧框 (法线朝开口内部)
        _face(bm, [front[(li, bi)], back[(li, bi)], back[(li, ti)], front[(li, ti)]], (1, 0, 0))
        _face(bm, [back[(ri, bi)], front[(ri, bi)], front[(ri, ti)], back[(ri, ti)]], (-1, 0, 0))
        # 上框
        _face(bm, [front[(li, ti)], front[(ri, ti)], back[(ri, ti)], back[(li, ti)]], (0, 0, -1))
        # 下框 (窗台, 门的话 z_bottom=0 跳过)
        if o["z_bottom"] > 1e-4:
            _face(bm, [front[(li, bi)], back[(li, bi)], back[(ri, bi)], front[(ri, bi)]], (0, 0, 1))

    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def create_wall(params):
    """创建墙壁 (带门窗洞, 四边面拓扑)

    params:
        length, height, thickness (米)
        openings: [{x, width, z_bottom, z_top}] (可选)
        name, material: 可选
    """
    length = params.get("length", 4.0)
    height = params.get("height", 2.8)
    thickness = params.get("thickness", 0.2)
    openings = params.get("openings", []) or []
    name = params.get("name", "Wall")

    mesh = _wall_mesh(length, height, thickness, openings)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    # 原点在底部中心
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.location = (0, 0, -height / 2)  # 网格以 z=0 为底, 原点几何中心在 H/2

    mat = params.get("material")
    if mat:
        _pbr(obj, mat.get("name") or f"{name}_mat",
             base=mat.get("base_color", [0.85, 0.82, 0.78, 1.0]),
             roughness=mat.get("roughness", 0.9))
    return _result(name, "openings", len(openings))


def create_floor(params):
    """创建地面/楼板: length, width, thickness"""
    length = params.get("length", 4.0)
    width = params.get("width", 4.0)
    thickness = params.get("thickness", 0.2)
    name = params.get("name", "Floor")
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (length, width, thickness)
    obj.location = (0, 0, thickness / 2)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    _set_bottom_origin(obj)
    if params.get("material"):
        _pbr(obj, params["material"].get("name") or f"{name}_mat",
             base=params["material"].get("base_color", [0.5, 0.38, 0.25, 1.0]),
             roughness=params["material"].get("roughness", 0.8))
    return _result(name)


# ─────────────────────────────────────────────────────────────
# 屋顶 — 真实几何 (山墙/四坡/平顶/锥形)
# ─────────────────────────────────────────────────────────────

def _roof_gable(length, width, height, eave=0.3, thickness=0.15):
    """山墙屋顶 — 三角棱柱, 带挑檐, 全四边面"""
    L, W, H = length + 2 * eave, width + 2 * eave, height
    t = thickness
    front = [(0, -W / 2, 0), (0, W / 2, 0), (0, 0, H)]
    back = [(L, -W / 2, 0), (L, W / 2, 0), (L, 0, H)]
    # 加檐口厚度: 边缘面
    verts = []
    f = {}
    for i, p in enumerate(front):
        f["f%d" % i] = len(verts); verts.append(p)
    for i, p in enumerate(back):
        f["b%d" % i] = len(verts); verts.append(p)
    verts += [(-t, -W / 2 - t, -t), (L + t, -W / 2 - t, -t), (L + t, W / 2 + t, -t), (-t, W / 2 + t, -t)]  # 底部檐
    verts += [(-t, -W / 2 - t, t), (L + t, -W / 2 - t, t), (L + t, W / 2 + t, t), (-t, W / 2 + t, t)]  # 顶面檐
    vi = lambda x: f[x]

    faces = [
        # 前后三角
        [vi("f0"), vi("f2"), vi("f1")],   # 前 (顶点2为顶)
        [vi("b0"), vi("b1"), vi("b2")],
        # 左右斜屋面 (两坡)
        [vi("f0"), vi("f1"), vi("b1"), vi("b0")],  # 左坡
        [vi("f1"), vi("f2"), vi("b2"), vi("b1")],  # 右坡 (脊线在前)
    ]
    # 底部檐口 (悬挑部分的下底面)
    e0, e1, e2, e3 = 4, 5, 6, 7  # 底檐四角
    t0, t1, t2, t3 = 8, 9, 10, 11  # 顶檐四角
    faces += [
        [e0, e1, e2, e3],          # 檐底 (朝下)
        [t3, t2, t1, t0],          # 檐顶 (朝上)
        [e0, e3, t3, t0],          # 檐侧 (左短边)
        [e1, e2, t2, t1],          # 檐侧 (右短边)
        [e0, e1, t1, t0],          # 檐侧 (前长边)
        [e3, e2, t2, t3],          # 檐侧 (后长边)
    ]
    return verts, faces


def _roof_hip(length, width, height, eave=0.3, thickness=0.15):
    """四坡屋顶 — 脊线 + 两三角两梯形"""
    L, W, H = length + 2 * eave, width + 2 * eave, height
    t = thickness
    # 横截面: 梯形 (底 W, 顶 W*0.3)
    top_w = W * 0.3
    verts = [
        (0, -W / 2, 0), (0, W / 2, 0), (0, top_w / 2, H), (0, -top_w / 2, H),
        (L, -W / 2, 0), (L, W / 2, 0), (L, top_w / 2, H), (L, -top_w / 2, H),
    ]
    faces = [
        [0, 2, 3, 1],   # 前 (梯形)
        [4, 5, 7, 6],   # 后
        [0, 1, 5, 4],   # 左坡
        [1, 3, 7, 5],   # 右坡
        [3, 2, 6, 7],   # 顶脊
        [2, 0, 4, 6],   # 左三角坡
    ]
    return verts, faces


def _roof_pyramid(length, width, height, eave=0.3, thickness=0.15):
    L, W, H = length + 2 * eave, width + 2 * eave, height
    verts = [
        (0, -W / 2, 0), (0, W / 2, 0), (0, W / 2, 0), (0, -W / 2, 0),
        (L, -W / 2, 0), (L, W / 2, 0), (L, 0, H),
    ]
    faces = [
        [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 6], [3, 0, 4, 6],
    ]
    return verts, faces


def create_roof(params):
    """创建屋顶

    params:
        length, width (建筑外廓), height (屋脊高度), eave (挑檐)
        style: gable|hip|flat|pyramid
        name, material
    """
    style = params.get("style", "gable")
    name = params.get("name", "Roof")
    length = params.get("length", 4.0)
    width = params.get("width", 4.0)
    height = params.get("height", 1.5)
    eave = params.get("eave", 0.3)

    if style == "gable":
        verts, faces = _roof_gable(length, width, height, eave)
    elif style == "hip":
        verts, faces = _roof_hip(length, width, height, eave)
    elif style == "pyramid":
        verts, faces = _roof_pyramid(length, width, height, eave)
    elif style == "flat":
        verts, faces = [], []
        verts = [(0, -width / 2 - eave, 0), (0, width / 2 + eave, 0),
                 (length, width / 2 + eave, 0), (length, -width / 2 - eave, 0)]
        # 加边檐
        verts += [(0, -width / 2 - eave, -0.15), (0, width / 2 + eave, -0.15),
                  (length, width / 2 + eave, -0.15), (length, -width / 2 - eave, -0.15)]
        faces = [[0, 1, 2, 3], [7, 6, 5, 4], [0, 3, 7, 4], [1, 2, 6, 5], [3, 2, 6, 7], [0, 4, 5, 1]]
    else:
        raise ValueError(f"不支持的屋顶样式: {style}")

    obj = _new_mesh_obj(name, verts, faces)
    _set_bottom_origin(obj)
    if params.get("material"):
        _pbr(obj, params["material"].get("name") or f"{name}_mat",
             base=params["material"].get("base_color", [0.45, 0.25, 0.18, 1.0]),
             roughness=params["material"].get("roughness", 0.95))
    return _result(name)


# ─────────────────────────────────────────────────────────────
# 门窗
# ─────────────────────────────────────────────────────────────

def create_door(params):
    """创建门 (门框 + 门扇 + 把手)

    params:
        width, height, thickness (门洞尺寸), frame_width, name
        style: plank|panel (可选)
    """
    width = params.get("width", 1.0)
    height = params.get("height", 2.1)
    thickness = params.get("thickness", 0.06)
    fw = params.get("frame_width", 0.08)
    name = params.get("name", "Door")

    def box(n, sx, sy, sz, px, py, pz):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(px, py, pz))
        o = bpy.context.active_object
        o.name = n
        o.scale = (sx, sy, sz)
        return o

    # 门框: 左右立柱 + 上横梁
    jamb_w = fw
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-width / 2 + jamb_w / 2, 0, height / 2))
    lj = bpy.context.active_object; lj.name = f"{name}_Frame_L"; lj.scale = (jamb_w, thickness + 0.05, height)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(width / 2 - jamb_w / 2, 0, height / 2))
    rj = bpy.context.active_object; rj.name = f"{name}_Frame_R"; rj.scale = (jamb_w, thickness + 0.05, height)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, height + fw / 2))
    lt = bpy.context.active_object; lt.name = f"{name}_Frame_T"; lt.scale = (width, thickness + 0.05, fw)

    # 门扇 (略小于洞口)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, height / 2 - 0.02))
    panel = bpy.context.active_object
    panel.name = f"{name}_Panel"
    panel.scale = (width - 2 * fw, thickness, height - fw - 0.02)

    # 门板线条 (竖条装饰)
    if params.get("style", "plank") == "plank":
        for i in [-1, 1]:
            bpy.ops.mesh.primitive_cube_add(size=1.0,
                location=(i * (width - 2 * fw) / 4, thickness * 0.6, height / 2 - 0.02))
            pl = bpy.context.active_object
            pl.name = f"{name}_Plank_{i}"
            pl.scale = (0.02, 0.01, height - fw - 0.05)

    # 把手
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=0.03, location=(0, thickness * 0.9, height * 0.42))
    hnd = bpy.context.active_object
    hnd.name = f"{name}_Handle"
    hnd.rotation_euler = (math.pi / 2, 0, 0)

    # 合并为单一对象
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = panel
    bpy.ops.object.join()
    panel.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _set_bottom_origin(panel)

    _pbr(panel, params.get("material_name", "M_Wood_Door"),
         base=params.get("base_color", [0.35, 0.22, 0.12, 1.0]),
         roughness=0.6)
    return _result(name)


def create_window(params):
    """创建窗 (窗框 + 玻璃 + 竖棂 + 窗台/窗楣)

    params:
        width, height, sill_height (窗台离地), thickness, name
    """
    width = params.get("width", 1.2)
    height = params.get("height", 1.2)
    sill = params.get("sill_height", 0.9)
    thickness = params.get("thickness", 0.06)
    name = params.get("name", "Window")
    fw = 0.06  # 框宽

    # 窗框
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-width / 2 + fw / 2, 0, height / 2))
    lf = bpy.context.active_object; lf.name = f"{name}_Frame_L"; lf.scale = (fw, thickness, height)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(width / 2 - fw / 2, 0, height / 2))
    rf = bpy.context.active_object; rf.name = f"{name}_Frame_R"; rf.scale = (fw, thickness, height)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, height + fw / 2))
    tf = bpy.context.active_object; tf.name = f"{name}_Frame_T"; tf.scale = (width, thickness, fw)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, -fw / 2))
    bf = bpy.context.active_object; bf.name = f"{name}_Frame_B"; bf.scale = (width, thickness, fw)

    # 玻璃 (半透亮色)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, height / 2))
    glass = bpy.context.active_object
    glass.name = f"{name}_Glass"
    glass.scale = (width - 2 * fw, thickness * 0.4, height - 2 * fw)
    _pbr(glass, "M_Glass", base=(0.72, 0.82, 0.9, 1.0), roughness=0.1,
         emission=(0.15, 0.2, 0.3), emission_strength=0.3)

    # 竖棂 (中间竖条)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, height / 2))
    mull = bpy.context.active_object
    mull.name = f"{name}_Mullion"
    mull.scale = (0.03, thickness * 0.5, height - 2 * fw)

    # 窗台 (外凸)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, thickness * 0.8, -0.04))
    sill_box = bpy.context.active_object
    sill_box.name = f"{name}_Sill"
    sill_box.scale = (width + 0.2, 0.12, 0.05)

    # 合并
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = lf
    bpy.ops.object.join()
    lf.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _set_bottom_origin(lf)
    lf.location.z = sill

    _pbr(lf, params.get("material_name", "M_Wood_Window"),
         base=params.get("base_color", [0.8, 0.82, 0.85, 1.0]), roughness=0.5)
    return _result(name)


# ─────────────────────────────────────────────────────────────
# 楼梯 — 单一网格, 全四边面
# ─────────────────────────────────────────────────────────────

def create_staircase(params):
    """直线楼梯: width, height (总高), run (总长), steps (级数)"""
    width = params.get("width", 1.2)
    height = params.get("height", 2.8)
    run = params.get("run", 3.6)
    steps = params.get("steps", 12)
    name = params.get("name", "Staircase")
    return _build_staircase(name, width, run, height, steps)


def _build_staircase(name, width, run, height, steps):
    """干净的楼梯构造: 每个台阶 2 面 (踏板+竖板) + 2 侧板"""
    step_d, step_h = run / steps, height / steps
    w2 = width / 2
    verts = []
    # 踏板顶点 (每台阶 4 个, 顶面 z=(i+1)h)
    for i in range(steps):
        z = (i + 1) * step_h
        y0, y1 = i * step_d, (i + 1) * step_d
        verts += [(-w2, y0, z), (w2, y0, z), (w2, y1, z), (-w2, y1, z)]
    # 竖板顶点 (每台阶 2 个, 前面 y=i*d)
    for i in range(steps):
        z0 = i * step_h
        verts += [(-w2, i * step_d, z0), (w2, i * step_d, z0)]

    faces = []
    for i in range(steps):
        t0 = i * 4
        faces.append([t0, t0 + 1, t0 + 2, t0 + 3])              # 踏板
        r0 = steps * 4 + i * 2
        faces.append([t0, t0 + 3, r0 + 1, r0])                  # 竖板
    # 两侧封板: 锯齿轮廓
    for s, sx in [(0, -w2), (1, w2)]:
        base = len(verts)
        for i in range(steps + 1):
            verts.append((sx, i * step_d, i * step_h))
        # 侧板每个台阶段是一个四边形 (从下后角到上前沿)
        for i in range(steps):
            b0 = base + i
            b1 = base + i + 1
            if s == 0:
                faces.append([b0, b1, b1 + steps + 1, b0 + steps + 1])
            else:
                faces.append([b1, b0, b0 + steps + 1, b1 + steps + 1])
    obj = _new_mesh_obj(name, verts, faces)
    _set_bottom_origin(obj)
    _pbr(obj, "M_Stone_Stair", base=(0.6, 0.58, 0.55, 1.0), roughness=0.9)
    return _result(name)


# ─────────────────────────────────────────────────────────────
# 家具
# ─────────────────────────────────────────────────────────────

def create_table(params):
    """桌子: length, width, height, top_thickness, leg_size"""
    length = params.get("length", 1.8)
    width = params.get("width", 0.9)
    height = params.get("height", 0.75)
    top_t = params.get("top_thickness", 0.05)
    leg = params.get("leg_size", 0.06)
    name = params.get("name", "Table")

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, height - top_t / 2))
    top = bpy.context.active_object; top.name = f"{name}_Top"; top.scale = (length, width, top_t)
    for (lx, ly) in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        bpy.ops.mesh.primitive_cube_add(size=1.0,
            location=(lx * (length / 2 - leg / 2), ly * (width / 2 - leg / 2), (height - top_t) / 2))
        o = bpy.context.active_object
        o.name = f"{name}_Leg_{lx}_{ly}"
        o.scale = (leg, leg, height - top_t)

    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = top
    bpy.ops.object.join()
    top.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _set_bottom_origin(top)
    _pbr(top, "M_Wood_Table", base=(0.42, 0.28, 0.16, 1.0), roughness=0.55)
    return _result(name)


def create_chair(params):
    """椅子: width, depth, seat_height, back_height"""
    width = params.get("width", 0.45)
    depth = params.get("depth", 0.45)
    seat_h = params.get("seat_height", 0.45)
    back_h = params.get("back_height", 0.9)
    name = params.get("name", "Chair")
    leg = 0.045
    seat_t = 0.04

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, seat_h - seat_t / 2))
    seat = bpy.context.active_object; seat.name = f"{name}_Seat"; seat.scale = (width, depth, seat_t)
    for (lx, ly) in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        bpy.ops.mesh.primitive_cube_add(size=1.0,
            location=(lx * (width / 2 - leg / 2), ly * (depth / 2 - leg / 2), (seat_h - seat_t) / 2))
        o = bpy.context.active_object; o.name = f"{name}_Leg_{lx}_{ly}"
        o.scale = (leg, leg, seat_h - seat_t)
    # 靠背
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, -depth / 2 + 0.02, (seat_h + back_h) / 2))
    back = bpy.context.active_object; back.name = f"{name}_Back"
    back.scale = (width, 0.035, back_h - seat_h)

    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = seat
    bpy.ops.object.join()
    seat.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _set_bottom_origin(seat)
    _pbr(seat, "M_Wood_Chair", base=(0.45, 0.3, 0.17, 1.0), roughness=0.6)
    return _result(name)


def create_crate(params):
    """木箱: length, width, height, 带边框"""
    length = params.get("length", 0.6)
    width = params.get("width", 0.6)
    height = params.get("height", 0.5)
    name = params.get("name", "Crate")

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, height / 2))
    body = bpy.context.active_object
    body.name = name
    body.scale = (length, width, height)
    _bevel(body, width=0.03, segments=2)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _set_bottom_origin(body)
    # 边框条
    for dz in [0.05, height - 0.05]:
        for (lx, ly) in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            bpy.ops.mesh.primitive_cube_add(size=1.0,
                location=(lx * length / 2 * (0.5 if lx else 0.5), ly * width / 2 * (0.5 if ly else 0.5), dz))
            o = bpy.context.active_object
            o.scale = (length * 0.55 if lx else 0.04, width * 0.55 if ly else 0.04, 0.03)
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    body.name = name
    _set_bottom_origin(body)
    _pbr(body, "M_Wood_Crate", base=(0.52, 0.36, 0.2, 1.0), roughness=0.75)
    return _result(name)


def create_column(params):
    """柱子: height, radius, fluted (凹槽纹), capital (柱头)"""
    height = params.get("height", 3.0)
    radius = params.get("radius", 0.2)
    name = params.get("name", "Column")

    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=radius, depth=height,
                                        location=(0, 0, height / 2))
    shaft = bpy.context.active_object
    shaft.name = f"{name}_Shaft"
    # 柱头
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=radius * 1.4, depth=0.12,
                                        location=(0, 0, height + 0.06))
    cap = bpy.context.active_object
    cap.name = f"{name}_Capital"
    # 柱基
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=radius * 1.25, depth=0.1,
                                        location=(0, 0, 0.05))
    base = bpy.context.active_object
    base.name = f"{name}_Base"
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = shaft
    bpy.ops.object.join()
    shaft.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _set_bottom_origin(shaft)
    _pbr(shaft, "M_Stone_Column", base=(0.78, 0.76, 0.72, 1.0), roughness=0.85)
    return _result(name)


# ─────────────────────────────────────────────────────────────
# 自然资产
# ─────────────────────────────────────────────────────────────

def create_tree(params):
    """程序化树: 树干 (锥+弯曲) + 树枝 + 树冠球体

    params: height, trunk_radius, canopy_radius, name, style: oak|pine
    """
    height = params.get("height", 4.0)
    trunk_r = params.get("trunk_radius", 0.2)
    canopy_r = params.get("canopy_radius", 1.2)
    name = params.get("name", "Tree")
    style = params.get("style", "oak")

    trunk_h = height * 0.55

    # 树干 (锥形 + 轻微弯曲)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=8,
                          radius1=trunk_r, radius2=trunk_r * 0.6, depth=trunk_h)
    mesh = bpy.data.meshes.new("trunk_mesh")
    bm.to_mesh(mesh)
    bm.free()
    trunk = bpy.data.objects.new(f"{name}_Trunk", mesh)
    bpy.context.collection.objects.link(trunk)
    trunk.location = (0, 0, trunk_h / 2)
    for v in trunk.data.vertices:
        t = (v.co.z + trunk_h / 2) / trunk_h
        v.co.x += (t ** 2) * 0.25  # 弯曲

    if style == "pine":
        # 松树: 3 层锥形树冠
        layers = 3
        for i in range(layers):
            r = canopy_r * (1 - i * 0.2)
            h = trunk_h + (i + 0.5) * (height - trunk_h) / layers
            bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=r, radius2=0.0,
                                            depth=(height - trunk_h) / layers * 1.4,
                                            location=(0, 0, h + 0.3))
            cone = bpy.context.active_object
            cone.name = f"{name}_Foliage_{i}"
    else:
        # 橡树: 树冠球体群
        import random
        random.seed(int(params.get("seed", 42)))
        for i in range(5):
            r = canopy_r * random.uniform(0.6, 0.9)
            ang = random.uniform(0, 2 * math.pi)
            d = canopy_r * random.uniform(0.3, 0.8)
            z = trunk_h + canopy_r * random.uniform(0.3, 1.0)
            bm = bmesh.new()
            bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r)
            for v in bm.verts:
                v.co += Vector((random.uniform(-0.1, 0.1), random.uniform(-0.1, 0.1),
                                random.uniform(-0.08, 0.08))) * r
            mesh = bpy.data.meshes.new("foliage_mesh")
            bm.to_mesh(mesh)
            bm.free()
            fol = bpy.data.objects.new(f"{name}_Foliage_{i}", mesh)
            bpy.context.collection.objects.link(fol)
            fol.location = (math.cos(ang) * d, math.sin(ang) * d, z)

    # 合并
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = trunk
    bpy.ops.object.join()
    trunk.name = name
    _set_bottom_origin(trunk)

    _pbr(trunk, "M_Bark", base=(0.32, 0.2, 0.11, 1.0), roughness=0.95)
    return _result(name)


def create_rock(params):
    """程序化岩石: 噪波变形 icosphere"""
    radius = params.get("radius", 0.6)
    name = params.get("name", "Rock")
    seed = params.get("seed", 0)

    import random
    random.seed(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=radius)
    for v in bm.verts:
        n = (math.sin(v.co.x * 3 + seed) * math.cos(v.co.y * 3) * 0.25 +
             math.sin(v.co.z * 5 + seed * 2) * 0.2)
        v.co *= 1.0 + n
        v.co.z *= 0.7  # 压扁
    mesh = bpy.data.meshes.new("rock_mesh")
    bm.to_mesh(mesh)
    bm.free()
    rock = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(rock)
    _set_bottom_origin(rock)
    _pbr(rock, "M_Rock", base=(0.45, 0.42, 0.38, 1.0), roughness=0.95)
    return _result(name)


# ─────────────────────────────────────────────────────────────
# 工作流: 中世纪房屋
# ─────────────────────────────────────────────────────────────

def build_medieval_house(params):
    """完整中世纪房屋 — 精确尺寸, 门窗真实开洞, 带装饰

    params:
        length, depth, height (外墙尺寸), roof_style: gable|hip
        door: {x, width, height} 门口位置
        windows: [{x, width, height, sill_height}] 窗列表
        wall_thickness, roof_height, name
    """
    L = params.get("length", 6.0)
    D = params.get("depth", 5.0)
    H = params.get("height", 3.0)
    t = params.get("wall_thickness", 0.2)
    roof_h = params.get("roof_height", 1.8)
    name = params.get("name", "MedievalHouse")
    door = params.get("door") or {"x": 0, "width": 1.0, "height": 2.1}
    windows = params.get("windows") or [
        {"x": 2.0, "width": 1.2, "height": 1.2, "z_bottom": 0.9},
        {"x": -2.0, "width": 1.2, "height": 1.2, "z_bottom": 0.9},
    ]

    parts = []

    # 1. 地面
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.15))
    floor = bpy.context.active_object
    floor.name = f"{name}_Floor"
    floor.scale = (L + 0.6, D + 0.6, 0.3)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _set_bottom_origin(floor)
    _pbr(floor, "M_Stone_Floor", base=(0.55, 0.53, 0.5, 1.0), roughness=0.95)
    parts.append(floor.name)

    # 2. 四面墙 (前墙带门+窗)
    front_openings = []
    front_openings.append({"x": door["x"], "width": door["width"],
                           "z_bottom": 0, "z_top": door["height"]})
    for w in windows:
        front_openings.append({"x": w["x"], "width": w["width"],
                               "z_bottom": w.get("z_bottom", 0.9),
                               "z_top": w["z_bottom"] + w["height"]})
    walls = []
    for (wl, wo, rot, name_w) in [
        (L, front_openings, 0.0, f"{name}_Wall_Front"),
        (L, [], math.pi, f"{name}_Wall_Back"),
        (D, [], math.pi / 2, f"{name}_Wall_Left"),
        (D, [], -math.pi / 2, f"{name}_Wall_Right"),
    ]:
        mesh = _wall_mesh(wl, H, t, wo)
        obj = bpy.data.objects.new(name_w, mesh)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        obj.location = (0, 0, -H / 2)
        obj.rotation_euler = (0, 0, rot)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        _set_bottom_origin(obj)
        # 定位: 前墙 y=-D/2, 后墙 y=+D/2, 左墙 x=-L/2, 右墙 x=+L/2
        if "Front" in name_w:
            obj.location = (0, -D / 2, 0)
        elif "Back" in name_w:
            obj.location = (0, D / 2, 0)
        elif "Left" in name_w:
            obj.location = (-L / 2, 0, 0)
        else:
            obj.location = (L / 2, 0, 0)
        _pbr(obj, "M_Plaster", base=(0.86, 0.83, 0.78, 1.0), roughness=0.9)
        _bevel(obj, width=0.02)
        walls.append(obj.name)
    parts += walls

    # 3. 门
    d_result = create_door({"width": door["width"], "height": door["height"],
                            "thickness": t - 0.02, "name": f"{name}_Door",
                            "location_x": door["x"]})
    door_obj = bpy.data.objects.get(f"{name}_Door")
    if door_obj:
        door_obj.location = (door["x"], -D / 2 + 0.01, 0)
        door_obj.rotation_euler = (0, 0, math.pi)  # 朝外
        parts.append(door_obj.name)

    # 4. 窗
    for i, w in enumerate(windows):
        w_result = create_window({"width": w["width"], "height": w["height"],
                                  "sill_height": w.get("z_bottom", 0.9),
                                  "thickness": t - 0.02, "name": f"{name}_Window_{i}"})
        wobj = bpy.data.objects.get(f"{name}_Window_{i}")
        if wobj:
            wobj.location = (w["x"], -D / 2 - 0.02, w.get("z_bottom", 0.9))
            parts.append(wobj.name)

    # 5. 屋顶
    roof = create_roof({"length": L, "width": D, "height": roof_h,
                        "style": params.get("roof_style", "gable"),
                        "name": f"{name}_Roof",
                        "material": {"name": "M_Clay_Roof",
                                     "base_color": [0.55, 0.3, 0.22, 1.0],
                                     "roughness": 0.9}})
    roof_obj = bpy.data.objects.get(f"{name}_Roof")
    if roof_obj:
        roof_obj.location = (0, 0, H)
        parts.append(roof_obj.name)

    # 6. 烟囱
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(L * 0.3, D * 0.2, H + roof_h + 0.4))
    chim = bpy.context.active_object
    chim.name = f"{name}_Chimney"
    chim.scale = (0.5, 0.5, 0.8)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _set_bottom_origin(chim)
    chim.location = (L * 0.3, D * 0.2, H)
    _pbr(chim, "M_Stone", base=(0.6, 0.58, 0.55, 1.0), roughness=0.95)
    parts.append(chim.name)

    # 7. 石基
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.08))
    base = bpy.context.active_object
    base.name = f"{name}_Base"
    base.scale = (L + 0.4, D + 0.4, 0.16)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _set_bottom_origin(base)
    _pbr(base, "M_Stone", base=(0.55, 0.53, 0.5, 1.0), roughness=0.95)
    parts.append(base.name)

    # 应用斜切到所有墙体
    for wname in walls:
        obj = bpy.data.objects.get(wname)
        if obj and obj.modifiers.get("Bevel"):
            _apply_modifiers(obj)

    return {
        "name": name,
        "parts": parts,
        "dimensions": {"length": L, "depth": D, "height": H,
                       "roof_height": roof_h},
        "total_objects": len(parts),
    }


# ─────────────────────────────────────────────────────────────
# 相机与运镜宏 (AI 影视工作流核心)
# ─────────────────────────────────────────────────────────────

def camera_setup(params):
    """创建相机 + 目标点 (空物体), 并设为活动相机

    params:
        location [x,y,z], target [x,y,z], fov (度, 默认 45),
        name, target_name, lens_mm (焦距, 可选覆盖 fov)
    """
    from .animation import _get_object  # noqa: F401 (一致性)
    bpy.ops.object.camera_add(location=tuple(params.get("location", [5, -5, 2])))
    cam = bpy.context.active_object
    cam.name = params.get("name", "Camera")
    cam.data.lens = params.get("lens_mm", 35)
    if params.get("fov"):
        cam.data.angle = math.radians(params["fov"])

    # 目标空物体
    bpy.ops.object.empty_add(type="SPHERE",
                             location=tuple(params.get("target", [0, 0, 1])))
    target = bpy.context.active_object
    target.name = params.get("target_name", f"{cam.name}_Target")
    target.scale = (0.1, 0.1, 0.1)

    # 相机跟踪目标
    con = cam.constraints.new(type="TRACK_TO")
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    # 设为活动相机
    bpy.context.scene.camera = cam

    return {"camera": cam.name, "target": target.name,
            "location": list(cam.location)}


def _keyframe_camera(cam, frame, location):
    cam.location = Vector(location)
    cam.keyframe_insert(data_path="location", frame=frame)


def camera_orbit(params):
    """相机环绕运镜: 围绕目标旋转半圈/整圈

    params:
        camera (相机名), target (目标名或 [x,y,z]), radius,
        start_angle, end_angle (度, 绕 Z 轴), frames (总帧数),
        height (相机高度), interpolation
    """
    from .animation import _get_object, set_frame_range, set_frame
    cam = _get_object(params.get("camera", "Camera"))
    radius = params.get("radius", 8.0)
    height = params.get("height", 2.0)
    sa = math.radians(params.get("start_angle", 0))
    ea = math.radians(params.get("end_angle", 360))
    frames = int(params.get("frames", 120))
    start_frame = int(params.get("start_frame", 0))
    interp = params.get("interpolation", "bezier")

    target_name = params.get("target")
    if target_name and target_name in bpy.data.objects:
        tgt = bpy.data.objects[target_name]
        target_pos = tgt.location.copy()
    else:
        target_pos = Vector(params.get("target_pos", [0, 0, 1])) if not target_name else Vector([0, 0, 1])

    # 沿圆弧插值相机位置关键帧 (每 15 度一个关键帧, BEZIER 平滑)
    steps = max(8, int(abs(ea - sa) / (math.pi / 12)))
    for i in range(steps + 1):
        angle = sa + (ea - sa) * (i / steps)
        frame = start_frame + int(frames * (i / steps))
        pos = (target_pos.x + radius * math.cos(angle),
               target_pos.y + radius * math.sin(angle),
               height)
        _keyframe_camera(cam, frame, pos)

    # 设置插值模式
    if cam.animation_data and cam.animation_data.action:
        mode = {"bezier": "BEZIER", "linear": "LINEAR", "constant": "CONSTANT"}.get(interp, "BEZIER")
        for fc in cam.animation_data.action.fcurves:
            if fc.data_path == "location":
                for kp in fc.keyframe_points:
                    kp.interpolation = mode

    set_frame_range({"start": start_frame, "end": start_frame + frames})
    set_frame({"frame": start_frame})
    return {"camera": cam.name, "orbit": f"{math.degrees(sa):.0f}°→{math.degrees(ea):.0f}°",
            "frames": frames}


def camera_dolly(params):
    """相机推拉: 沿视线方向前进/后退

    params: camera, target, from_distance, to_distance, frames, height
    """
    from .animation import _get_object, set_frame_range
    cam = _get_object(params.get("camera", "Camera"))
    radius_from = params.get("from_distance", 8.0)
    radius_to = params.get("to_distance", 3.0)
    height = params.get("height", 2.0)
    frames = int(params.get("frames", 90))
    start_frame = int(params.get("start_frame", 0))

    target_name = params.get("target")
    if target_name and target_name in bpy.data.objects:
        tgt = bpy.data.objects[target_name]
        tx, ty = tgt.location.x, tgt.location.y
    else:
        tx, ty = 0.0, 0.0

    # 固定角度 (相机当前角度)
    cur_angle = math.atan2(cam.location.y - ty, cam.location.x - tx)

    for i, r in [(0, radius_from), (1, radius_to)]:
        frame = start_frame + int(frames * i)
        _keyframe_camera(cam, frame, (tx + r * math.cos(cur_angle),
                                      ty + r * math.sin(cur_angle),
                                      height))
    set_frame_range({"start": start_frame, "end": start_frame + frames})
    return {"camera": cam.name, "dolly": f"{radius_from}m→{radius_to}m",
            "frames": frames}


def animate_turntable(params):
    """转盘动画 (产品展示): 相机固定, 对象绕 Z 轴旋转 N 圈

    params: object_name, revolutions, frames, axis (z|x|y), start_frame
    """
    from .animation import _get_object, set_frame_range
    obj = _get_object(params.get("object_name", ""))
    revs = params.get("revolutions", 1)
    frames = int(params.get("frames", 120))
    start_frame = int(params.get("start_frame", 0))
    axis = params.get("axis", "z").lower()
    axis_idx = {"x": 0, "y": 1, "z": 2}[axis]

    # 记录当前旋转, 动画到 +N 圈
    cur = list(obj.rotation_euler)
    cur[axis_idx] += revs * 2 * math.pi

    obj.keyframe_insert(data_path="rotation_euler", frame=start_frame)
    obj.rotation_euler = Euler(cur, "XYZ")
    obj.keyframe_insert(data_path="rotation_euler", frame=start_frame + frames)

    set_frame_range({"start": start_frame, "end": start_frame + frames})
    return {"object": obj.name, "revolutions": revs, "axis": axis,
            "frames": frames}


def animate_float(params):
    """漂浮动画 (sin 波): 对象在 base_z 附近上下浮动

    params: object_name, height (浮动幅度), frames (周期), start_frame
    """
    from .animation import _get_object, set_frame_range
    obj = _get_object(params.get("object_name", ""))
    amp = params.get("height", 0.3)
    frames = int(params.get("frames", 60))
    start_frame = int(params.get("start_frame", 0))
    base_z = obj.location.z

    steps = 16
    for i in range(steps + 1):
        t = i / steps
        frame = start_frame + int(frames * t)
        obj.location.z = base_z + amp * math.sin(t * 2 * math.pi)
        obj.keyframe_insert(data_path="location", frame=frame)

    set_frame_range({"start": start_frame, "end": start_frame + frames * 2})
    return {"object": obj.name, "amplitude": amp, "period": frames}


def animate_appear(params):
    """出现动画: 从 scale 0 弹出到全尺寸 (带弹跳)

    params: object_name, frame, duration (帧), bounce (是否弹跳)
    """
    from .animation import _get_object, set_frame_range
    obj = _get_object(params.get("object_name", ""))
    frame = int(params.get("frame", 0))
    duration = int(params.get("duration", 20))

    obj.scale = (0.001, 0.001, 0.001)
    obj.keyframe_insert(data_path="scale", frame=frame)
    if params.get("bounce", True):
        obj.scale = (1.15, 1.15, 1.15)
        obj.keyframe_insert(data_path="scale", frame=frame + int(duration * 0.6))
        obj.scale = (0.95, 0.95, 0.95)
        obj.keyframe_insert(data_path="scale", frame=frame + int(duration * 0.85))
    obj.scale = (1.0, 1.0, 1.0)
    obj.keyframe_insert(data_path="scale", frame=frame + duration)

    set_frame_range({"start": frame, "end": frame + duration + 10})
    return {"object": obj.name, "frame": frame, "duration": duration}


def follow_path(params):
    """沿路径运动: 对象沿曲线路径移动 (Follow Path 约束)

    params: object_name, path_name (曲线对象), frames, start_frame
    """
    from .animation import _get_object, add_constraint, set_frame_range
    obj = _get_object(params.get("object_name", ""))
    path = _get_object(params.get("path_name", ""))
    if path.type != "CURVE":
        raise ValueError(f"路径必须是曲线对象: {path.name}")
    frames = int(params.get("frames", 120))
    start_frame = int(params.get("start_frame", 0))

    add_constraint({"name": obj.name, "constraint": "follow_path",
                    "target": path.name, "constraint_name": "FollowPath"})
    con = obj.constraints["FollowPath"]
    con.offset = 0.0
    con.keyframe_insert(data_path="offset", frame=start_frame)
    con.offset = frames
    con.keyframe_insert(data_path="offset", frame=start_frame + frames)

    set_frame_range({"start": start_frame, "end": start_frame + frames})
    return {"object": obj.name, "path": path.name, "frames": frames}


# ─────────────────────────────────────────────────────────────
# 角色部件宏 (Q萌风格)
# ─────────────────────────────────────────────────────────────

def create_turtle_shell(params):
    """六边形龟壳: 半球 + 鳞片凸块 + 裙边

    params:
        radius (壳半径, 默认 0.8), height (椭圆高度), name, material
    """
    import bmesh as _bm
    radius = params.get("radius", 0.8)
    height = params.get("height", 0.55)
    name = params.get("name", "Shell")

    # UV 球, 椭圆化, 长轴沿 X
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=radius,
                                         location=(0, 0, 0))
    shell = bpy.context.active_object
    shell.name = name
    shell.scale = (1.15, 1.0, height / radius)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # bmesh: 删下半球, 顶面鳞片凸起, 底部裙边
    _select_only(shell)
    try:
        bpy.ops.object.mode_set(mode="EDIT")
        bm = _bm.from_edit_mesh(shell.data)
        bm.normal_update()

        # 1. 删除 z<0 的顶点 (留半球)
        remove = [v for v in bm.verts if v.co.z < 0.001]
        _bm.ops.delete(bm, geom=remove, context="VERTS")
        bm.verts.ensure_lookup_table()

        # 2. 顶面鳞片: 选 z > 40% 高的面, inset + 两次挤出 (凸块)
        max_z = max(v.co.z for v in bm.verts)
        top_faces = [f for f in bm.faces if f.calc_center_median().z > max_z * 0.4]
        if top_faces:
            _bm.ops.inset_region(bm, faces=top_faces, thickness=0.03, depth=0)
            _bm.ops.inset_region(bm, faces=top_faces, thickness=0.012, depth=0.02)
            for f in top_faces:
                f.normal_update()

        # 3. 底部裙边: 选边缘环, 挤出外扩
        boundary = [e for e in bm.edges if e.is_boundary]
        if boundary:
            r = _bm.ops.extrude_edge_only(bm, edges=boundary)
            # 5.x 兼容: 返回值键可能变化, 从结果里收集所有边
            new_edges = []
            for val in r.values():
                for item in val:
                    if isinstance(item, _bm.types.BMEdge):
                        new_edges.append(item)
            for e in new_edges:
                for v in e.verts:
                    v.co = v.co * 1.15 + Vector((0, 0, 0.02))

        bm.normal_update()
        _bm.update_edit_mesh(shell.data)
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")

    # 4. 圆润处理
    _bevel(shell, width=0.015, segments=1)
    subsurf = shell.modifiers.new(name="Subsurf", type="SUBSURF")
    subsurf.levels = 2
    subsurf.render_levels = 2
    _apply_modifiers(shell)

    mat = params.get("material")
    _pbr(shell, (mat or {}).get("name", "M_Shell_Green"),
         base=(mat or {}).get("base_color", [0.15, 0.45, 0.2, 1.0]),
         roughness=(mat or {}).get("roughness", 0.4),
         metallic=(mat or {}).get("metallic", 0.0))

    return _result(name, scales=len(top_faces))


def create_cute_eye(params):
    """Q萌大眼睛: 白眼球 + 大瞳孔 + 高光 (自带发光)

    params:
        location [x,y,z], scale, name, look_at (可选: 注视对象)
    """
    loc = params.get("location", [0, 0, 0])
    scale = params.get("scale", 1.0)
    name = params.get("name", "Eye")

    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    # 白眼球 (椭球)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.16 * scale, location=tuple(loc))
    eye = bpy.context.active_object
    eye.name = name
    eye.scale = (1.0, 1.0, 1.15)
    _select_only(eye)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _pbr(eye, "M_Eye_White", base=(0.98, 0.98, 1.0, 1.0), roughness=0.1)

    # 瞳孔 (深色小球, 突出前方)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.095 * scale,
        location=(loc[0] + 0.09 * scale, loc[1], loc[2] - 0.02 * scale))
    pupil = bpy.context.active_object
    pupil.name = f"{name}_Pupil"
    pupil.scale = (0.7, 0.75, 0.75)
    _select_only(pupil)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _pbr(pupil, "M_Eye_Pupil", base=(0.08, 0.08, 0.1, 1.0), roughness=0.05,
         emission=(0.05, 0.05, 0.08), emission_strength=0.5)

    # 高光 (小发光点)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.028 * scale,
        location=(loc[0] + 0.14 * scale, loc[1] + 0.045 * scale, loc[2] + 0.075 * scale))
    glint = bpy.context.active_object
    glint.name = f"{name}_Glint"
    _pbr(glint, "M_Eye_Glint", base=(1.0, 1.0, 1.0, 1.0), roughness=0.0,
         emission=(1.0, 1.0, 1.0), emission_strength=2.0)

    # 合并 (只选眼睛部件 — 绝不用 select_all, 会误并场景其他对象)
    bpy.ops.object.select_all(action="DESELECT")
    for part in [eye, pupil, glint]:
        part.select_set(True)
    bpy.context.view_layer.objects.active = eye
    bpy.ops.object.join()
    eye.name = name

    look = params.get("look_at")
    if look and look in bpy.data.objects:
        con = eye.constraints.new(type="TRACK_TO")
        con.target = bpy.data.objects[look]
        con.track_axis = "TRACK_NEGATIVE_Z"
        con.up_axis = "UP_Y"

    return _result(name)


# ─────────────────────────────────────────────────────────────
# 场景宏 (海底竞技场)
# ─────────────────────────────────────────────────────────────

def create_arena(params):
    """悬浮环形战斗平台: 金属圆盘 + 发光边缘环 + 支撑柱

    params:
        radius, thickness, height (离地高度), glow_color, name
    """
    radius = params.get("radius", 4.0)
    thickness = params.get("thickness", 0.3)
    height = params.get("height", 0.2)
    name = params.get("name", "Arena")
    glow = params.get("glow_color", [0.2, 0.6, 1.0])

    # 平台 (圆柱)
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=thickness,
                                        location=(0, 0, thickness / 2 + height))
    plate = bpy.context.active_object
    plate.name = f"{name}_Plate"
    _pbr(plate, "M_Arena_Metal", base=(0.35, 0.38, 0.42, 1.0), roughness=0.35,
         metallic=0.8)

    # 发光边缘环 (扁环)
    bpy.ops.mesh.primitive_torus_add(major_radius=radius + 0.05, minor_radius=0.06,
                                     location=(0, 0, thickness + height + 0.02))
    ring = bpy.context.active_object
    ring.name = f"{name}_GlowRing"
    ring.scale = (1.0, 1.0, 0.4)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _pbr(ring, "M_Arena_Glow", base=(*glow, 1.0), roughness=0.1, metallic=0.2,
         emission=tuple(glow), emission_strength=3.0)

    # 支撑柱 ×4
    for i in range(4):
        import math as _m
        a = i * _m.pi / 2 + _m.pi / 4
        x, y = _m.cos(a) * radius * 0.6, _m.sin(a) * radius * 0.6
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.12,
                                            depth=height + thickness,
                                            location=(x, y, (height + thickness) / 2))
        col = bpy.context.active_object
        col.name = f"{name}_Pillar_{i}"
        _pbr(col, "M_Arena_Metal", base=(0.3, 0.32, 0.36, 1.0), roughness=0.4,
             metallic=0.8)

    return {"name": name, "radius": radius, "parts": 6}


def create_bubbles(params):
    """漂浮水泡: 半透明小球群 + 可选上升动画

    params:
        count, area (散布范围 [x,y,z]), size (半径范围), name,
        animate (是否上升动画), frames (动画帧数)
    """
    import random
    count = int(params.get("count", 20))
    area = params.get("area", [4, 4, 3])
    size = params.get("size", [0.05, 0.15])
    name = params.get("name", "Bubbles")
    random.seed(params.get("seed", 7))

    created = []
    for i in range(count):
        r = random.uniform(*size)
        loc = (random.uniform(-area[0], area[0]),
               random.uniform(-area[1], area[1]),
               random.uniform(0, area[2]))
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc)
        b = bpy.context.active_object
        b.name = f"{name}_{i:03d}"
        _pbr(b, "M_Bubble", base=(0.7, 0.85, 1.0, 0.5), roughness=0.05,
             emission=(0.4, 0.6, 0.9), emission_strength=0.4)
        created.append(b.name)

    if params.get("animate"):
        from .animation import set_frame_range, set_frame
        frames = int(params.get("frames", 120))
        for i, bname in enumerate(created):
            b = bpy.data.objects.get(bname)
            if not b:
                continue
            start = int(params.get("start_frame", 0))
            b.keyframe_insert(data_path="location", frame=start)
            b.location.z += random.uniform(1.5, 3.5)
            b.location.x += random.uniform(-0.5, 0.5)
            b.keyframe_insert(data_path="location", frame=start + frames)
        set_frame_range({"start": 0, "end": start + frames})

    return {"count": len(created), "name": name}


def setup_compositor_glow(params):
    """合成辉光: 渲染后处理 (Glare 节点)

    params:
        threshold (辉光阈值, 0-1), size (强度)
    兼容 Blender 4.x/5.x (合成节点树位置 API 变化)
    """
    scene = bpy.context.scene

    # 多路径查找合成节点树 (Blender 5.x API 重构)
    tree = None
    if hasattr(scene, "node_tree") and scene.node_tree is not None:
        tree = scene.node_tree
    else:
        for vl in scene.view_layers:
            if hasattr(vl, "node_tree") and vl.node_tree is not None:
                tree = vl.node_tree
                break
    if tree is None:
        # 尝试创建 (4.x 方式)
        try:
            scene.use_nodes = True
            tree = scene.node_tree
        except Exception:
            # Blender 5.x 合成 API 变化 — 优雅降级 (EEVEE 自带 Bloom)
            return {"compositor": False, "note": "Blender 5.x 合成节点树 API 变化 — 跳过 Glare, 可用 EEVEE 内置 Bloom"}

    tree.nodes.clear()

    rl = tree.nodes.new("CompositorNodeRLayers")
    rl.location = (0, 0)

    glare = tree.nodes.new("CompositorNodeGlare")
    glare.location = (300, 0)
    glare.glare_type = "FOG_GLOW"
    glare.quality = "HIGH"
    glare.threshold = params.get("threshold", 0.5)
    glare.size = params.get("size", 8.0)
    glare.mix = 0.3

    comp = tree.nodes.new("CompositorNodeComposite")
    comp.location = (600, 0)

    tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], comp.inputs["Image"])

    return {"compositor": True, "glare": "FOG_GLOW",
            "threshold": glare.threshold, "size": glare.size}


# ─────────────────────────────────────────────────────────────
# 导出
# ─────────────────────────────────────────────────────────────

def export_fbx(params):
    """导出 FBX (正确轴/单位/嵌入纹理) — 大操作

    params: object_name (可选, 空=整个场景), filepath
    """
    filepath = params.get("filepath", "")
    if not filepath:
        raise ValueError("需要 filepath")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    obj_name = params.get("object_name")
    bpy.ops.object.select_all(action="DESELECT")
    if obj_name:
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            raise ValueError(f"对象不存在: {obj_name}")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    bpy.ops.export_scene.fbx(
        filepath=filepath,
        use_selection=bool(obj_name),
        apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Y",
        axis_up="Z",
        object_types={"MESH"},
        use_mesh_modifiers=True,
        mesh_smooth_type="OFF",
        path_mode="COPY",
        embed_textures=True,
        add_leaf_bones=False,
        bake_anim=False,
        use_triangles=params.get("use_triangles", False),
    )
    return {"filepath": filepath, "size": os.path.getsize(filepath)}


def export_gltf(params):
    """导出 glTF/GLB"""
    filepath = params.get("filepath", "")
    if not filepath:
        raise ValueError("需要 filepath")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    obj_name = params.get("object_name")

    bpy.ops.object.select_all(action="DESELECT")
    if obj_name:
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            raise ValueError(f"对象不存在: {obj_name}")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    bpy.ops.export_scene.gltf(
        filepath=filepath,
        use_selection=bool(obj_name),
        export_format="GLB" if filepath.lower().endswith(".glb") else "GLTF_SEPARATE",
        export_materials="EXPORT",
        export_yup=False,
    )
    return {"filepath": filepath, "size": os.path.getsize(filepath)}
