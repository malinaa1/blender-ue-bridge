"""
桥接系统 v2 端到端测试脚本

测试 Blender addon 连接、原子/宏工具、质量验证、资产传输。
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.blender_client import BlenderClient
from mcp_server.ue_client import UEClient
from mcp_server.asset_pipeline import AssetPipeline

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BRIDGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0


def check(result, label):
    global PASS, FAIL
    ok_flag = result.get("status") == "success"
    if ok_flag:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}: {result.get('message')}")
    return ok_flag


def test_addon_protocol(blender):
    """测试新协议: ping / 排队 / 轮询"""
    print("=" * 60)
    print("测试 1: Addon 协议 (ping → 排队 → 轮询)")
    print("=" * 60)

    check(blender.ping() and {"status": "success"} or {"status": "error"}, "ping")

    # 创建 + 轮询 (原子命令走队列)
    r = blender.create_object("cube", "TestCube", size=[1.0, 1.0, 1.0])
    check(r, f"create_object 队列执行 (id={r.get('result', {}).get('id')})")

    # 信息
    r = blender.get_object_info("TestCube")
    check(r, "object_info")
    if r.get("status") == "success":
        q = r.get("result", {}).get("quality", {})
        print(f"    质量分: {q.get('quality_score', '?')} (目标 >= 90)")
        print(f"    四边面比例: {q.get('quad_ratio', '?')}")


def test_atomic_tools(blender):
    """测试原子工具链: 挤出/斜切/布尔"""
    print("\n" + "=" * 60)
    print("测试 2: 原子工具 (挤出/斜切/布尔)")
    print("=" * 60)

    # 挤出
    check(blender.create_object("cube", "TestExtrude", size=[1, 1, 1]), "创建立方体")
    check(blender.extrude_face("TestExtrude", 0.5, face_indices=[0]), "挤出顶面 0.5m")

    # 尺寸验证: 1x1x1 + 挤出0.5 = 高 1.5 (z 方向面索引 0 为顶面)
    dims = blender.assert_dimensions("TestExtrude", [1.0, 1.0, 1.5], tolerance=0.01)
    check(dims, "挤出后尺寸断言 [1,1,1.5]")

    # 斜切
    check(blender.add_modifier("TestExtrude", "bevel", {"width": 0.02}), "添加 Bevel")
    check(blender.apply_modifier("TestExtrude"), "应用 Bevel")

    # 布尔
    check(blender.create_object("cylinder", "TestCutter", radius=0.2, depth=2.0), "创建布尔刀具")
    check(blender.set_transform("TestCutter", location=[0.3, 0.3, 0.5]), "定位刀具")
    r = blender.boolean_operation("TestExtrude", "TestCutter", "difference")
    check(r, "布尔差集")
    q = blender.check_mesh_quality("TestExtrude")
    if q.get("status") == "success":
        print(f"    布尔后质量: {q.get('result', {}).get('quality_score', '?')}")


def test_macro_tools(blender):
    """测试宏工具: 墙/屋顶/房屋"""
    print("\n" + "=" * 60)
    print("测试 3: 宏工具 (墙/屋顶/房屋)")
    print("=" * 60)

    check(blender.create_wall(4.0, 2.8, 0.2,
                              openings=[{"x": 0, "width": 1.0, "z_bottom": 0,
                                         "z_top": 2.1}],
                              name="TestWall"), "墙 (带门洞)")

    r = blender.create_roof(4.0, 4.0, 1.5, style="gable", name="TestRoof")
    check(r, "山墙屋顶")

    r = blender.build_medieval_house(
        length=4.0, depth=3.0, height=2.8,
        door={"x": 0, "width": 1.0, "height": 2.1},
        windows=[{"x": 1.2, "width": 1.0, "height": 1.0, "z_bottom": 0.9}],
        name="TestHouse")
    check(r, "中世纪房屋工作流")
    if r.get("status") == "success":
        print(f"    部件: {len(r.get('result', {}).get('parts', []))} 个对象")


def test_verification(blender):
    """测试验证层"""
    print("\n" + "=" * 60)
    print("测试 4: 验证层 (测量/断言/质量)")
    print("=" * 60)

    r = blender.measure_distance(object_a="TestCube", object_b="TestExtrude")
    check(r, "measure_distance")
    if r.get("status") == "success":
        print(f"    距离: {r['result']['distance']}m")

    r = blender.measure_gap("TestCube", "TestWall")
    check(r, "measure_gap")

    r = blender.assert_dimensions("TestWall", [4.0, 0.2, 2.8])
    check(r, "assert_dimensions")

    r = blender.check_scene_quality()
    check(r, "check_scene_quality")
    if r.get("status") == "success":
        print(f"    平均质量分: {r['result'].get('average_score', '?')}")


def test_screenshot_and_export(blender):
    """测试截图和导出"""
    print("\n" + "=" * 60)
    print("测试 5: 截图 + 导出")
    print("=" * 60)

    shot = os.path.join(BRIDGE_ROOT, "shared_assets", "screenshots", "test.png")
    r = blender.get_screenshot(shot, 800, 600)
    check(r, "视口截图")
    if r.get("status") == "success":
        print(f"    {shot}")

    out = os.path.join(BRIDGE_ROOT, "shared_assets", "models", "TestHouse.fbx")
    r = blender.export_fbx("TestHouse", out)
    check(r, "FBX 导出")
    if r.get("status") == "success":
        print(f"    {out} ({r['result'].get('size', '?')} bytes)")


def test_ue_connection():
    """测试 UE 连接"""
    print("\n" + "=" * 60)
    print("测试 6: UE 连接")
    print("=" * 60)
    ue = UEClient()
    r = ue.get_actors()
    is_error = "error" in str(r).lower()
    if is_error:
        FAIL += 1
        print(f"  ❌ UE: {r.get('message', r)}")
    else:
        PASS += 1
        print("  ✅ UE 连接正常")


def cleanup(blender):
    print("\n清理测试对象...")
    blender.delete_object(["TestCube", "TestExtrude", "TestWall", "TestRoof",
                           "TestHouse"])
    print("  已清理")


def main():
    print("╔══════════════════════════════════════════════════╗")
    print("║   Blender↔UE Bridge v2 端到端测试                ║")
    print("╚══════════════════════════════════════════════════╝")

    blender = BlenderClient()
    if not blender.ping():
        print("❌ Blender addon 未连接 — 请先启动 Blender 并启用 'BlenderUE Bridge' 插件")
        return 1

    test_addon_protocol(blender)
    test_atomic_tools(blender)
    test_macro_tools(blender)
    test_verification(blender)
    test_screenshot_and_export(blender)
    test_ue_connection()

    cleanup(blender)

    print("\n" + "=" * 60)
    print(f"测试汇总: {PASS} 通过, {FAIL} 失败")
    print("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
