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
