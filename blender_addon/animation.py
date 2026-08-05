"""动画原子命令 — 关键帧/约束/时间轴

设计参考 (2026 生态):
- sandraschi/blender-mcp 的 blender_animation (21 操作: 关键帧/约束/插值/NLA)
- XUJL-916/blender-mcp-enhanced (异步渲染队列)
- Evolink-AI Seedance 工作流 (相机运镜优先的 AI 影视流程)

handler 签名同 commands: def handler(params) -> dict
"""

import math

import bpy
from mathutils import Vector, Euler

_INTERPOLATION = {
    "bezier": "BEZIER", "linear": "LINEAR", "constant": "CONSTANT",
    "bounce": "BOUNCE", "elastic": "ELASTIC", "quad": "QUAD",
}

_CONSTRAINTS = {
    "track_to": "TRACK_TO", "copy_location": "COPY_LOCATION",
    "copy_rotation": "COPY_ROTATION", "copy_scale": "COPY_SCALE",
    "child_of": "CHILD_OF", "damped_track": "DAMPED_TRACK",
    "locked_track": "LOCKED_TRACK", "stretch_to": "STRETCH_TO",
    "follow_path": "FOLLOW_PATH", "limit_location": "LIMIT_LOCATION",
}


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


def _set_fcurve_interpolation(obj, data_path, interpolation):
    """设置指定属性通道的插值模式"""
    if interpolation not in _INTERPOLATION:
        return
    mode = _INTERPOLATION[interpolation]
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            if fc.data_path == data_path:
                for kp in fc.keyframe_points:
                    kp.interpolation = mode


def _insert_keyframe(obj, data_path, frame):
    obj.keyframe_insert(data_path=data_path, frame=frame)


# ─────────────────────────────────────────────────────────────
# 时间轴
# ─────────────────────────────────────────────────────────────

def set_frame_range(params):
    """设置动画帧范围: start, end, fps (可选)"""
    scene = bpy.context.scene
    if "fps" in params:
        scene.render.fps = params["fps"]
    start = int(params.get("start", scene.frame_start))
    end = int(params.get("end", scene.frame_end))
    scene.frame_start = start
    scene.frame_end = end
    return {"start": start, "end": end, "fps": scene.render.fps}


def set_frame(params):
    """跳转当前帧: frame"""
    scene = bpy.context.scene
    scene.frame_set(int(params.get("frame", 0)))
    return {"frame": scene.frame_current}


def get_frame_info(params):
    """获取时间轴信息"""
    scene = bpy.context.scene
    return {
        "current": scene.frame_current,
        "start": scene.frame_start,
        "end": scene.frame_end,
        "fps": scene.render.fps,
    }


# ─────────────────────────────────────────────────────────────
# 关键帧
# ─────────────────────────────────────────────────────────────

def insert_keyframe(params):
    """插入关键帧: name, frame, location/rotation(度)/scale"""
    obj = _get_object(params["name"])
    frame = int(params.get("frame", bpy.context.scene.frame_current))

    if "location" in params:
        obj.location = _vec3(params["location"])
        _insert_keyframe(obj, "location", frame)
    if "rotation" in params:
        # 输入为角度 (度), 转弧度
        obj.rotation_euler = Euler(_vec3(params["rotation"]) * (math.pi / 180), "XYZ")
        _insert_keyframe(obj, "rotation_euler", frame)
    if "scale" in params:
        obj.scale = _vec3(params["scale"], (1, 1, 1))
        _insert_keyframe(obj, "scale", frame)

    interpolation = params.get("interpolation")
    if interpolation:
        for dp in ("location", "rotation_euler", "scale"):
            if dp in params:
                _set_fcurve_interpolation(obj, dp, interpolation)

    return {"name": obj.name, "frame": frame}


