"""
Q萌海龟打斗场景 — 完整角色动画工作流 (AI 全流程)

阶段:
  1. 建模: 头部/龟壳(六边形)/四肢/尾巴/大眼睛
  2. 骨架: 脊柱3节 + 颈 + 头 + 前肢两段 + 后肢 + 尾巴
  3. 绑定: 自动权重
  4. 表情: 形态键 (眨眼/愤怒)
  5. 动画: 预备-爆发-收招-受击-反击 循环 (骨骼姿态关键帧)
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
    """清空场景 (保留相机/灯光重建)"""
    r = blender.list_objects()
    if r.get("status") == "success":
        names = [o["name"] for o in r["result"]["objects"]]
        if names:
            blender.delete_object(names)
    print("  场景已清空")


# ═══════════════════════════════════════════════════════════
# 阶段 1: 基础建模 (Q萌造型)
# ═══════════════════════════════════════════════════════════

def build_turtle(blender):
    print("\n" + "═" * 60)
    print("  阶段 1: 基础建模 (Q萌海龟)")
    print("═" * 60)

    # 身体 (椭圆球 — 比例夸张: 身体圆润)
    r = blender.create_object("sphere", "Turtle_Body", radius=0.5,
                              location=[0, 0, 0.55])
    step(blender, "身体 (半径 0.5)", r)
    r = blender.set_transform("Turtle_Body", scale=[1.3, 1.0, 0.85])
    step(blender, "身体椭圆化 (萌感)", r)

    # 头部 (占身体 1/3, 超大比例)
    r = blender.create_object("sphere", "Turtle_Head", radius=0.34,
                              location=[0.75, 0, 0.75])
    step(blender, "头部 (大比例)", r)
    blender.set_transform("Turtle_Head", scale=[1.05, 1.0, 1.1])

    # 六边形龟壳
    r = blender.create_turtle_shell(radius=0.75, height=0.5,
                                    name="Turtle_Shell",
                                    material={"name": "M_Shell_Deep",
                                              "base_color": [0.12, 0.38, 0.18, 1.0],
                                              "roughness": 0.4})
    step(blender, "龟壳 (六边形鳞片 + 裙边)", r)
    blender.set_transform("Turtle_Shell", location=[-0.1, 0, 0.5],
                          scale=[1.0, 1.0, 0.95])

    # 四肢 (短粗圆润 — 萌点)
    limbs = [
        ("Leg_FL", [0.35, 0.5, 0.35]), ("Leg_FR", [0.35, -0.5, 0.35]),
        ("Leg_BL", [-0.45, 0.45, 0.35]), ("Leg_BR", [-0.45, -0.45, 0.35]),
    ]
    for lname, loc in limbs:
        r = blender.create_object("sphere", lname, radius=0.22, location=loc)
        blender.set_transform(lname, scale=[0.9, 1.1, 0.8])

    # 尾巴
    r = blender.create_object("sphere", "Turtle_Tail", radius=0.13,
                              location=[-0.75, 0, 0.3])
    blender.set_transform("Turtle_Tail", scale=[1.4, 0.8, 0.8])

    # 大眼睛 (萌点核心 — 超大 + 发光)
    r = blender.create_cute_eye(location=[0.98, 0.28, 0.92], scale=1.0,
                                name="Eye_R")
    r = blender.create_cute_eye(location=[0.98, -0.28, 0.92], scale=1.0,
                                name="Eye_L")
    step(blender, "大眼睛 (白眼球+瞳孔+高光)", r)

    # 微笑嘴 (扁椭球)
    r = blender.create_object("torus", "Turtle_Mouth", radius=0.16,
                              depth=0.09, location=[0.88, 0, 0.62])
    blender.set_transform("Turtle_Mouth", scale=[1.0, 1.0, 0.4],
                          rotation=[0, 0.5, 0])
    step(blender, "微笑嘴", r)

    # 细分曲面 + 倒角 (整体圆润)
    last = {"status": "success"}
    for part in ["Turtle_Body", "Turtle_Head"]:
        last = blender.add_modifier(part, "subdivision", {"levels": 2})
        last = blender.add_modifier(part, "bevel", {"width": 0.01, "segments": 1})
        last = blender.apply_modifier(part, "Subsurf")
        last = blender.apply_modifier(part, "Bevel")
    step(blender, "细分曲面 + 倒角 (圆润质感)", last)

    # 材质
    blender.set_material("Turtle_Head", "M_Skin_Light",
                         base_color=[0.35, 0.65, 0.32, 1.0], roughness=0.7)
    for lname, _ in limbs:
        blender.set_material(lname, "M_Skin_Light",
                             base_color=[0.35, 0.65, 0.32, 1.0], roughness=0.7)
    last = blender.set_material("Turtle_Tail", "M_Skin_Light",
                                base_color=[0.35, 0.65, 0.32, 1.0], roughness=0.7)
    step(blender, "皮肤材质 (浅绿哑光)", last)

    # 截图验证
    blender.get_screenshot(os.path.join(SHOT_DIR, "turtle_model.png"),
                           width=960, height=540)
    print("  📸 截图: shared_assets/screenshots/turtle_model.png")


# ═══════════════════════════════════════════════════════════
# 阶段 2: 骨架
# ═══════════════════════════════════════════════════════════

def build_rig(blender):
    print("\n" + "═" * 60)
    print("  阶段 2: 骨架 (脊柱3节 + 前肢两段 + 尾巴)")
    print("═" * 60)

    # 缩放适配: 海龟身体 ~1.6m, 骨架 scale=1.6
    r = blender.create_turtle_skeleton(scale=1.6, name="TurtleRig")
    step(blender, "海龟骨架 (12 骨骼)", r)

    # 对齐骨架到身体中心
    blender.set_transform("TurtleRig", location=[-0.1, 0, 0.15])
    return r


# ═══════════════════════════════════════════════════════════
# 阶段 3: 绑定
# ═══════════════════════════════════════════════════════════

def bind_turtle(blender):
    print("\n" + "═" * 60)
    print("  阶段 3: 绑定 (自动权重)")
    print("═" * 60)

    # 合并身体部件为一个网格 (壳/头/四肢/尾巴 — 除眼睛)
    parts = ["Turtle_Body", "Turtle_Shell", "Turtle_Head",
             "Leg_FL", "Leg_FR", "Leg_BL", "Leg_BR", "Turtle_Tail",
             "Turtle_Mouth"]
    r = blender.join_objects(parts, new_name="Turtle_Mesh")
    step(blender, "合并网格 (9 部件)", r)

    r = blender.auto_weight(mesh="Turtle_Mesh", armature="TurtleRig")
    step(blender, "自动权重绑定 (Ctrl+P)", r)

    return r


# ═══════════════════════════════════════════════════════════
# 阶段 4: 表情形态键
# ═══════════════════════════════════════════════════════════

def build_expressions(blender):
    print("\n" + "═" * 60)
    print("  阶段 4: 表情形态键 (眨眼/愤怒/惊讶)")
    print("═" * 60)

    r = blender.add_shape_key("Turtle_Mesh", "Angry")
    step(blender, "愤怒形态键 (眉毛下压)", r)
    r = blender.set_shape_key_value("Turtle_Mesh", "Angry", 0.0)
    step(blender, "愤怒值初始化 0", r)

    r = blender.add_shape_key("Turtle_Mesh", "Surprised")
    step(blender, "惊讶形态键", r)

    r = blender.make_eye_blink_shape("Turtle_Mesh", "Blink")
    step(blender, "眨眼形态键 (上眼睑下压)", r)

    return r


# ═══════════════════════════════════════════════════════════
# 阶段 5: 打斗动画 (预备-爆发-收招-受击-反击 循环)
# ═══════════════════════════════════════════════════════════

def animate_fight(blender):
    print("\n" + "═" * 60)
    print("  阶段 5: 打斗动画 (预备-爆发-收招-受击-反击)")
    print("═" * 60)
    rig = "TurtleRig"

    # 时间轴 48 帧 @24fps = 2 秒循环
    blender.set_frame_range(0, 48, fps=24)

    # ── 预备 (1-10): 后仰蓄力 ──
    print("  [预备 1-10帧] 后仰蓄力")
    blender.set_bone_pose(rig, "spine2", rotation=[0, -12, 0], frame=1)
    blender.set_bone_pose(rig, "head", rotation=[0, 10, 0], frame=1)
    # 右臂后拉 (上臂外旋 + 前臂弯曲)
    blender.set_bone_pose(rig, "arm_R_upper", rotation=[0, 0, 25], frame=1)
    blender.set_bone_pose(rig, "arm_R_lower", rotation=[0, 0, 70], frame=1)
    blender.set_bone_pose(rig, "arm_L_upper", rotation=[0, 0, -10], frame=1)
    blender.set_bone_pose(rig, "arm_L_lower", rotation=[0, 0, -20], frame=1)
    blender.set_bone_pose(rig, "root", location=[0, 0, 0.05], frame=1)

    # ── 爆发 (11-15): 出拳! ──
    print("  [爆发 11-15帧] 出拳!!")
    blender.set_bone_pose(rig, "spine2", rotation=[0, 14, 0], frame=11)
    blender.set_bone_pose(rig, "head", rotation=[0, -8, 0], frame=11)
    blender.set_bone_pose(rig, "arm_R_upper", rotation=[0, 0, -18], frame=11)
    blender.set_bone_pose(rig, "arm_R_lower", rotation=[0, 0, -30], frame=11)
    blender.set_bone_pose(rig, "root", location=[0, 0, -0.03], frame=11)
    blender.set_bone_pose(rig, "arm_R_upper", rotation=[0, 0, -15], frame=15)
    blender.set_bone_pose(rig, "arm_R_lower", rotation=[0, 0, 5], frame=15,
                          interpolation="constant")

    # ── 收招 (16-25): 缓慢收回 + 缩壳 ──
    print("  [收招 16-25帧] 防御缩壳")
    blender.set_bone_pose(rig, "spine2", rotation=[0, -8, 0], frame=16)
    blender.set_bone_pose(rig, "head", rotation=[0, 30, 0], frame=25)
    blender.set_bone_pose(rig, "arm_R_upper", rotation=[0, 0, 12], frame=25)
    blender.set_bone_pose(rig, "arm_R_lower", rotation=[0, 0, 40], frame=25)
    blender.set_bone_pose(rig, "arm_L_upper", rotation=[0, 0, 10], frame=25)
    blender.set_bone_pose(rig, "arm_L_lower", rotation=[0, 0, 35], frame=25)

    # ── 受击 (26-35): 龟壳震动 + 表情谨慎 ──
    print("  [受击 26-35帧] 震动 + 眨眼")
    blender.set_bone_pose(rig, "spine2", rotation=[0, 3, 0], frame=28)
    blender.set_bone_pose(rig, "spine2", rotation=[0, -5, 0], frame=30)
    blender.set_bone_pose(rig, "spine2", rotation=[0, 2, 0], frame=33)
    blender.set_bone_pose(rig, "spine2", rotation=[0, 0, 0], frame=35)
    # 眨眼 (形态键 1 帧)
    blender.set_shape_key_value("Turtle_Mesh", "Blink", 0.0, frame=26)
    blender.set_shape_key_value("Turtle_Mesh", "Blink", 1.0, frame=28)
    blender.set_shape_key_value("Turtle_Mesh", "Blink", 0.0, frame=30)
    # 愤怒表情渐强
    blender.set_shape_key_value("Turtle_Mesh", "Angry", 0.0, frame=26)
    blender.set_shape_key_value("Turtle_Mesh", "Angry", 0.8, frame=35)

    # ── 反击准备 (36-45): 头部探出 + 眼睛睁大 ──
    print("  [反击 36-45帧] 头部探出")
    blender.set_bone_pose(rig, "head", rotation=[0, 0, 0], frame=36)
    blender.set_bone_pose(rig, "head", rotation=[0, -6, 0], frame=45)
    blender.set_bone_pose(rig, "neck", rotation=[0, 8, 0], frame=36)
    blender.set_bone_pose(rig, "neck", rotation=[0, 0, 0], frame=45)
    blender.set_shape_key_value("Turtle_Mesh", "Surprised", 0.0, frame=36)
    blender.set_shape_key_value("Turtle_Mesh", "Surprised", 0.7, frame=45)
    blender.set_shape_key_value("Turtle_Mesh", "Angry", 0.8, frame=36)
    blender.set_shape_key_value("Turtle_Mesh", "Angry", 0.3, frame=45)

    # ── 循环闭合 (46-48): 回到预备姿态 ──
    print("  [循环闭合 46-48帧]")
    blender.set_bone_pose(rig, "spine2", rotation=[0, -12, 0], frame=48)
    blender.set_bone_pose(rig, "head", rotation=[0, 10, 0], frame=48)
    blender.set_bone_pose(rig, "arm_R_upper", rotation=[0, 0, 25], frame=48)
    blender.set_bone_pose(rig, "arm_R_lower", rotation=[0, 0, 70], frame=48)
    blender.set_shape_key_value("Turtle_Mesh", "Surprised", 0.0, frame=48)
    blender.set_shape_key_value("Turtle_Mesh", "Angry", 0.0, frame=48)

    print("  ✅ 动画完成 (48 帧 @24fps = 2s 循环)")


# ═══════════════════════════════════════════════════════════
# 阶段 6: 场景 (海底竞技场)
# ═══════════════════════════════════════════════════════════

def build_scene(blender):
    print("\n" + "═" * 60)
    print("  阶段 6: 海底竞技场")
    print("═" * 60)

    # 环形战斗平台 (发光边缘)
    r = blender.create_arena(radius=3.0, thickness=0.25, height=0.15,
                             glow_color=[0.2, 0.7, 1.0], name="Arena")
    step(blender, "悬浮竞技场 (金属+发光环)", r)

    # 漂浮水泡 (上升动画)
    r = blender.create_bubbles(count=25, area=[3, 3, 2.5], size=[0.04, 0.12],
                               name="Bubble", animate=True, frames=48)
    step(blender, "水泡粒子 (25 个, 上升动画)", r)

    # 灯光: 主光冷蓝 + 轮廓光暖黄 (冷暖对比)
    r = blender.create_object("empty", "Light_Key", location=[4, -3, 5])
    blender.spawn_point_light("Light_Key", color=[0.4, 0.6, 1.0], energy=800)
    r = blender.create_object("empty", "Light_Rim", location=[-3, 0, 2])
    blender.spawn_point_light("Light_Rim", color=[1.0, 0.75, 0.35], energy=600)
    r = blender.create_object("empty", "Light_Ambient", location=[0, 0, 6])
    last = blender.spawn_point_light("Light_Ambient", color=[0.3, 0.5, 0.8], energy=200)
    step(blender, "三点布光 (冷主光 + 暖轮廓 + 环境)", last)

    # 相机: 低角度仰拍 + 广角 24mm
    r = blender.camera_setup(location=[4.5, -2.5, 0.8], target=[0.3, 0, 0.9],
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

    # 合成辉光
    r = blender.setup_compositor_glow(threshold=0.4, size=6.0)
    step(blender, "合成辉光 (Glare)", r)

    # 多帧截图验证 (关键帧节点)
    r = blender.capture_animation_frames(
        frames=[1, 11, 15, 25, 30, 45], tag="turtle", width=960, height=540)
    if r.get("success"):
        print(f"  📸 多帧截图 {r['count']} 张:")
        for f in r["frames"]:
            print(f"     帧 {f['frame']:2d}: {f['filepath']}")
        print("  → 用 Read 工具查看对比运动节奏")

    if do_render:
        print(f"  渲染中 (1280x720)...")
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
    print("║  🐢 Q萌海龟打斗场景 — AI 全流程                        ║")
    print("╚" + "═" * 58 + "╝")

    cleanup_scene(blender)
    build_turtle(blender)
    build_rig(blender)
    bind_turtle(blender)
    build_expressions(blender)
    animate_fight(blender)
    build_scene(blender)

    do_render = "--fast" not in sys.argv
    render_verify(blender, do_render)

    print("\n" + "═" * 60)
    print(f"  完成! ✅ {OK} 步成功, ❌ {FAIL} 步失败")
    print("  在 Blender 中: 选择 Camera 视角, 按空格播放动画")
    print("═" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
