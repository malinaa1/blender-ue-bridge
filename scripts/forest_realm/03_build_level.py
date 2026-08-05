"""
Forest Realm - UE 关卡搭建
在 DONG 项目中放置资产、灯光、特效
"""
import socket
import json
import time
import os

# UE TCP 连接
UE_HOST = "127.0.0.1"
UE_PORT = 55557
DELAY = 1.5  # 命令间隔，防止崩溃

def send_ue(command_type, params=None):
    """发送命令到 UE"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    try:
        sock.connect((UE_HOST, UE_PORT))
        cmd = {"type": command_type}
        if params:
            cmd["params"] = params
        sock.send(json.dumps(cmd).encode())
        data = sock.recv(65536)
        result = json.loads(data.decode())
        status = result.get("status", "unknown")
        if status == "error":
            print(f"  ERROR: {result.get('message', 'Unknown')}")
        return result
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        sock.close()

def spawn_actor(actor_type, name, location, rotation=None, scale=None, static_mesh=None):
    """生成 Actor"""
    params = {
        "type": actor_type,
        "name": name,
        "location": list(location),
    }
    if rotation:
        params["rotation"] = list(rotation)
    if scale:
        params["scale"] = list(scale)
    if static_mesh:
        params["static_mesh"] = static_mesh

    result = send_ue("spawn_actor", params)
    time.sleep(DELAY)
    return result

def set_transform(name, location=None, rotation=None, scale=None):
    """设置 Actor 变换"""
    params = {"name": name}
    if location:
        params["location"] = list(location)
    if rotation:
        params["rotation"] = list(rotation)
    if scale:
        params["scale"] = list(scale)

    result = send_ue("set_actor_transform", params)
    time.sleep(DELAY)
    return result

def apply_material(actor_name, material_path):
    """应用材质"""
    result = send_ue("apply_material_to_actor", {
        "actor_name": actor_name,
        "material_path": material_path
    })
    time.sleep(DELAY)
    return result

# ============================================================
# 区域布局
# ============================================================
# 苏醒之地: (0, 0, 0)
# 溪谷小径: (0, 60, -5)
# 花海平原: (50, 120, -3)
# 蘑菇洞穴: (-50, 120, -15)
# 树灵居所: (0, 200, 5)
# 世界之树: (0, 280, 10)

print("=" * 60)
print("Forest Realm - Level Building")
print("=" * 60)

# 测试连接
print("\n[1] Testing UE connection...")
result = send_ue("ping")
print(f"  UE: {result}")

# ============================================================
# 区域 1: 苏醒之地
# ============================================================
print("\n[2] Building Area 1: Awakening Glade...")

# 巨花 - 苏醒点
spawn_actor("StaticMeshActor", "SM_Giant_Flower_01",
    location=(0, 0, 0),
    static_mesh="/Game/ForestRealm/Models/SM_Giant_Flower")

# 周围小花
for i in range(6):
    import math
    angle = 2 * math.pi * i / 6
    r = 5 + (i % 2) * 2
    spawn_actor("StaticMeshActor", f"SM_Giant_Flower_Small_{i}",
        location=(math.cos(angle)*r, math.sin(angle)*r, 0),
        scale=(0.5, 0.5, 0.5),
        static_mesh="/Game/ForestRealm/Models/SM_Giant_Flower")

# 周围树木
for i in range(4):
    angle = 2 * math.pi * i / 4 + 0.5
    r = 15
    spawn_actor("StaticMeshActor", f"SM_Tree_Oak_A1_{i}",
        location=(math.cos(angle)*r, math.sin(angle)*r, 0),
        scale=(1.5, 1.5, 1.5),
        static_mesh="/Game/ForestRealm/Models/SM_Tree_Oak")

# 苏醒之地灯光 - 温暖金色
spawn_actor("PointLight", "Light_Awakening_01",
    location=(0, 0, 8),
    )

# 萤火虫点光
for i in range(8):
    import random
    random.seed(i)
    x = random.uniform(-10, 10)
    y = random.uniform(-10, 10)
    z = random.uniform(2, 6)
    spawn_actor("PointLight", f"Firefly_A1_{i}",
        location=(x, y, z))

# ============================================================
# 区域 2: 溪谷小径
# ============================================================
print("\n[3] Building Area 2: Valley Path...")

# 木桥
spawn_actor("StaticMeshActor", "SM_Bridge_01",
    location=(0, 45, -3),
    static_mesh="/Game/ForestRealm/Models/SM_Bridge_Wood")

# 岩石
for i in range(6):
    import random
    random.seed(i + 100)
    x = random.uniform(-5, 5)
    y = 35 + i * 8
    z = -5 + random.uniform(-1, 1)
    s = random.uniform(0.8, 2.0)
    spawn_actor("StaticMeshActor", f"SM_Rock_V2_{i}",
        location=(x, y, z),
        scale=(s, s, s),
        static_mesh="/Game/ForestRealm/Models/SM_Rock")

# 溪边树木
for i in range(5):
    side = 1 if i % 2 == 0 else -1
    y = 30 + i * 10
    spawn_actor("StaticMeshActor", f"SM_Tree_Willow_V2_{i}",
        location=(side * 12, y, -4),
        scale=(1.2, 1.2, 1.2),
        static_mesh="/Game/ForestRealm/Models/SM_Tree_Willow")

# 水晶
for i in range(3):
    import random
    random.seed(i + 200)
    spawn_actor("StaticMeshActor", f"SM_Crystal_V2_{i}",
        location=(random.uniform(-3, 3), 40 + i * 15, -4),
        scale=(0.8, 0.8, 0.8),
        static_mesh="/Game/ForestRealm/Models/SM_Crystal")

# ============================================================
# 区域 3: 花海平原
# ============================================================
print("\n[4] Building Area 3: Flower Plains...")

# 大量小花（巨花缩小版）
for i in range(12):
    import random
    random.seed(i + 300)
    x = 40 + random.uniform(-30, 30)
    y = 110 + random.uniform(-25, 25)
    s = random.uniform(0.15, 0.35)
    spawn_actor("StaticMeshActor", f"SM_Flower_Field_{i}",
        location=(x, y, -3),
        scale=(s, s, s),
        static_mesh="/Game/ForestRealm/Models/SM_Giant_Flower")

# 花海中的树木
for i in range(6):
    import random
    random.seed(i + 350)
    x = 40 + random.uniform(-40, 40)
    y = 110 + random.uniform(-30, 30)
    spawn_actor("StaticMeshActor", f"SM_Tree_Oak_Flower_{i}",
        location=(x, y, -3),
        scale=(1.3, 1.3, 1.3),
        static_mesh="/Game/ForestRealm/Models/SM_Tree_Oak")

# 水晶点缀
for i in range(4):
    import random
    random.seed(i + 380)
    spawn_actor("StaticMeshActor", f"SM_Crystal_Flower_{i}",
        location=(40 + random.uniform(-20, 20), 110 + random.uniform(-20, 20), -3),
        static_mesh="/Game/ForestRealm/Models/SM_Crystal")

# ============================================================
# 区域 4: 蘑菇洞穴 (地面入口)
# ============================================================
print("\n[5] Building Area 4: Mushroom Cavern entrance...")

# 巨型蘑菇
for i in range(8):
    import random, math
    random.seed(i + 400)
    angle = 2 * math.pi * i / 8
    r = random.uniform(5, 20)
    x = -50 + math.cos(angle) * r
    y = 110 + math.sin(angle) * r
    s = random.uniform(0.8, 1.5)
    spawn_actor("StaticMeshActor", f"SM_Mushroom_Giant_{i}",
        location=(x, y, -15),
        scale=(s, s, s),
        static_mesh="/Game/ForestRealm/Models/SM_Mushroom_Giant")

# 蘑菇区域岩石
for i in range(5):
    import random
    random.seed(i + 450)
    spawn_actor("StaticMeshActor", f"SM_Rock_Cave_{i}",
        location=(-50 + random.uniform(-15, 15), 110 + random.uniform(-15, 15), -15),
        scale=(1.5, 1.5, 1.5),
        static_mesh="/Game/ForestRealm/Models/SM_Rock")

# ============================================================
# 区域 5: 树灵居所
# ============================================================
print("\n[6] Building Area 5: Tree Spirit's Home...")

# 大型柳树
for i in range(4):
    import math
    angle = 2 * math.pi * i / 4
    r = 15
    spawn_actor("StaticMeshActor", f"SM_Tree_Willow_Spirit_{i}",
        location=(math.cos(angle)*r, 200 + math.sin(angle)*r, 5),
        scale=(2.0, 2.0, 2.0),
        static_mesh="/Game/ForestRealm/Models/SM_Tree_Willow")

# 橡树
for i in range(3):
    import random
    random.seed(i + 500)
    spawn_actor("StaticMeshActor", f"SM_Tree_Oak_Spirit_{i}",
        location=(random.uniform(-20, 20), 200 + random.uniform(-20, 20), 5),
        scale=(1.8, 1.8, 1.8),
        static_mesh="/Game/ForestRealm/Models/SM_Tree_Oak")

# 水晶
for i in range(5):
    import random
    random.seed(i + 530)
    spawn_actor("StaticMeshActor", f"SM_Crystal_Spirit_{i}",
        location=(random.uniform(-15, 15), 200 + random.uniform(-15, 15), 5),
        scale=(1.2, 1.2, 1.2),
        static_mesh="/Game/ForestRealm/Models/SM_Crystal")

# ============================================================
# 区域 6: 世界之树
# ============================================================
print("\n[7] Building Area 6: World Tree...")

# 世界之树
spawn_actor("StaticMeshActor", "SM_World_Tree_01",
    location=(0, 280, 10),
    scale=(2.0, 2.0, 2.0),
    static_mesh="/Game/ForestRealm/Models/SM_World_Tree")

# 祭坛
spawn_actor("StaticMeshActor", "SM_Altar_01",
    location=(0, 270, 10),
    static_mesh="/Game/ForestRealm/Models/SM_Altar")

# 周围水晶
for i in range(6):
    import math
    angle = 2 * math.pi * i / 6
    r = 20
    spawn_actor("StaticMeshActor", f"SM_Crystal_WorldTree_{i}",
        location=(math.cos(angle)*r, 280 + math.sin(angle)*r, 10),
        scale=(1.5, 1.5, 1.5),
        static_mesh="/Game/ForestRealm/Models/SM_Crystal")

# 世界之树发光点光
for i in range(8):
    import random, math
    random.seed(i + 600)
    angle = 2 * math.pi * i / 8
    r = random.uniform(3, 8)
    spawn_actor("PointLight", f"Light_WorldTree_{i}",
        location=(math.cos(angle)*r, 280 + math.sin(angle)*r, 15 + random.uniform(0, 10)))

# ============================================================
# 全局灯光
# ============================================================
print("\n[8] Setting up global lighting...")

# 主方向光 (太阳)
spawn_actor("DirectionalLight", "Sun_Main",
    location=(0, 0, 50))

# 环境光点
spawn_actor("PointLight", "Ambient_01",
    location=(0, 100, 30))

# ============================================================
# 设置 Player Start
# ============================================================
print("\n[9] Setting Player Start...")
# 注: UE MCP 可能不直接支持 PlayerStart，需要在编辑器中手动设置
# 或者使用 execute_ue_command

print("\n" + "=" * 60)
print("Level building complete!")
print("Total actors placed: ~100+")
print("=" * 60)
