"""骨架/绑定/形态键命令 — 角色动画核心

支持:
- 骨骼链创建 (脊柱/四肢/尾巴), 前肢两段 (上臂+前臂)
- 骨骼姿态控制 + 关键帧 (pose_bone.rotation_euler)
- 自动权重绑定 (Ctrl+P ARMATURE_AUTO)
- 形态键 (shape keys): 眨眼/愤怒/惊讶等表情
"""

import math

import bpy
from mathutils import Vector, Euler


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


# ─────────────────────────────────────────────────────────────
# 骨架创建
# ─────────────────────────────────────────────────────────────

def create_armature(params):
    """创建骨架 (骨骼链)

    params:
        name: 骨架名
        bones: 骨骼列表 [
            {name, head [x,y,z], tail [x,y,z], parent (骨骼名, 空=根),
             roll (度, 可选)}
        ]
        display: xray|wire (显示模式, 可选)
    """
    bones = params.get("bones", [])
    if not bones:
        raise ValueError("需要 bones 列表")
    name = params.get("name", "Armature")

    arm_data = bpy.data.armatures.new(name)
    arm_data.display_type = "OCTAHEDRAL"
    if params.get("display") == "xray":
        arm_data.show_in_front = True

    arm = bpy.data.objects.new(name, arm_data)
    bpy.context.collection.objects.link(arm)

    # 编辑模式创建骨骼
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for b in bones:
            bone = arm_data.edit_bones.new(b["name"])
            bone.head = Vector(b.get("head", [0, 0, 0]))
            bone.tail = Vector(b.get("tail", [0, 0, 1]))
            if b.get("parent"):
                parent = arm_data.edit_bones.get(b["parent"])
                if parent:
                    bone.parent = parent
                    bone.use_connect = False
            if b.get("roll"):
                bone.roll = math.radians(b["roll"])
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")

    return {"name": arm.name, "bones": [b["name"] for b in bones]}


def create_turtle_skeleton(params):
    """海龟骨架预设 — 根骨 + 脊柱3节 + 颈 + 头 + 四肢(前肢两段) + 尾巴

    params:
        name, scale (缩放, 默认1), origin [x,y,z]
    """
    s = params.get("scale", 1.0)
    ox, oy, oz = params.get("origin", [0, 0, 0])
    n = params.get("name", "TurtleRig")
    f = lambda v: [v[0] * s + ox, v[1] * s + oy, v[2] * s + oz]

    # 海龟朝向 +X (头朝 +X), 壳中心在原点
    bones = [
        # 根骨 (壳中心, 底部)
        {"name": "root", "head": f([-0.1, 0, 0.3]), "tail": f([0.1, 0, 0.3])},
        # 脊柱 3 节 (向后上弯曲的链条)
        {"name": "spine1", "head": f([0.1, 0, 0.3]), "tail": f([0.3, 0, 0.45]), "parent": "root"},
        {"name": "spine2", "head": f([0.3, 0, 0.45]), "tail": f([0.55, 0, 0.5]), "parent": "spine1"},
        {"name": "spine3", "head": f([0.55, 0, 0.5]), "tail": f([0.8, 0, 0.45]), "parent": "spine2"},
        # 颈部
        {"name": "neck", "head": f([0.8, 0, 0.45]), "tail": f([1.05, 0, 0.42]), "parent": "spine3"},
        # 头部
        {"name": "head", "head": f([1.05, 0, 0.42]), "tail": f([1.35, 0, 0.48]), "parent": "neck"},
        # 前肢 (两段: 上臂 + 前臂), 左右各一, 壳侧前方
        {"name": "arm_L_upper", "head": f([0.35, 0.45, 0.3]), "tail": f([0.55, 0.8, 0.28]), "parent": "root", "roll": 90},
        {"name": "arm_L_lower", "head": f([0.55, 0.8, 0.28]), "tail": f([0.65, 1.1, 0.25]), "parent": "arm_L_upper", "roll": 90},
        {"name": "arm_R_upper", "head": f([0.35, -0.45, 0.3]), "tail": f([0.55, -0.8, 0.28]), "parent": "root", "roll": -90},
        {"name": "arm_R_lower", "head": f([0.55, -0.8, 0.28]), "tail": f([0.65, -1.1, 0.25]), "parent": "arm_R_upper", "roll": -90},
        # 后肢 (单段)
        {"name": "leg_L", "head": f([-0.5, 0.4, 0.3]), "tail": f([-0.7, 0.7, 0.2]), "parent": "root"},
        {"name": "leg_R", "head": f([-0.5, -0.4, 0.3]), "tail": f([-0.7, -0.7, 0.2]), "parent": "root"},
        # 尾巴
        {"name": "tail", "head": f([-0.9, 0, 0.35]), "tail": f([-1.3, 0, 0.3]), "parent": "root"},
    ]

    return create_armature({"name": n, "bones": bones, "display": "xray"})


# ─────────────────────────────────────────────────────────────
# 骨骼姿态 + 关键帧
# ─────────────────────────────────────────────────────────────

