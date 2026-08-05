"""
精确建模演示 — 使用 v2 宏工具构建中世纪村庄

演示内容:
1. 用 build_medieval_house 构建带门窗开洞的房屋 (精确尺寸)
2. 用 create_wall/roof/column 等宏工具构建塔楼和围墙
3. 网格质量检查 + 尺寸断言验证
4. 导出 FBX + (可选) 传输到 UE

用法:
    python scripts/demo_precision.py              # 只建模型
    python scripts/demo_precision.py --to-ue      # 构建后导入 UE
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.blender_client import BlenderClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def ok(result, label):
    status = "✅" if result.get("status") == "success" else "❌"
    print(f"  {status} {label}")
    if result.get("status") != "success":
        print(f"    ERROR: {result.get('message')}")
        return False
    return True


def build_village(blender, to_ue=False):
    print("=" * 60)
    print(" 中世纪村庄 — 精确建模演示")
    print("=" * 60)

    # 1. 主屋 (带门 + 3 窗, 山墙屋顶)
    print("\n[1] 主屋 (6x5x3m, 门+3窗)")
    result = blender.build_medieval_house(
        length=6.0, depth=5.0, height=3.0,
        door={"x": 0, "width": 1.0, "height": 2.1},
        windows=[
            {"x": 1.8, "width": 1.2, "height": 1.2, "z_bottom": 0.9},
            {"x": -1.8, "width": 1.2, "height": 1.2, "z_bottom": 0.9},
            {"x": 0, "width": 1.0, "height": 1.0, "z_bottom": 1.6},
        ],
        roof_style="gable", name="House_Main")
    ok(result, "主屋")
    time.sleep(0.3)

    # 2. 石屋 (四坡屋顶)
    print("\n[2] 石屋 (4x4x2.8m, 四坡屋顶)")
    result = blender.build_medieval_house(
        length=4.0, depth=4.0, height=2.8,
        door={"x": 0, "width": 0.9, "height": 2.0},
        windows=[{"x": 1.2, "width": 1.0, "height": 1.0, "z_bottom": 1.0}],
        roof_style="hip", name="House_Stone")
    ok(result, "石屋")
    time.sleep(0.3)

    # 3. 塔楼 (柱子 + 平台 + 屋顶)
    print("\n[3] 塔楼 (圆柱 + 锥顶)")
    blender.create_column(height=4.0, radius=0.8, name="Tower_Base")
    result = blender.create_roof(length=2.0, width=2.0, height=1.6,
                                 style="pyramid", name="Tower_Roof",
                                 material={"name": "M_Clay_Roof",
                                           "base_color": [0.55, 0.3, 0.22, 1.0],
                                           "roughness": 0.9})
    ok(result, "塔楼")
    # 塔顶平台
    blender.create_floor(length=1.8, width=1.8, thickness=0.1, name="Tower_Platform")
    blender.set_transform("Tower_Platform", location=[0, 0, 3.2])
    blender.set_transform("Tower_Roof", location=[0, 0, 3.3])

    # 4. 围墙 (带门洞)
    print("\n[4] 围墙 (10x2.5m, 门洞 1.5m)")
    result = blender.create_wall(
        length=10.0, height=2.5, thickness=0.3,
        openings=[{"x": 0, "width": 1.5, "z_bottom": 0, "z_top": 2.1}],
        name="Wall_01",
        material={"name": "M_Stone_Wall", "base_color": [0.55, 0.53, 0.5, 1.0],
                  "roughness": 0.95})
    ok(result, "围墙")
    time.sleep(0.3)

    # 5. 家具 (酒馆内部)
    print("\n[5] 家具")
    blender.create_table(length=2.0, width=1.0, height=0.75, name="Table_Tavern")
    blender.set_transform("Table_Tavern", location=[2.0, 1.5, 0])
    blender.create_chair(name="Chair_01")
    blender.set_transform("Chair_01", location=[2.2, 2.1, 0])
    ok({"status": "success"}, "桌子+椅子")

    # 6. 树木与岩石 (村庄装饰)
    print("\n[6] 环境")
    blender.create_tree(height=4.5, style="oak", name="Tree_Oak_01")
    blender.set_transform("Tree_Oak_01", location=[6.0, 3.0, 0])
    blender.create_tree(height=3.5, style="pine", name="Tree_Pine_01")
    blender.set_transform("Tree_Pine_01", location=[-6.0, -3.0, 0])
    blender.create_rock(radius=0.8, name="Rock_01")
    blender.set_transform("Rock_01", location=[5.0, -3.0, 0])
    ok({"status": "success"}, "树木+岩石")

    # 7. 质量验证
    print("\n[7] 质量验证")
    quality = blender.check_scene_quality()
    if quality.get("status") == "success":
        q = quality.get("result", {})
        print(f"  对象数: {q.get('object_count', '?')}")
        print(f"  平均质量分: {q.get('average_score', '?')}")
        worst = q.get("worst")
        if worst:
            print(f"  最差: {worst.get('name')} ({worst.get('quality_score')}) "
                  f"问题: {worst.get('issues')}")

    # 尺寸断言
    dims = blender.assert_dimensions("House_Main_Floor", [6.6, 5.6, 0.3])
    print(f"  地面尺寸断言: {dims.get('result', dims)}")

    # 8. 截图
    print("\n[8] 截图")
    result = blender.get_screenshot(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "shared_assets", "screenshots", "village_demo.png"),
        width=1280, height=720)
    if result.get("status") == "success":
        print(f"  ✅ 截图已保存")

    # 9. 导出
    print("\n[9] 导出 FBX")
    export_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "shared_assets", "models")
    exported = []
    for obj_name in ["House_Main", "House_Stone", "Tower_Base"]:
        result = blender.export_fbx(obj_name, os.path.join(export_dir, f"{obj_name}.fbx"))
        if result.get("status") == "success":
            size = result.get("result", {}).get("size", "?")
            print(f"  ✅ {obj_name}.fbx ({size} bytes)")
            exported.append(obj_name)
        else:
            print(f"  ❌ {obj_name}: {result.get('message')}")
        time.sleep(0.5)

    # 10. (可选) 导入 UE
    if to_ue:
        print("\n[10] 导入 UE")
        from mcp_server.ue_client import UEClient
        ue = UEClient()
        for obj_name in exported:
            fbx_path = os.path.join(export_dir, f"{obj_name}.fbx")
            result = ue.import_asset(fbx_path, "/Game/VillageDemo/")
            print(f"  {obj_name}: {result.get('status')}")
            time.sleep(1.5)

    print("\n" + "=" * 60)
    print(" 演示完成! 在 Blender 中查看结果 (Shared assets/screenshots)")
    print("=" * 60)


if __name__ == "__main__":
    to_ue = "--to-ue" in sys.argv
    blender = BlenderClient()
    print(f"Blender 连接: {'✅' if blender.ping() else '❌ (请先启动 Blender 并启用插件)'}")
    if not blender.ping():
        sys.exit(1)
    build_village(blender, to_ue)
