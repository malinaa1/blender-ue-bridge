"""慢速放置村庄 - 每个命令间隔2秒，避免崩溃"""
import socket, json, time

def ue_cmd(cmd, timeout=15):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(('127.0.0.1', 55557))
    sock.sendall(json.dumps(cmd).encode())
    data = sock.recv(65536)
    result = json.loads(data)
    sock.close()
    return result

# 清理旧 Actor
print("Cleaning old actors...")
actors = ue_cmd({"type": "get_actors_in_level", "params": {}})
for a in actors.get("result", {}).get("actors", []):
    n = a.get("name", "")
    if any(x in n for x in ["Tavern", "StoneHouse", "WoodHouse", "Tower", "Light_", "SunLight"]):
        try:
            ue_cmd({"type": "delete_actor", "params": {"name": n}}, 5)
            print(f"  Deleted: {n}")
        except:
            pass
        time.sleep(0.5)

time.sleep(2)

# =============================================
# 1. 太阳光
# =============================================
print("\n[1/4] SunLight...")
r = ue_cmd({"type": "spawn_actor", "params": {
    "type": "DirectionalLight", "name": "SunLight",
    "location": [0, 0, 5000], "rotation": [-45, -30, 0]
}})
print(f"  {r.get('status')}")
time.sleep(3)

# =============================================
# 2. 建筑 - 3倍缩放，村庄布局
# =============================================
print("\n[2/4] Buildings...")

buildings = [
    # 中央广场
    ("Tavern_01",     "/Game/Village/SM_Tavern",       [0, 0, 0],       0,   [3,3,3]),
    # 北街
    ("StoneHouse_01", "/Game/Village/SM_House_Stone",  [0, 3000, 0],    0,   [3,3,3]),
    ("WoodHouse_01",  "/Game/Village/SM_House_Wood",   [0, 6000, 0],    0,   [3,3,3]),
    # 南街
    ("StoneHouse_02", "/Game/Village/SM_House_Stone",  [0, -3000, 0],   180, [3,3,3]),
    ("WoodHouse_02",  "/Game/Village/SM_House_Wood",   [0, -6000, 0],   180, [3,3,3]),
    # 东街
    ("WoodHouse_03",  "/Game/Village/SM_House_Wood",   [3000, 1500, 0], -90, [3,3,3]),
    ("WoodHouse_04",  "/Game/Village/SM_House_Wood",   [3000, -1500,0], -90, [3,3,3]),
    # 西街
    ("WoodHouse_05",  "/Game/Village/SM_House_Wood",   [-3000,1500, 0], 90,  [3,3,3]),
    ("WoodHouse_06",  "/Game/Village/SM_House_Wood",   [-3000,-1500,0], 90,  [3,3,3]),
    # 四角塔
    ("Tower_NE",      "/Game/Village/SM_Tower",        [5000, 5000, 0], 0,   [3,3,3]),
    ("Tower_NW",      "/Game/Village/SM_Tower",        [-5000,5000, 0], 0,   [3,3,3]),
    ("Tower_SE",      "/Game/Village/SM_Tower",        [5000,-5000, 0], 0,   [3,3,3]),
    ("Tower_SW",      "/Game/Village/SM_Tower",        [-5000,-5000,0], 0,   [3,3,3]),
]

for i, (name, mesh, loc, rot_z, scale) in enumerate(buildings):
    r = ue_cmd({"type": "spawn_actor", "params": {
        "type": "StaticMeshActor", "name": name,
        "location": loc, "rotation": [0, rot_z, 0], "scale": scale,
        "static_mesh": mesh
    }})
    s = "OK" if r.get("status") == "success" else "FAIL"
    print(f"  [{s}] {i+1}/{len(buildings)} {name}")
    time.sleep(2)

time.sleep(3)

# =============================================
# 3. 街灯
# =============================================
print("\n[3/4] Street lights...")

lights = [
    # 广场4角
    ("Light_Square_1", [800, 800, 200]),
    ("Light_Square_2", [-800, 800, 200]),
    ("Light_Square_3", [800, -800, 200]),
    ("Light_Square_4", [-800, -800, 200]),
    # 北街
    ("Light_North_1", [150, 1500, 200]),
    ("Light_North_2", [-150, 4500, 200]),
    # 南街
    ("Light_South_1", [150, -1500, 200]),
    ("Light_South_2", [-150, -4500, 200]),
    # 东街
    ("Light_East_1", [1500, 150, 200]),
    # 西街
    ("Light_West_1", [-1500, 150, 200]),
]

for name, loc in lights:
    r = ue_cmd({"type": "spawn_actor", "params": {
        "type": "PointLight", "name": name, "location": loc
    }})
    s = "OK" if r.get("status") == "success" else "FAIL"
    print(f"  [{s}] {name}")
    time.sleep(1)

print("\n[4/4] DONE!")
print("Check UE Editor - buildings should be 3x bigger with proper layout!")
