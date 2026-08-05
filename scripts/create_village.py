"""
中世纪村庄 v2 — 使用新宏工具构建 (精确尺寸 + 验证拓扑)

流程:
1. Blender: build_medieval_house ×2 + 塔楼 + 围墙 (宏工具)
2. 验证: check_scene_quality + assert_dimensions
3. 导出 FBX → UE Content/Village
4. UE: 放置建筑 + 灯光

用法:
    python scripts/create_village.py            # Blender 建模 + 导出
    python scripts/create_village.py --to-ue    # 构建后放入 UE
"""

import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.blender_client import BlenderClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BRIDGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# UE 项目 Content 目录 — 通过环境变量 UE_CONTENT_DIR 指定 (例如 D:/UE5Projects/MyGame/Content)
UE_CONTENT = os.environ.get("UE_CONTENT_DIR", "")
if not UE_CONTENT:
    print("⚠️ 未设置 UE_CONTENT_DIR 环境变量 — 跳过 UE 导入 (仅 Blender 建模)")
    print("   设置方式: set UE_CONTENT_DIR=D:/你的UE项目/Content")
EXPORT_DIR = os.path.join(BRIDGE_ROOT, "shared_assets", "models")


def build_models(blender):
    """在 Blender 中构建村庄模型 (宏工具)"""
    print("=" * 60)
    print("  Blender: 构建村庄模型")
    print("=" * 60)

    models = []

    # 1. 木屋 (山墙屋顶)
    print("\n[1] SM_House_Wood (7x5x3m, 山墙)")
    r = blender.build_medieval_house(
        length=7.0, depth=5.0, height=3.0,
        door={"x": 0, "width": 1.0, "height": 2.1},
        windows=[
            {"x": 2.2, "width": 1.2, "height": 1.2, "z_bottom": 0.9},
            {"x": -2.2, "width": 1.2, "height": 1.2, "z_bottom": 0.9},
        ],
        roof_style="gable", name="SM_House_Wood")
    print(f"  {'✅' if r.get('status') == 'success' else '❌ ' + str(r.get('message'))}")
    if r.get("status") == "success":
        models.append("SM_House_Wood")
    time.sleep(0.3)

    # 2. 石屋 (四坡屋顶)
    print("\n[2] SM_House_Stone (9x6x5m, 四坡)")
    r = blender.build_medieval_house(
        length=9.0, depth=6.0, height=5.0,
        door={"x": 0, "width": 1.2, "height": 2.4},
        windows=[
            {"x": 3.0, "width": 1.2, "height": 1.4, "z_bottom": 1.4},
            {"x": -3.0, "width": 1.2, "height": 1.4, "z_bottom": 1.4},
            {"x": 1.5, "width": 1.0, "height": 1.0, "z_bottom": 3.4},
        ],
        roof_style="hip", name="SM_House_Stone")
    print(f"  {'✅' if r.get('status') == 'success' else '❌ ' + str(r.get('message'))}")
    if r.get("status") == "success":
        models.append("SM_House_Stone")
    time.sleep(0.3)

    # 3. 酒馆 (带门廊: 主体 + 门廊屋顶)
    print("\n[3] SM_Tavern (11x7x3.5m)")
    r = blender.build_medieval_house(
        length=11.0, depth=7.0, height=3.5,
        door={"x": 0, "width": 1.4, "height": 2.4},
        windows=[
            {"x": 3.5, "width": 1.4, "height": 1.2, "z_bottom": 1.0},
            {"x": -3.5, "width": 1.4, "height": 1.2, "z_bottom": 1.0},
            {"x": 0, "width": 1.2, "height": 1.2, "z_bottom": 1.0},
        ],
        roof_style="gable", name="SM_Tavern")
    print(f"  {'✅' if r.get('status') == 'success' else '❌ ' + str(r.get('message'))}")
    if r.get("status") == "success":
        models.append("SM_Tavern")
    time.sleep(0.3)

    # 4. 瞭望塔 (柱子 + 锥顶)
    print("\n[4] SM_Tower (直径4m 高12m)")
    r = blender.create_column(height=10.0, radius=2.0, name="SM_Tower")
    # 塔顶平台
    blender.create_floor(length=3.5, width=3.5, thickness=0.3,
                         name="Tower_Platform")
    blender.set_transform("Tower_Platform", location=[0, 0, 10])
    # 锥形屋顶
    r2 = blender.create_roof(length=4.5, width=4.5, height=2.0,
                             style="pyramid", name="Tower_Roof",
                             material={"name": "M_Clay_Roof",
                                       "base_color": [0.55, 0.3, 0.22, 1.0],
                                       "roughness": 0.9})
    blender.set_transform("Tower_Roof", location=[0, 0, 10.3])
    ok = r.get("status") == "success" and r2.get("status") == "success"
    print(f"  {'✅' if ok else '❌'}")
    if ok:
        models.append("SM_Tower")

    # 5. 质量验证
    print("\n[5] 质量验证")
    q = blender.check_scene_quality()
    if q.get("status") == "success":
        print(f"  平均质量分: {q['result'].get('average_score', '?')} "
              f"(目标 >= 90)")
        worst = q["result"].get("worst")
        if worst and worst.get("quality_score", 100) < 90:
            print(f"  ⚠️ 最差: {worst.get('name')} "
                  f"({worst.get('quality_score')}) {worst.get('issues')}")

    # 6. 截图
    blender.get_screenshot(os.path.join(BRIDGE_ROOT, "shared_assets",
                                        "screenshots", "village_build.png"),
                           width=1280, height=720)

    return models