def animate_location(params):
    """位置动画: name, start_frame, end_frame, from [x,y,z], to [x,y,z], interpolation"""
    obj = _get_object(params["name"])
    sf = int(params.get("start_frame", 0))
    ef = int(params.get("end_frame", sf + 30))
    obj.location = _vec3(params.get("from"))
    _insert_keyframe(obj, "location", sf)
    obj.location = _vec3(params.get("to"))
    _insert_keyframe(obj, "location", ef)
    _set_fcurve_interpolation(obj, "location", params.get("interpolation", "bezier"))
    return {"name": obj.name, "start_frame": sf, "end_frame": ef}


def animate_rotation(params):
    """旋转动画 (度): name, start_frame, end_frame, from [rx,ry,rz], to, interpolation"""
    obj = _get_object(params["name"])
    sf = int(params.get("start_frame", 0))
    ef = int(params.get("end_frame", sf + 30))
    obj.rotation_euler = Euler(_vec3(params.get("from")) * (math.pi / 180), "XYZ")
    _insert_keyframe(obj, "rotation_euler", sf)
    obj.rotation_euler = Euler(_vec3(params.get("to")) * (math.pi / 180), "XYZ")
    _insert_keyframe(obj, "rotation_euler", ef)
    _set_fcurve_interpolation(obj, "rotation_euler", params.get("interpolation", "bezier"))
    return {"name": obj.name, "start_frame": sf, "end_frame": ef}


def animate_scale(params):
    """缩放动画: name, start_frame, end_frame, from [x,y,z], to, interpolation"""
    obj = _get_object(params["name"])
    sf = int(params.get("start_frame", 0))
    ef = int(params.get("end_frame", sf + 30))
    obj.scale = _vec3(params.get("from"), (1, 1, 1))
    _insert_keyframe(obj, "scale", sf)
    obj.scale = _vec3(params.get("to"), (1, 1, 1))
    _insert_keyframe(obj, "scale", ef)
    _set_fcurve_interpolation(obj, "scale", params.get("interpolation", "bezier"))
    return {"name": obj.name, "start_frame": sf, "end_frame": ef}


def clear_animation(params):
    """清除动画: name (全部动画) 或 data_path"""
    obj = _get_object(params["name"])
    if obj.animation_data and obj.animation_data.action:
        if params.get("data_path"):
            for fc in list(obj.animation_data.action.fcurves):
                if fc.data_path == params["data_path"]:
                    obj.animation_data.action.fcurves.remove(fc)
            removed = params["data_path"]
        else:
            obj.animation_data.action = None
            removed = "all"
        return {"name": obj.name, "removed": removed}
    return {"name": obj.name, "removed": "none"}


# ─────────────────────────────────────────────────────────────
# 约束
# ─────────────────────────────────────────────────────────────

def add_constraint(params):
    """添加约束: name, constraint(类型), target, influence

    类型: track_to|damped_track|copy_location|copy_rotation|copy_scale|
          child_of|locked_track|stretch_to|follow_path|limit_location
    """
    obj = _get_object(params["name"])
    ctype = _CONSTRAINTS.get(params.get("constraint", ""))
    if ctype is None:
        raise ValueError(f"不支持的约束: {params.get('constraint')}")
    con = obj.constraints.new(type=ctype)
    con.name = params.get("constraint_name", f"{params['constraint']}")

    target_name = params.get("target")
    if target_name and hasattr(con, "target"):
        con.target = _get_object(target_name)
    if hasattr(con, "influence"):
        con.influence = params.get("influence", 1.0)

    if ctype == "FOLLOW_PATH":
        if target_name:
            # 路径约束需要设置路径偏移轴
            con.use_fixed_location = True
            con.forward_axis = params.get("forward_axis", "TRACK_NEGATIVE_Y")
            con.up_axis = params.get("up_axis", "UP_Z")
            obj.location = (0, 0, 0)
    return {"name": obj.name, "constraints": [c.name for c in obj.constraints]}


