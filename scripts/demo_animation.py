"""
动画演示 — AI 全流程动画工作流 (参考 Evolink-AI Seedance 工作流)

流程:
1. 建模: 中世纪房屋 + 村庄
2. 相机运镜: camera_orbit 环绕 + camera_dolly 推拉
3. 物体动画: 转盘/漂浮/出现
4. 物理模拟: 刚体掉落
5. 多帧截图验证
6. (可选) 渲染成片

用法:
    python scripts/demo_animation.py               # 动画设置 + 多帧验证
    python scripts/demo_animation.py --render      # 额外渲染成片 (eevee)
    python scripts/demo_animation.py --render-cycles # cycles 渲染 (慢)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.blender_client import BlenderClient

BRIDGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOT_DIR = os.path.join(BRIDGE_ROOT, "shared_assets", "screenshots")
FRAME_DIR = os.path.join(BRIDGE_ROOT, "shared_assets", "frames")


def ok(result, label):
    status = "✅" if result.get("status") == "success" else "❌"
    print(f"  {status} {label}")
    if result.get("status") != "success":
        print(f"    ERROR: {result.get('message')}")
    return result.get("status") == "success"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blender = BlenderClient()
    print(f"Blender 连接: {'✅' if blender.ping() else '❌ 请先启动 Blender 并启用插件'}")
    if not blender.ping():
        sys.exit(1)

    print("=" * 60)
    print("  AI 动画工作流演示")
    print("=" * 60)

    # ── 1. 建模 ─────────────────────────────────────────────
    print("\n[1] 建模 (房屋 + 石柱 + 木箱)")
    blender.build_medieval_house(
        length=6.0, depth=5.0, height=3.0,
        door={"x": 0, "width": 1.0, "height": 2.1},
        windows=[{"x": 1.8, "width": 1.2, "height": 1.2, "z_bottom": 0.9},
                 {"x": -1.8, "width": 1.2, "height": 1.2, "z_bottom": 0.9}],
        roof_style="gable", name="HeroHouse")
    blender.create_column(height=2.0, radius=0.3, name="SpinColumn")
    blender.set_transform("SpinColumn", location=[3.5, 0, 0])
    blender.create_crate(length=0.6, width=0.6, height=0.5, name="DropCrate")
    blender.set_transform("DropCrate", location=[-3, 0, 4])
    blender.create_rock(radius=0.4, name="FloatRock")
    blender.set_transform("FloatRock", location=[-3, 3, 1])
    # 地面
    blender.create_floor(length=20, width=20, thickness=0.2, name="Ground")
    ok({"status": "success"}, "场景就绪")

    # ── 2. 相机运镜 ─────────────────────────────────────────
    print("\n[2] 相机运镜")
    ok(blender.camera_setup(location=[8, -8, 3], target=[0, 0, 1.5],
                            name="CamOrbit"), "创建相机")
    ok(blender.camera_orbit(radius=8, height=2.5, start_angle=45,
                            end_angle=405, frames=120, camera="CamOrbit"),
       "环绕运镜 360° (120帧)")
    ok(blender.camera_dolly(from_distance=8, to_distance=4, frames=60,
                            camera="CamOrbit", start_frame=120),
       "推拉运镜 (120-180帧)")

    # ── 3. 物体动画 ─────────────────────────────────────────
    print("\n[3] 物体动画")
    ok(blender.animate_turntable("SpinColumn", revolutions=2, frames=120),
       "柱子转盘 2 圈")
    ok(blender.animate_float("FloatRock", height=0.5, frames=60),
       "岩石漂浮")
    ok(blender.animate_appear("DropCrate", frame=60, duration=25),
       "木箱出现 (弹跳)")

    # ── 4. 物理模拟 ─────────────────────────────────────────
    print("\n[4] 物理模拟 (刚体掉落)")
    ok(blender.setup_rigid_body_world(gravity=[0, 0, -9.81],
                                      frame_start=200, frame_end=320),
       "物理世界")
    ok(blender.add_rigid_body("Ground", type="passive", friction=0.8),
       "地面 (passive)")
    ok(blender.add_rigid_body("DropCrate", type="active", mass=5, friction=0.6),
       "木箱 (active, 5kg)")
    ok(blender.add_rigid_body("FloatRock", type="active", mass=3),
       "岩石 (active, 3kg)")

    # ── 5. 时间轴 + 多帧验证 ────────────────────────────────
    print("\n[5] 多帧截图验证 (动画视觉闭环)")
    ok(blender.set_frame_range(0, 320, fps=24), "时间轴 0-320 @24fps")
    r = blender.capture_animation_frames(
        frames=[0, 60, 90, 150, 220, 280, 320], tag="anim_demo",
        width=960, height=540)
    if r.get("success"):
        print(f"  ✅ 截取 {r['count']} 帧:")
        for f in r["frames"]:
            print(f"     帧 {f['frame']:3d}: {f['filepath']}")
        print("  → 用 Read 工具查看这些图片, 对比运动是否流畅/穿模")

    # ── 6. (可选) 渲染成片 ──────────────────────────────────
    if "--render" in sys.argv or "--render-cycles" in sys.argv:
        engine = "cycles" if "--render-cycles" in sys.argv else "eevee"
        print(f"\n[6] 渲染成片 ({engine})")
        os.makedirs(FRAME_DIR, exist_ok=True)
        r = blender.render_animation(FRAME_DIR, start=0, end=320,
                                     engine=engine, resolution_x=1280,
                                     resolution_y=720, samples=64)
        if r.get("status") == "success":
            print(f"  ✅ 渲染 {r['result']['frames']} 帧 → {FRAME_DIR}")
        else:
            print(f"  ❌ {r.get('message')}")

    print("\n" + "=" * 60)
    print(" 完成! 在 Blender 中按空格播放动画查看效果")
    print(" 截图在 shared_assets/screenshots/")
    print("=" * 60)


if __name__ == "__main__":
    main()