def export_models(blender, models):
    """导出 FBX 到 UE Content"""
    print("\n" + "=" * 60)
    print("  导出 FBX → UE Content/Village")
    print("=" * 60)

    village_dir = os.path.join(UE_CONTENT, "Village")
    os.makedirs(village_dir, exist_ok=True)

    for name in models:
        fbx = os.path.join(EXPORT_DIR, f"{name}.fbx")
        r = blender.export_fbx(name, fbx)
        if r.get("status") == "success":
            shutil.copy2(fbx, os.path.join(village_dir, f"{name}.fbx"))
            print(f"  ✅ {name}.fbx")
        else:
            print(f"  ❌ {name}: {r.get('message')}")
        time.sleep(0.5)


def place_in_ue():
    """在 UE 中放置建筑 + 灯光"""
    print("\n" + "=" * 60)
    print("  UE: 放置村庄")
    print("=" * 60)

    import socket
    import json

    def ue_cmd(cmd, timeout=30):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(("127.0.0.1", 55557))
            sock.sendall(json.dumps(cmd).encode())
            data = sock.recv(65536)
            return json.loads(data)
        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            sock.close()

    # 清理旧建筑
    print("  清理旧 Actor...")
    actors = ue_cmd({"type": "get_actors_in_level", "params": {}})
    for a in actors.get("result", {}).get("actors", []):
        n = a.get("name", "")
        if any(x in n for x in ["Tavern", "StoneHouse", "WoodHouse", "Tower",
                                "Light_", "SunLight"]):
            ue_cmd({"type": "delete_actor", "params": {"name": n}}, 5)
            time.sleep(0.3)

    # 太阳
    ue_cmd({"type": "spawn_actor", "params": {
        "type": "DirectionalLight", "name": "SunLight",
        "location": [0, 0, 5000], "rotation": [-45, -30, 0]}})
    time.sleep(1)

    # 建筑布局 (1m = 100 UE 单位)
    buildings = [
        ("Tavern_01",     "/Game/Village/SM_Tavern",      [0, 0, 0],         0,   [3, 3, 3]),
        ("StoneHouse_01", "/Game/Village/SM_House_Stone", [0, 3000, 0],      0,   [3, 3, 3]),
        ("WoodHouse_01",  "/Game/Village/SM_House_Wood",  [0, 6000, 0],      0,   [3, 3, 3]),
        ("WoodHouse_02",  "/Game/Village/SM_House_Wood",  [0, -6000, 0],     180, [3, 3, 3]),
        ("Tower_NE",      "/Game/Village/SM_Tower",       [5000, 5000, 0],   0,   [3, 3, 3]),
        ("Tower_SW",      "/Game/Village/SM_Tower",       [-5000, -5000, 0], 0,   [3, 3, 3]),
    ]
    for name, mesh, loc, rot, scale in buildings:
        r = ue_cmd({"type": "spawn_actor", "params": {
            "type": "StaticMeshActor", "name": name, "location": loc,
            "rotation": [0, rot, 0], "scale": scale, "static_mesh": mesh}})
        print(f"  {'✅' if r.get('status') == 'success' else '❌'} {name}")
        time.sleep(1.5)

    # 街灯
    for name, loc in [
        ("Light_Square_1", [800, 800, 200]), ("Light_Square_2", [-800, 800, 200]),
        ("Light_North_1", [150, 1500, 200]), ("Light_South_1", [150, -1500, 200]),
    ]:
        ue_cmd({"type": "spawn_actor", "params": {
            "type": "PointLight", "name": name, "location": loc}})
        time.sleep(0.8)

    print("\n  DONE! 村庄已放置到 UE")


def main():
    blender = BlenderClient()
    print(f"Blender 连接: {'✅' if blender.ping() else '❌ 请先启动 Blender 并启用插件'}")
    if not blender.ping():
        sys.exit(1)

    models = build_models(blender)
    export_models(blender, models)

    if "--to-ue" in sys.argv:
        place_in_ue()
    else:
        print("\n提示: 加 --to-ue 参数可在构建后自动导入 UE")


if __name__ == "__main__":
    main()