def set_bone_pose(params):
    """设置骨骼姿态: name(骨架), bone, rotation(度, 欧拉)

    params:
        name: 骨架对象名
        bone: 骨骼名
        rotation: [rx, ry, rz] 度
        location: [x,y,z] 可选 (局部)
        frame: 可选, 同时插关键帧
        interpolation: 可选
    """
    arm = _get_object(params["name"])
    if arm.type != "ARMATURE":
        raise ValueError(f"不是骨架: {arm.name}")
    bone_name = params.get("bone", "")
    if bone_name not in arm.pose.bones:
        raise ValueError(f"骨骼不存在: {bone_name}")
    pb = arm.pose.bones[bone_name]

    if "rotation" in params:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = Euler(_vec3(params["rotation"]) * (math.pi / 180), "XYZ")
    if "location" in params:
        pb.location = _vec3(params["location"])

    if params.get("frame") is not None:
        frame = int(params["frame"])
        if "rotation" in params:
            pb.keyframe_insert(data_path="rotation_euler", frame=frame)
        if "location" in params:
            pb.keyframe_insert(data_path="location", frame=frame)
        interp = params.get("interpolation")
        if interp and arm.animation_data and arm.animation_data.action:
            mode = {"bezier": "BEZIER", "linear": "LINEAR",
                    "constant": "CONSTANT", "bounce": "BOUNCE"}.get(interp, "BEZIER")
            for fc in arm.animation_data.action.fcurves:
                if "rotation_euler" in fc.data_path or "location" in fc.data_path:
                    for kp in fc.keyframe_points:
                        if kp.co.x == frame:
                            kp.interpolation = mode
    return {"bone": bone_name, "rotation": list(pb.rotation_euler),
            "location": list(pb.location)}


def get_bone_pose(params):
    """获取骨骼姿态: name, bone"""
    arm = _get_object(params["name"])
    pb = arm.pose.bones[params.get("bone", "")]
    return {"bone": pb.name,
            "rotation": [math.degrees(v) for v in pb.rotation_euler],
            "location": list(pb.location)}


def reset_bone_pose(params):
    """重置骨骼姿态: name, bone (清空旋转/位移)"""
    arm = _get_object(params["name"])
    pb = arm.pose.bones[params.get("bone", "")]
    pb.rotation_euler = Euler((0, 0, 0), "XYZ")
    pb.location = Vector((0, 0, 0))
    return {"bone": pb.name, "reset": True}


def clear_pose_animation(params):
    """清除整个骨架的动画: name"""
    arm = _get_object(params["name"])
    if arm.animation_data and arm.animation_data.action:
        arm.animation_data.action = None
    return {"name": arm.name, "cleared": True}


# ─────────────────────────────────────────────────────────────
# 绑定 (自动权重)
# ─────────────────────────────────────────────────────────────

def auto_weight(params):
    """自动权重绑定: mesh(模型), armature(骨架)

    params:
        mesh: 模型对象名
        armature: 骨架对象名
        clean_weights: 是否清理权重 (可选, 默认 True)
    """
    mesh = _get_object(params["mesh"])
    arm = _get_object(params["armature"])
    if mesh.type != "MESH":
        raise ValueError(f"绑定目标必须是网格: {mesh.name}")
    if arm.type != "ARMATURE":
        raise ValueError(f"必须是骨架: {arm.name}")

    # 顺序: 先选模型, 再选骨架, 最后激活骨架
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")

    # 清理权重 (可选)
    if params.get("clean_weights", True):
        bpy.context.view_layer.objects.active = mesh
        bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
        bpy.ops.paint.weight_gradient()  # 触发权重更新
        bpy.ops.object.mode_set(mode="OBJECT")

    return {"mesh": mesh.name, "armature": arm.name, "parented": True}


# ─────────────────────────────────────────────────────────────
# 形态键 (表情)
# ─────────────────────────────────────────────────────────────

def add_shape_key(params):
    """添加形态键: name(对象), shape_name, 模式

    params:
        mode: base(基础) | relative(相对, 默认) | absolute
    """
    obj = _get_object(params["name"])
    if obj.type != "MESH":
        raise ValueError(f"形态键只支持网格: {obj.name}")
    shape_name = params.get("shape_name", "")
    if not shape_name:
        raise ValueError("需要 shape_name")

    mode = params.get("mode", "RELATIVE")
    # 基础键 (如果有的话先建)
    if not obj.data.shape_keys:
        obj.shape_key_add(name="Basis")
    sk = obj.shape_key_add(name=shape_name)
    return {"object": obj.name, "shape_key": sk.name,
            "existing": [sk2.name for sk2 in obj.data.shape_keys.key_blocks]}


def set_shape_key_value(params):
    """设置形态键值: name, shape_name, value (0-1), frame (可选, 同时插关键帧)"""
    obj = _get_object(params["name"])
    if not obj.data.shape_keys:
        raise ValueError(f"对象没有形态键: {obj.name}")
    sk = obj.data.shape_keys.key_blocks.get(params.get("shape_name", ""))
    if sk is None:
        raise ValueError(f"形态键不存在: {params.get('shape_name')}")
    value = float(params.get("value", 0.0))
    sk.value = max(0.0, min(1.0, value))
    if params.get("frame") is not None:
        sk.keyframe_insert(data_path="value", frame=int(params["frame"]))
    return {"shape_key": sk.name, "value": round(sk.value, 3)}


def make_eye_blink_shape(params):
    """制作眨眼形态键: 缩 Z 轴挤压上眼睑区域

    params: name(对象), shape_name (默认 Blink)
    使用网格变形: 把上半球顶点向 Z 下压
    """
    obj = _get_object(params["name"])
    shape_name = params.get("shape_name", "Blink")
    if not obj.data.shape_keys:
        obj.shape_key_add(name="Basis")
    sk = obj.shape_key_add(name=shape_name)
    # 编辑上半部顶点: 所有 z > 0.3*max_z 的顶点 z *= 0.15 (挤压)
    max_z = max(v.co.z for v in obj.data.vertices)
    for v, s in zip(obj.data.vertices, sk.data):
        if v.co.z > max_z * 0.2:
            s.co.z = v.co.z * 0.12
    sk.value = 0.0
    return {"shape_key": shape_name, "vertices": len(sk.data)}
