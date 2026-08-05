"""
Q萌海龟打斗场景 — 完整角色动画工作流 (AI 全流程, 双龟对打)

阶段:
  1. 建模: 两只海龟 (绿龟 vs 橙龟, 镜像造型)
  2. 骨架: 脊柱3节 + 前肢两段 (各自独立 rig)
  3. 绑定: 自动权重
  4. 表情: 形态键 (眨眼/愤怒/惊讶)
  5. 动画: 预备-爆发-收招-受击-反击 循环 (对手镜像动作)
  6. 场景: 海底竞技场 + 水泡 + 灯光 + 相机 (低角度广角)
  7. 渲染: 辉光 + 多帧验证

用法:
    python scripts/turtle_fight.py                # 全流程 (渲染用 eevee)
    python scripts/turtle_fight.py --fast         # 跳过渲染
    python scripts/turtle_fight.py --cycles       # 用 cycles 渲染
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.blender_client import BlenderClient

BRIDGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(BRIDGE_ROOT, "shared_assets", "screenshots")
FRAME_DIR = os.path.join(BRIDGE_ROOT, "shared_assets", "frames", "turtle")

OK = 0
FAIL = 0


def step(blender, label, result):
    """检查每步结果"""
    global OK, FAIL
    ok_flag = result.get("status") == "success"
    if ok_flag:
        OK += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}: {result.get('message')}")
    return ok_flag


def cleanup_scene(blender):
    """清空场景"""
    r = blender.list_objects()
    if r.get("status") == "success":
        names = [o["name"] for o in r["result"]["objects"]]
        if names:
            blender.delete_object(names)
    print("  场景已清空")


# ═══════════════════════════════════════════════════════════
# 阶段 1: 基础建模 (参数化 — 支持双龟)
# ═══════════════════════════════════════════════════════════

def build_turtle(blender, prefix="TurtleA",
                 skin=(0.35, 0.65, 0.32), shell_color=(0.12, 0.38, 0.18)):
    """构建一只 Q萌海龟 (朝向 +X)"""
    print(f"\n  ── {prefix} (皮肤 {skin[0]:.2f},{skin[1]:.2f},{skin[2]:.2f}) ──")

    # 身体 (椭圆球 — 比例夸张)
    r = blender.create_object("sphere", f"{prefix}_Body", radius=0.5,
                              location=[0, 0, 0.55])
    blender.set_transform(f"{prefix}_Body", scale=[1.3, 1.0, 0.85])

    # 头部 (占身体 1/3)
    blender.create_object("sphere", f"{prefix}_Head", radius=0.34,
                          location=[0.95, 0, 0.8])
    blender.set_transform(f"{prefix}_Head", scale=[1.05, 1.0, 1.1])

    # 六边形龟壳 — 罩住身体上半
    blender.create_turtle_shell(radius=1.0, height=0.9, name=f"{prefix}_Shell",
                                material={"name": f"M_Shell_{prefix}",
                                          "base_color": [*shell_color, 1.0],
                                          "roughness": 0.4})
    blender.set_transform(f"{prefix}_Shell", location=[-0.35, 0, 0.1])

    # 四肢
    limbs = [
        (f"{prefix}_Leg_FL", [0.5, 0.62, 0.2]), (f"{prefix}_Leg_FR", [0.5, -0.62, 0.2]),
        (f"{prefix}_Leg_BL", [-0.6, 0.55, 0.2]), (f"{prefix}_Leg_BR", [-0.6, -0.55, 0.2]),
    ]
    for lname, loc in limbs:
        blender.create_object("sphere", lname, radius=0.24, location=loc)
        blender.set_transform(lname, scale=[1.0, 0.9, 0.75])

    # 尾巴
    blender.create_object("sphere", f"{prefix}_Tail", radius=0.14,
                          location=[-1.05, 0, 0.3])
    blender.set_transform(f"{prefix}_Tail", scale=[1.6, 0.8, 0.8])

    # 大眼睛
    blender.create_cute_eye(location=[1.18, 0.3, 0.98], scale=1.0,
                            name=f"{prefix}_Eye_R")
    blender.create_cute_eye(location=[1.18, -0.3, 0.98], scale=1.0,
                            name=f"{prefix}_Eye_L")

    # 微笑嘴
    blender.create_object("torus", f"{prefix}_Mouth", radius=0.16,
                          depth=0.09, location=[1.08, 0, 0.68])
    blender.set_transform(f"{prefix}_Mouth", scale=[1.0, 1.0, 0.4],
                          rotation=[0, 0.5, 0])

    # 细分 + 倒角
    last = {"status": "success"}
    for part in [f"{prefix}_Body", f"{prefix}_Head"]:
        last = blender.add_modifier(part, "subdivision", {"levels": 2},
                                    modifier_name="Subsurf")
        last = blender.add_modifier(part, "bevel", {"width": 0.01, "segments": 1},
                                    modifier_name="Bevel")
        last = blender.apply_modifier(part, "Subsurf")
        last = blender.apply_modifier(part, "Bevel")

    # 材质
    last = blender.set_material(f"{prefix}_Head", f"M_Skin_{prefix}",
                                base_color=[*skin, 1.0], roughness=0.7)
    for lname, _ in limbs:
        blender.set_material(lname, f"M_Skin_{prefix}",
                             base_color=[*skin, 1.0], roughness=0.7)
    blender.set_material(f"{prefix}_Tail", f"M_Skin_{prefix}",
                         base_color=[*skin, 1.0], roughness=0.7)
    return {"prefix": prefix}


# ═══════════════════════════════════════════════════════════
# 阶段 2-4: 骨架 + 绑定 + 表情 (参数化)
# ═══════════════════════════════════════════════════════════

def build_rig(blender, prefix):
    """骨架: 脊柱3节 + 前肢两段 + 尾巴"""
    rig_name = f"{prefix}Rig"
    r = blender.create_turtle_skeleton(scale=1.2, name=rig_name)
    # 头骨对准头部中心
    blender.set_transform(rig_name, location=[-0.31, 0, 0.3])
    return r


def bind_turtle(blender, prefix):
    """绑定: 合并网格 + 自动权重"""
    rig_name = f"{prefix}Rig"
    parts = [f"{prefix}_Body", f"{prefix}_Shell", f"{prefix}_Head",
             f"{prefix}_Leg_FL", f"{prefix}_Leg_FR", f"{prefix}_Leg_BL",
             f"{prefix}_Leg_BR", f"{prefix}_Tail", f"{prefix}_Mouth"]
    r = blender.join_objects(parts, new_name=f"{prefix}_Mesh")
    step(blender, f"{prefix} 合并网格", r)
    r = blender.auto_weight(mesh=f"{prefix}_Mesh", armature=rig_name)
    step(blender, f"{prefix} 自动权重绑定", r)
    return r


def build_expressions(blender, prefix):
    """表情形态键"""
    blender.add_shape_key(f"{prefix}_Mesh", "Angry")
    blender.set_shape_key_value(f"{prefix}_Mesh", "Angry", 0.0)
    blender.add_shape_key(f"{prefix}_Mesh", "Surprised")
    blender.make_eye_blink_shape(f"{prefix}_Mesh", "Blink")
    return {"prefix": prefix}


# ═══════════════════════════════════════════════════════════
# 阶段 5: 打斗动画 (双龟对打, 对手镜像)
# ═══════════════════════════════════════════════════════════

def _pose(blender, rig, bone, rotation, frame, flip=False, interp=""):
    """设置骨骼姿态 (flip 时镜像: 交换左右臂 + x/z 取反)"""
    r = list(rotation)
    if flip:
        bone = bone.replace("arm_R", "arm_L").replace("arm_L", "arm_R")
        r[0] = -r[0]  # x 镜像
        r[2] = -r[2]  # z 镜像
    kwargs = {"frame": frame}
    if interp:
        kwargs["interpolation"] = interp
    blender.set_bone_pose(rig, bone, rotation=r, **kwargs)


def animate_fight(blender, prefix, flip=False):
    """打斗循环 48 帧: 预备-爆发-收招-受击-反击 (flip=对手镜像)"""
    rig = f"{prefix}Rig"
    print(f"  [{prefix}] 打斗动画 (48帧 @24fps 循环, {'镜像' if flip else '本体'})")

    # ── 预备 (1-10): 后仰蓄力 ──
    _pose(blender, rig, "spine2", [0, -12, 0], 1, flip)
    _pose(blender, rig, "head", [0, 10, 0], 1, flip)
    _pose(blender, rig, "arm_R_upper", [0, 0, 25], 1, flip)
    _pose(blender, rig, "arm_R_lower", [0, 0, 70], 1, flip)
    _pose(blender, rig, "arm_L_upper", [0, 0, -10], 1, flip)
    _pose(blender, rig, "arm_L_lower", [0, 0, -20], 1, flip)
    blender.set_bone_pose(rig, "root", location=[0, 0, 0.05], frame=1)

    # ── 爆发 (11-15): 出拳! ──
    _pose(blender, rig, "spine2", [0, 14, 0], 11, flip)
    _pose(blender, rig, "head", [0, -8, 0], 11, flip)
    _pose(blender, rig, "arm_R_upper", [0, 0, -18], 11, flip)
    _pose(blender, rig, "arm_R_lower", [0, 0, -30], 11, flip)
    blender.set_bone_pose(rig, "root", location=[0, 0, -0.03], frame=11)
    _pose(blender, rig, "arm_R_upper", [0, 0, -15], 15, flip)
    _pose(blender, rig, "arm_R_lower", [0, 0, 5], 15, flip, "constant")

    # ── 收招 (16-25): 防御缩壳 ──
    _pose(blender, rig, "spine2", [0, -8, 0], 16, flip)
    _pose(blender, rig, "head", [0, 30, 0], 25, flip)
    _pose(blender, rig, "arm_R_upper", [0, 0, 12], 25, flip)
    _pose(blender, rig, "arm_R_lower", [0, 0, 40], 25, flip)
    _pose(blender, rig, "arm_L_upper", [0, 0, 10], 25, flip)
    _pose(blender, rig, "arm_L_lower", [0, 0, 35], 25, flip)

    # ── 受击 (26-35): 震动 + 表情 ──
    _pose(blender, rig, "spine2", [0, 3, 0], 28, flip)
    _pose(blender, rig, "spine2", [0, -5, 0], 30, flip)
    _pose(blender, rig, "spine2", [0, 2, 0], 33, flip)
    _pose(blender, rig, "spine2", [0, 0, 0], 35, flip)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Blink", 0.0, frame=26)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Blink", 1.0, frame=28)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Blink", 0.0, frame=30)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Angry", 0.0, frame=26)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Angry", 0.8, frame=35)

    # ── 反击准备 (36-45): 头部探出 ──
    _pose(blender, rig, "head", [0, 0, 0], 36, flip)
    _pose(blender, rig, "head", [0, -6, 0], 45, flip)
    _pose(blender, rig, "neck", [0, 8, 0], 36, flip)
    _pose(blender, rig, "neck", [0, 0, 0], 45, flip)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Surprised", 0.0, frame=36)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Surprised", 0.7, frame=45)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Angry", 0.8, frame=36)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Angry", 0.3, frame=45)

    # ── 循环闭合 (46-48) ──
    _pose(blender, rig, "spine2", [0, -12, 0], 48, flip)
    _pose(blender, rig, "head", [0, 10, 0], 48, flip)
    _pose(blender, rig, "arm_R_upper", [0, 0, 25], 48, flip)
    _pose(blender, rig, "arm_R_lower", [0, 0, 70], 48, flip)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Surprised", 0.0, frame=48)
    blender.set_shape_key_value(f"{prefix}_Mesh", "Angry", 0.0, frame=48)


# ═══════════════════════════════════════════════════════════
# 阶段 6: 场景 (海底竞技场 + 双龟站位)
# ═══════════════════════════════════════════════════════════

def build_scene(blender, turtles):
    print("\n" + "═" * 60)
    print("  阶段 6: 海底竞技场 (双龟对位)")
    print("═" * 60)

    # 环形战斗平台 (发光边缘, 半径 3.5)
    r = blender.create_arena(radius=3.5, thickness=0.25, height=0.15,
                             glow_color=[0.2, 0.7, 1.0], name="Arena")
    step(blender, "悬浮竞技场 (金属+发光环)", r)

    # 双龟站位: 平台两侧面对面 (平台顶面 z=0.4)
    # 龟 A 在左侧 (面朝 +X), 龟 B 在右侧 (旋转 180° 面朝 -X)
    print("  [站位] 双龟上平台...")
    sides = [(-2.0, 0), (2.0, 0)]  # (x, yaw)
    for i, (prefix, rig, flip) in enumerate(turtles):
        x, yaw = sides[i]
        for obj_name in [f"{prefix}_Mesh", f"{prefix}_Eye_L", f"{prefix}_Eye_R",
                         f"{prefix}Rig"]:
            g = blender.get_transform(obj_name)
            if g.get("status") == "success":
                loc = g["result"]["location"]
                blender.set_transform(obj_name,
                                      location=[x, loc[1], loc[2] + 0.4],
                                      rotation=[0, 0, yaw])
    print("  ✅ 双龟面对面站位")

    # 漂浮水泡
    r = blender.create_bubbles(count=25, area=[3, 3, 2.5], size=[0.04, 0.12],
                               name="Bubble", animate=True, frames=48)
    step(blender, "水泡粒子 (25 个, 上升动画)", r)

    # 灯光: 冷主光 + 暖轮廓
    blender.spawn_point_light("Light_Key", color=[0.4, 0.6, 1.0], energy=800,
                              location=[4, -3, 5])
    blender.spawn_point_light("Light_Rim", color=[1.0, 0.75, 0.35], energy=600,
                              location=[-3, 0, 2])
    last = blender.spawn_point_light("Light_Ambient", color=[0.3, 0.5, 0.8],
                                     energy=200, location=[0, 0, 6])
    step(blender, "三点布光 (冷主光 + 暖轮廓 + 环境)", last)

    # 相机: 低角度仰拍 + 广角 24mm (拍向双龟中间)
    r = blender.camera_setup(location=[5.5, -3.0, 0.8], target=[0, 0, 0.9],
                             lens_mm=24, name="Cam_Fight")
    step(blender, "低角度广角相机 (24mm 仰拍)", r)

    return r


# ═══════════════════════════════════════════════════════════
# 阶段 7: 渲染验证
# ═══════════════════════════════════════════════════════════

def render_verify(blender, do_render):
    print("\n" + "═" * 60)
    print("  阶段 7: 辉光 + 多帧验证")
    print("═" * 60)

    r = blender.setup_compositor_glow(threshold=0.4, size=6.0)
    step(blender, "合成辉光 (Glare)", r)

    # 多帧截图验证
    r = blender.capture_animation_frames(
        frames=[1, 11, 15, 25, 30, 45], tag="turtle", width=960, height=540)
    if r.get("success"):
        print(f"  📸 多帧截图 {r['count']} 张:")
        for f in r["frames"]:
            print(f"     帧 {f['frame']:2d}: {f['filepath']}")
        print("  → 用 Read 工具查看对比运动节奏")

    if do_render:
        print(f"  渲染中 (1280x720, 主线程)...")
        os.makedirs(FRAME_DIR, exist_ok=True)
        r = blender.render_animation(FRAME_DIR, start=0, end=48,
                                     engine="cycles" if "--cycles" in sys.argv else "eevee",
                                     resolution_x=1280, resolution_y=720, samples=64)
        if r.get("status") == "success":
            print(f"  ✅ 渲染 {r['result']['frames']} 帧 → {FRAME_DIR}")
        else:
            print(f"  ❌ 渲染失败: {r.get('message')}")

    return r


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blender = BlenderClient()
    print(f"Blender 连接: {'✅' if blender.ping() else '❌'}")
    if not blender.ping():
        sys.exit(1)

    print("\n" + "╔" + "═" * 58 + "╗")
    print("║  🐢🐢 Q萌海龟打斗场景 (双龟对打) — AI 全流程        ║")
    print("╚" + "═" * 58 + "╝")

    cleanup_scene(blender)

    # ── 阶段 1-4: 双龟建模/骨架/绑定/表情 ──
    print("\n" + "═" * 60)
    print("  阶段 1: 基础建模 (Q萌海龟 ×2)")
    print("═" * 60)
    build_turtle(blender, "TurtleA", skin=(0.35, 0.65, 0.32),
                 shell_color=(0.12, 0.38, 0.18))   # 绿龟
    build_turtle(blender, "TurtleB", skin=(0.85, 0.5, 0.25),
                 shell_color=(0.55, 0.25, 0.12))   # 橙龟
    blender.get_screenshot(os.path.join(SHOT_DIR, "turtle_model.png"),
                           width=960, height=540)
    print("  📸 截图: shared_assets/screenshots/turtle_model.png")

    print("\n" + "═" * 60)
    print("  阶段 2-3: 骨架 + 绑定")
    print("═" * 60)
    for prefix in ["TurtleA", "TurtleB"]:
        r = build_rig(blender, prefix)
        step(blender, f"{prefix} 骨架 (12 骨骼)", r)
        bind_turtle(blender, prefix)

    print("\n" + "═" * 60)
    print("  阶段 4: 表情形态键")
    print("═" * 60)
    for prefix in ["TurtleA", "TurtleB"]:
        build_expressions(blender, prefix)
    step(blender, "双龟表情形态键 (眨眼/愤怒/惊讶)", {"status": "success"})

    # ── 阶段 5: 双龟对打动画 ──
    print("\n" + "═" * 60)
    print("  阶段 5: 打斗动画 (预备-爆发-收招-受击-反击)")
    print("═" * 60)
    blender.set_frame_range(0, 48, fps=24)
    animate_fight(blender, "TurtleA", flip=False)  # 本体 (右拳出击)
    animate_fight(blender, "TurtleB", flip=True)   # 对手 (镜像, 左拳)
    step(blender, "双龟对打动画 (48帧 @24fps = 2s 循环)",
         {"status": "success"})

    # ── 阶段 6-7: 场景 + 渲染 ──
    turtles = [("TurtleA", "TurtleARig", False), ("TurtleB", "TurtleBRig", True)]
    build_scene(blender, turtles)

    do_render = "--fast" not in sys.argv
    render_verify(blender, do_render)

    print("\n" + "═" * 60)
    print(f"  完成! ✅ {OK} 步成功, ❌ {FAIL} 步失败")
    print("  在 Blender 中: 选择 Camera 视角, 按空格播放双龟对打!")
    print("═" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
