"""
Forest Realm - Blueprint 创建脚本
创建游戏逻辑 Blueprint
"""
import socket
import json
import time

UE_HOST = "127.0.0.1"
UE_PORT = 55557
DELAY = 2.0

def send_ue(command_type, params=None):
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
        else:
            print(f"  OK: {command_type}")
        return result
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        sock.close()
    time.sleep(DELAY)

def create_blueprint(name, parent_class="Actor"):
    result = send_ue("create_blueprint", {
        "name": name,
        "parent_class": parent_class
    })
    time.sleep(DELAY)
    return result

def add_variable(bp_name, var_name, var_type, default_value=None):
    params = {
        "blueprint_name": bp_name,
        "variable_name": var_name,
        "variable_type": var_type
    }
    if default_value is not None:
        params["default_value"] = default_value
    result = send_ue("create_variable", params)
    time.sleep(DELAY)
    return result

def add_component(bp_name, component_type, component_name):
    result = send_ue("add_component_to_blueprint", {
        "blueprint_name": bp_name,
        "component_type": component_type,
        "component_name": component_name
    })
    time.sleep(DELAY)
    return result

def compile_blueprint(name):
    result = send_ue("compile_blueprint", {"name": name})
    time.sleep(DELAY)
    return result

# ============================================================
print("=" * 60)
print("Forest Realm - Blueprint Creation")
print("=" * 60)

# 测试连接
print("\n[0] Testing connection...")
send_ue("ping")

# ============================================================
# BP_SpiritLight - 精灵之光收集品
# ============================================================
print("\n[1] Creating BP_SpiritLight...")
create_blueprint("BP_SpiritLight", "Actor")
add_variable("BP_SpiritLight", "LightValue", "Integer", 1)
add_variable("BP_SpiritLight", "IsCollected", "Boolean", False)
add_variable("BP_SpiritLight", "FloatSpeed", "Float", 2.0)
add_variable("BP_SpiritLight", "FloatHeight", "Float", 0.3)
compile_blueprint("BP_SpiritLight")

# ============================================================
# BP_StarFragment - 星辰碎片
# ============================================================
print("\n[2] Creating BP_StarFragment...")
create_blueprint("BP_StarFragment", "Actor")
add_variable("BP_StarFragment", "FragmentValue", "Integer", 1)
add_variable("BP_StarFragment", "IsCollected", "Boolean", False)
compile_blueprint("BP_StarFragment")

# ============================================================
# BP_MushroomPlatform - 蘑菇弹跳平台
# ============================================================
print("\n[3] Creating BP_MushroomPlatform...")
create_blueprint("BP_MushroomPlatform", "Actor")
add_variable("BP_MushroomPlatform", "BounceForce", "Float", 1500.0)
add_variable("BP_MushroomPlatform", "BounceCooldown", "Float", 0.5)
add_variable("BP_MushroomPlatform", "IsBouncing", "Boolean", False)
compile_blueprint("BP_MushroomPlatform")

# ============================================================
# BP_CrystalPuzzle - 水晶谜题
# ============================================================
print("\n[4] Creating BP_CrystalPuzzle...")
create_blueprint("BP_CrystalPuzzle", "Actor")
add_variable("BP_CrystalPuzzle", "IsActive", "Boolean", False)
add_variable("BP_CrystalPuzzle", "RotationStep", "Float", 45.0)
add_variable("BP_CrystalPuzzle", "TargetAngle", "Float", 0.0)
compile_blueprint("BP_CrystalPuzzle")

# ============================================================
# BP_HiddenFlower - 隐藏花朵
# ============================================================
print("\n[5] Creating BP_HiddenFlower...")
create_blueprint("BP_HiddenFlower", "Actor")
add_variable("BP_HiddenFlower", "IsRevealed", "Boolean", False)
add_variable("BP_HiddenFlower", "RevealRadius", "Float", 3.0)
compile_blueprint("BP_HiddenFlower")

# ============================================================
# BP_TreeSpirit - 树灵 NPC
# ============================================================
print("\n[6] Creating BP_TreeSpirit...")
create_blueprint("BP_TreeSpirit", "Actor")
add_variable("BP_TreeSpirit", "HasSpoken", "Boolean", False)
add_variable("BP_TreeSpirit", "DialogueText", "String", "Welcome, traveler...")
add_variable("BP_TreeSpirit", "InteractionRadius", "Float", 5.0)
compile_blueprint("BP_TreeSpirit")

# ============================================================
# BP_WorldTreeAltar - 世界之树祭坛
# ============================================================
print("\n[7] Creating BP_WorldTreeAltar...")
create_blueprint("BP_WorldTreeAltar", "Actor")
add_variable("BP_WorldTreeAltar", "RequiredLights", "Integer", 20)
add_variable("BP_WorldTreeAltar", "DepositedLights", "Integer", 0)
add_variable("BP_WorldTreeAltar", "IsActivated", "Boolean", False)
compile_blueprint("BP_WorldTreeAltar")

# ============================================================
# BP_GameMode - 游戏模式
# ============================================================
print("\n[8] Creating BP_GameMode...")
create_blueprint("BP_GameMode", "GameModeBase")
add_variable("BP_GameMode", "TotalSpiritLights", "Integer", 20)
add_variable("BP_GameMode", "CollectedLights", "Integer", 0)
add_variable("BP_GameMode", "GameState", "String", "Playing")
compile_blueprint("BP_GameMode")

# ============================================================
# BP_PlayerCharacter - 玩家角色
# ============================================================
print("\n[9] Creating BP_PlayerCharacter...")
create_blueprint("BP_PlayerCharacter", "Character")
add_variable("BP_PlayerCharacter", "CurrentSpiritLights", "Integer", 0)
add_variable("BP_PlayerCharacter", "MaxHealth", "Float", 100.0)
add_variable("BP_PlayerCharacter", "CurrentHealth", "Float", 100.0)
add_variable("BP_PlayerCharacter", "CanDoubleJump", "Boolean", False)
add_variable("BP_PlayerCharacter", "CanDash", "Boolean", False)
add_variable("BP_PlayerCharacter", "CanGlide", "Boolean", False)
add_variable("BP_PlayerCharacter", "CanFly", "Boolean", False)
add_variable("BP_PlayerCharacter", "DashCooldown", "Float", 2.0)
add_variable("BP_PlayerCharacter", "MoveSpeed", "Float", 600.0)
compile_blueprint("BP_PlayerCharacter")

print("\n" + "=" * 60)
print("All Blueprints created!")
print("=" * 60)