def remove_constraint(params):
    """移除约束: name, constraint"""
    obj = _get_object(params["name"])
    con = obj.constraints.get(params.get("constraint", ""))
    if con:
        obj.constraints.remove(con)
    return {"name": obj.name, "constraints": [c.name for c in obj.constraints]}


def list_constraints(params):
    """列出约束: name"""
    obj = _get_object(params["name"])
    return {"name": obj.name, "constraints": [c.name for c in obj.constraints]}


# ─────────────────────────────────────────────────────────────
# 物理 (刚体)
# ─────────────────────────────────────────────────────────────

def add_rigid_body(params):
    """添加刚体: name, type(active|passive), friction, mass, shape

    地面等静态物体用 type=passive, 动态物体用 type=active
    """
    obj = _get_object(params["name"])
    rb_type = params.get("type", "active")
    # 确保对象有网格数据
    if obj.type != "MESH":
        raise ValueError(f"刚体只支持网格对象: {obj.name}")

    rb = obj.rigid_body
    if rb is None:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.rigidbody.object_add(type=rb_type)
        rb = obj.rigid_body

    rb.friction = params.get("friction", 0.5)
    rb.restitution = params.get("restitution", 0.0)
    rb.mass = params.get("mass", 1.0)
    rb.collision_shape = params.get("shape", "CONVEX_HULL")

    return {"name": obj.name, "type": rb_type, "mass": rb.mass}


def setup_rigid_body_world(params):
    """配置物理世界: gravity, frame_start"""
    scene = bpy.context.scene
    if scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    world = scene.rigidbody_world
    g = params.get("gravity", [0, 0, -9.81])
    world.gravity = Vector(g)
    world.point_cache.frame_start = int(params.get("frame_start", 1))
    world.point_cache.frame_end = int(params.get("frame_end", 250))
    return {"gravity": list(world.gravity),
            "frame_start": world.point_cache.frame_start,
            "frame_end": world.point_cache.frame_end}


# ─────────────────────────────────────────────────────────────
# 渲染
# ─────────────────────────────────────────────────────────────

def render_animation(params):
    """渲染动画帧序列 — 必须在主线程执行 (bpy.ops.render 非主线程会崩溃)

    params:
        output_dir: 输出目录 (PNG)
        start/end: 帧范围 (默认整个时间轴)
        engine: cycles|eevee
        resolution_x/y: 分辨率
        samples: cycles 采样数
    """
    import os
    # 主线程执行 (队列模式), 用数据 API 避免 context 依赖
    scene = bpy.data.scenes[0]
    output_dir = params.get("output_dir", "")
    if not output_dir:
        raise ValueError("需要 output_dir")
    os.makedirs(output_dir, exist_ok=True)

    # 保存设置
    prev_engine = scene.render.engine
    prev_fmt = scene.render.image_settings.file_format
    prev_path = scene.render.filepath

    engine = params.get("engine", "eevee")
    # Blender 4.2=BLENDER_EEVEE_NEXT, 5.x=BLENDER_EEVEE — 枚举兼容
    if engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = int(params.get("samples", 64))
    else:
        scene.render.engine = "BLENDER_EEVEE"  # 5.x 名称 (4.2 曾用 _NEXT)
    scene.render.resolution_x = int(params.get("resolution_x", 1280))
    scene.render.resolution_y = int(params.get("resolution_y", 720))
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(output_dir, "frame_")

    start = int(params.get("start", scene.frame_start))
    end = int(params.get("end", scene.frame_end))

    rendered = []
    for frame in range(start, end + 1):
        scene.frame_set(frame)
        scene.render.filepath = os.path.join(output_dir, f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        rendered.append(os.path.join(output_dir, f"frame_{frame:04d}.png"))

    # 恢复设置
    scene.render.engine = prev_engine
    scene.render.image_settings.file_format = prev_fmt
    scene.render.filepath = prev_path

    return {"frames": len(rendered), "output_dir": output_dir,
            "start": start, "end": end, "files": rendered}
