"""
Forest Realm - 自然资产批量建模
创建: 树木、蘑菇、水晶、岩石、花朵
"""
import socket
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mcp_server.blender_client import BlenderClient

client = BlenderClient()
EXPORT_DIR = "D:/MOD/input/DONG/Content/ForestRealm/Models"

def send_blender(code):
    result = client.execute_code(code)
    if result.get('status') == 'error':
        print(f"  ERROR: {result.get('message', 'Unknown')}")
    time.sleep(0.3)
    return result

def export_fbx(name):
    """导出当前选中对象为 FBX"""
    send_blender(f"""
import bpy, os
export_dir = "{EXPORT_DIR}"
os.makedirs(export_dir, exist_ok=True)
filepath = os.path.join(export_dir, "{name}.fbx")
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.fbx(
    filepath=filepath,
    use_selection=True,
    apply_scale_options='FBX_SCALE_ALL',
    bake_space_transform=True,
    mesh_smooth_type='OFF',
    path_mode='COPY',
    embed_textures=True,
    add_leaf_bones=False,
    bake_anim=False,
)
print(f"Exported: {{filepath}}")
""")
    print(f"  [OK] {name}")

def clear_scene():
    send_blender("""
import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
""")

# ============================================================
# 1. SM_Tree_Oak - 橡树
# ============================================================
def create_oak_tree():
    print("\n--- SM_Tree_Oak ---")
    clear_scene()
    send_blender("""
import bpy, bmesh, math, random
from mathutils import Vector

def bm_to_obj(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

random.seed(100)

# 树干
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.35, radius2=0.15, depth=3.5)
trunk = bm_to_obj(bm, "Trunk")
trunk.location.z = 1.75

# 树枝
for i in range(5):
    angle = 2 * math.pi * i / 5 + random.uniform(-0.3, 0.3)
    h = 1.5 + random.uniform(0, 1.5)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.12, radius2=0.05, depth=random.uniform(1.0, 2.0))
    branch = bm_to_obj(bm, f"Branch_{i}")
    branch.location = (math.cos(angle)*0.25, math.sin(angle)*0.25, h)
    branch.rotation_euler = (math.radians(random.uniform(20, 50)), 0, angle)

# 树冠 - 多个球体
for i in range(6):
    angle = random.uniform(0, 2*math.pi)
    dist = random.uniform(0.3, 1.2)
    z = 3.0 + random.uniform(-0.5, 1.0)
    r = random.uniform(0.8, 1.5)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r)
    for v in bm.verts:
        v.co += Vector((random.uniform(-0.1,0.1), random.uniform(-0.1,0.1), random.uniform(-0.1,0.1))) * r
    foliage = bm_to_obj(bm, f"Foliage_{i}")
    foliage.location = (math.cos(angle)*dist, math.sin(angle)*dist, z)

# 应用绿色材质
mat = bpy.data.materials.new("M_TreeOak")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs[0].default_value = (0.15, 0.45, 0.1, 1.0)  # Base Color
    bsdf.inputs['Roughness'].default_value = 0.8

mat_bark = bpy.data.materials.new("M_Bark")
mat_bark.use_nodes = True
bsdf2 = mat_bark.node_tree.nodes.get("Principled BSDF")
if bsdf2:
    bsdf2.inputs[0].default_value = (0.35, 0.2, 0.1, 1.0)
    bsdf2.inputs['Roughness'].default_value = 0.9

for obj in bpy.data.objects:
    if 'Foliage' in obj.name:
        obj.data.materials.append(mat)
    elif 'Trunk' in obj.name or 'Branch' in obj.name:
        obj.data.materials.append(mat_bark)

bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = bpy.data.objects.get('Trunk')
bpy.ops.object.join()
bpy.context.active_object.name = "SM_Tree_Oak"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
""")
    export_fbx("SM_Tree_Oak")

# ============================================================
# 2. SM_Tree_Willow - 柳树
# ============================================================
def create_willow_tree():
    print("\n--- SM_Tree_Willow ---")
    clear_scene()
    send_blender("""
import bpy, bmesh, math, random
from mathutils import Vector

def bm_to_obj(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

random.seed(200)

# 树干 - 弯曲
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.4, radius2=0.2, depth=4.0)
trunk = bm_to_obj(bm, "Trunk")
trunk.location.z = 2.0

# 添加弯曲
for v in trunk.data.vertices:
    t = (v.co.z + 2.0) / 4.0
    v.co.x += math.sin(t * math.pi) * 0.5

# 垂枝 - 长条形
for i in range(12):
    angle = 2 * math.pi * i / 12
    r = random.uniform(1.5, 2.5)
    bm = bmesh.new()
    # 垂下的枝条
    for s in range(8):
        t = s / 7.0
        x = math.cos(angle) * r * (1 - t * 0.3)
        y = math.sin(angle) * r * (1 - t * 0.3)
        z = 3.5 - t * 3.0  # 垂下
        bm.verts.new((x, y, z))
    verts = list(bm.verts)
    for s in range(len(verts)-1):
        bm.faces.new([verts[s], verts[s+1], verts[(s+1)%len(verts)], verts[s%len(verts)]])
    bm.normal_update()
    vine = bm_to_obj(bm, f"Vine_{i}")

# 材质
mat = bpy.data.materials.new("M_Willow")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs[0].default_value = (0.1, 0.35, 0.08, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.75

for obj in bpy.data.objects:
    obj.data.materials.append(mat)

bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = bpy.data.objects.get('Trunk')
bpy.ops.object.join()
bpy.context.active_object.name = "SM_Tree_Willow"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
""")
    export_fbx("SM_Tree_Willow")

# ============================================================
# 3. SM_Mushroom_Giant - 巨型发光蘑菇
# ============================================================
def create_giant_mushroom():
    print("\n--- SM_Mushroom_Giant ---")
    clear_scene()
    send_blender("""
import bpy, bmesh, math, random
from mathutils import Vector

def bm_to_obj(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

# 蘑菇茎
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.25, radius2=0.18, depth=1.5)
stem = bm_to_obj(bm, "Stem")
stem.location.z = 0.75

# 蘑菇帽
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.9)
# 压扁成帽状
for v in bm.verts:
    if v.co.z > 0:
        v.co.z *= 0.4  # 上半部分压扁
    else:
        v.co.z = 0     # 下半部分切平
cap = bm_to_obj(bm, "Cap")
cap.location.z = 1.5

# 发光斑点
for i in range(8):
    angle = 2 * math.pi * i / 8
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.06)
    dot = bm_to_obj(bm, f"Dot_{i}")
    dot.location = (math.cos(angle)*0.6, math.sin(angle)*0.6, 1.55)

# 材质
mat_cap = bpy.data.materials.new("M_MushroomCap")
mat_cap.use_nodes = True
bsdf = mat_cap.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs[0].default_value = (0.4, 0.1, 0.7, 1.0)
    bsdf.inputs['Emission Color'].default_value = (0.5, 0.2, 0.9, 1.0)
    bsdf.inputs['Emission Strength'].default_value = 1.5

mat_stem = bpy.data.materials.new("M_MushroomStem")
mat_stem.use_nodes = True
bsdf2 = mat_stem.node_tree.nodes.get("Principled BSDF")
if bsdf2:
    bsdf2.inputs[0].default_value = (0.85, 0.8, 0.65, 1.0)

mat_dot = bpy.data.materials.new("M_MushroomDot")
mat_dot.use_nodes = True
bsdf3 = mat_dot.node_tree.nodes.get("Principled BSDF")
if bsdf3:
    bsdf3.inputs[0].default_value = (0.9, 0.8, 1.0, 1.0)
    bsdf3.inputs['Emission Color'].default_value = (0.8, 0.6, 1.0, 1.0)
    bsdf3.inputs['Emission Strength'].default_value = 3.0

for obj in bpy.data.objects:
    if 'Cap' in obj.name:
        obj.data.materials.append(mat_cap)
    elif 'Stem' in obj.name:
        obj.data.materials.append(mat_stem)
    elif 'Dot' in obj.name:
        obj.data.materials.append(mat_dot)

bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = bpy.data.objects.get('Stem')
bpy.ops.object.join()
bpy.context.active_object.name = "SM_Mushroom_Giant"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
""")
    export_fbx("SM_Mushroom_Giant")

# ============================================================
# 4. SM_Crystal - 水晶
# ============================================================
def create_crystal():
    print("\n--- SM_Crystal ---")
    clear_scene()
    send_blender("""
import bpy, bmesh, math, random
from mathutils import Vector

def bm_to_obj(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

# 主水晶柱
bm = bmesh.new()
# 六棱柱 + 尖顶
segments = 6
height = 2.0
radius = 0.3

# 底部
bottom = []
for i in range(segments):
    angle = 2 * math.pi * i / segments
    bottom.append(bm.verts.new((radius*math.cos(angle), radius*math.sin(angle), 0)))

# 中间
mid = []
for i in range(segments):
    angle = 2 * math.pi * i / segments
    mid.append(bm.verts.new((radius*math.cos(angle), radius*math.sin(angle), height*0.7)))

# 顶部尖
top = bm.verts.new((0, 0, height))

# 面
for i in range(segments):
    ni = (i+1) % segments
    bm.faces.new([bottom[i], bottom[ni], mid[ni], mid[i]])
    bm.faces.new([mid[i], mid[ni], top])
bm.faces.new(bottom)
bm.faces.new(mid)

crystal = bm_to_obj(bm, "Crystal")

# 小水晶
for j in range(3):
    bm = bmesh.new()
    h = random.uniform(0.8, 1.3)
    r = random.uniform(0.12, 0.2)
    angle_off = random.uniform(0, math.pi*2)
    bottom = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        bottom.append(bm.verts.new((r*math.cos(angle), r*math.sin(angle), 0)))
    mid = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        mid.append(bm.verts.new((r*math.cos(angle), r*math.sin(angle), h*0.7)))
    top = bm.verts.new((0, 0, h))
    for i in range(segments):
        ni = (i+1) % segments
        bm.faces.new([bottom[i], bottom[ni], mid[ni], mid[i]])
        bm.faces.new([mid[i], mid[ni], top])
    bm.faces.new(bottom)
    bm.faces.new(mid)
    small = bm_to_obj(bm, f"SmallCrystal_{j}")
    small.location = (math.cos(angle_off)*0.5, math.sin(angle_off)*0.5, 0)
    small.rotation_euler = (math.radians(random.uniform(-15, 15)), math.radians(random.uniform(-15, 15)), 0)

# 材质 - 半透明蓝紫
mat = bpy.data.materials.new("M_Crystal")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs[0].default_value = (0.3, 0.5, 0.9, 1.0)
    bsdf.inputs['Emission Color'].default_value = (0.4, 0.6, 1.0, 1.0)
    bsdf.inputs['Emission Strength'].default_value = 2.0
    bsdf.inputs['Roughness'].default_value = 0.1
    bsdf.inputs['Metallic'].default_value = 0.0
    bsdf.inputs['Specular IOR Level'].default_value = 0.8

for obj in bpy.data.objects:
    obj.data.materials.append(mat)

bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = bpy.data.objects.get('Crystal')
bpy.ops.object.join()
bpy.context.active_object.name = "SM_Crystal"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
""")
    export_fbx("SM_Crystal")

# ============================================================
# 5. SM_Rock - 岩石
# ============================================================
def create_rock():
    print("\n--- SM_Rock ---")
    clear_scene()
    send_blender("""
import bpy, bmesh, math, random
from mathutils import Vector

def bm_to_obj(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

random.seed(300)

# 主岩石 - 噪波变形的 ICO 球
bm = bmesh.new()
bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
for v in bm.verts:
    n = math.sin(v.co.x*3)*math.cos(v.co.y*3)*0.2 + math.sin(v.co.z*5)*0.15
    v.co *= (1.0 + n)
    v.co.z *= 0.6  # 压扁

rock = bm_to_obj(bm, "Rock")

# 苔藓部分 - 顶部
bm = bmesh.new()
bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.8)
for v in bm.verts:
    if v.co.z < 0:
        v.co.z = 0
    v.co *= 1.02
moss = bm_to_obj(bm, "Moss")
moss.location.z = 0.1

# 材质
mat_rock = bpy.data.materials.new("M_Rock")
mat_rock.use_nodes = True
bsdf = mat_rock.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs[0].default_value = (0.45, 0.42, 0.38, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.95

mat_moss = bpy.data.materials.new("M_Moss")
mat_moss.use_nodes = True
bsdf2 = mat_moss.node_tree.nodes.get("Principled BSDF")
if bsdf2:
    bsdf2.inputs[0].default_value = (0.2, 0.5, 0.15, 1.0)
    bsdf2.inputs['Roughness'].default_value = 0.85

rock.data.materials.append(mat_rock)
moss.data.materials.append(mat_moss)

bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = rock
bpy.ops.object.join()
bpy.context.active_object.name = "SM_Rock"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
""")
    export_fbx("SM_Rock")

# ============================================================
# 6. SM_Bridge_Wood - 木桥
# ============================================================
def create_bridge():
    print("\n--- SM_Bridge_Wood ---")
    clear_scene()
    send_blender("""
import bpy, bmesh, math
from mathutils import Vector

def bm_to_obj(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

# 桥面板
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
for v in bm.verts:
    v.co.x *= 2.0   # 宽
    v.co.y *= 4.0   # 长
    v.co.z *= 0.1   # 薄
deck = bm_to_obj(bm, "Deck")
deck.location.z = 1.0

# 扶手 - 两侧
for side in [-1, 1]:
    # 立柱
    for i in range(5):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.08, radius2=0.06, depth=1.5)
        post = bm_to_obj(bm, f"Post_{side}_{i}")
        post.location = (side * 1.8, -3.5 + i * 1.75, 1.75)

    # 横梁
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= 0.06
        v.co.y *= 4.0
        v.co.z *= 0.06
    rail = bm_to_obj(bm, f"Rail_{side}")
    rail.location = (side * 1.8, 0, 2.4)

# 材质
mat = bpy.data.materials.new("M_Wood")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs[0].default_value = (0.5, 0.3, 0.15, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.85

for obj in bpy.data.objects:
    obj.data.materials.append(mat)

bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = bpy.data.objects.get('Deck')
bpy.ops.object.join()
bpy.context.active_object.name = "SM_Bridge_Wood"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
""")
    export_fbx("SM_Bridge_Wood")

# ============================================================
# 7. SM_Altar - 祭坛
# ============================================================
def create_altar():
    print("\n--- SM_Altar ---")
    clear_scene()
    send_blender("""
import bpy, bmesh, math
from mathutils import Vector

def bm_to_obj(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

# 底座 - 圆形
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=2.0, radius2=1.8, depth=0.5)
base = bm_to_obj(bm, "Base")
base.location.z = 0.25

# 中层
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=1.5, radius2=1.3, depth=0.4)
mid = bm_to_obj(bm, "Mid")
mid.location.z = 0.7

# 顶部平台
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=1.0, radius2=1.0, depth=0.3)
top = bm_to_obj(bm, "Top")
top.location.z = 1.05

# 中央石碑
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
for v in bm.verts:
    v.co.x *= 0.4
    v.co.y *= 0.15
    v.co.z *= 1.2
stone = bm_to_obj(bm, "Stone")
stone.location.z = 1.8

# 符文环 - 小方块排列成圆
for i in range(12):
    angle = 2 * math.pi * i / 12
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.15)
    rune = bm_to_obj(bm, f"Rune_{i}")
    rune.location = (math.cos(angle)*1.6, math.sin(angle)*1.6, 0.95)

# 材质
mat = bpy.data.materials.new("M_Altar")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs[0].default_value = (0.7, 0.7, 0.75, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.6

mat_rune = bpy.data.materials.new("M_Rune")
mat_rune.use_nodes = True
bsdf2 = mat_rune.node_tree.nodes.get("Principled BSDF")
if bsdf2:
    bsdf2.inputs[0].default_value = (0.8, 0.9, 1.0, 1.0)
    bsdf2.inputs['Emission Color'].default_value = (0.6, 0.8, 1.0, 1.0)
    bsdf2.inputs['Emission Strength'].default_value = 2.0

for obj in bpy.data.objects:
    if 'Rune' in obj.name:
        obj.data.materials.append(mat_rune)
    else:
        obj.data.materials.append(mat)

bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = bpy.data.objects.get('Base')
bpy.ops.object.join()
bpy.context.active_object.name = "SM_Altar"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
""")
    export_fbx("SM_Altar")

# ============================================================
# 8. SM_World_Tree - 世界之树
# ============================================================
def create_world_tree():
    print("\n--- SM_World_Tree ---")
    clear_scene()
    send_blender("""
import bpy, bmesh, math, random
from mathutils import Vector

def bm_to_obj(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

random.seed(999)

# 巨大树干
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=2.0, radius2=0.8, depth=8.0)
trunk = bm_to_obj(bm, "Trunk")
trunk.location.z = 4.0

# 扭曲效果
for v in trunk.data.vertices:
    t = (v.co.z + 4.0) / 8.0
    angle = t * 1.5
    x, y = v.co.x, v.co.y
    v.co.x = x * math.cos(angle) - y * math.sin(angle)
    v.co.y = x * math.sin(angle) + y * math.cos(angle)

# 大型树根
for i in range(6):
    angle = 2 * math.pi * i / 6 + random.uniform(-0.2, 0.2)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.6, radius2=0.2, depth=3.0)
    root = bm_to_obj(bm, f"Root_{i}")
    root.location = (math.cos(angle)*1.5, math.sin(angle)*1.5, 0.5)
    root.rotation_euler = (math.radians(70), 0, angle)

# 巨大树冠
for i in range(8):
    angle = random.uniform(0, 2*math.pi)
    dist = random.uniform(1.0, 3.0)
    z = 7.0 + random.uniform(-1.0, 2.0)
    r = random.uniform(1.5, 3.0)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r)
    for v in bm.verts:
        v.co += Vector((random.uniform(-0.2,0.2), random.uniform(-0.2,0.2), random.uniform(-0.2,0.2))) * r
    canopy = bm_to_obj(bm, f"Canopy_{i}")
    canopy.location = (math.cos(angle)*dist, math.sin(angle)*dist, z)

# 发光纹路 - 沿树干的小球
for i in range(15):
    t = random.uniform(0, 1)
    angle = random.uniform(0, 2*math.pi)
    r = 1.5 * (1 - t * 0.5) + 0.3
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.08)
    glow = bm_to_obj(bm, f"Glow_{i}")
    glow.location = (math.cos(angle)*r, math.sin(angle)*r, t*8.0)

# 材质
mat_trunk = bpy.data.materials.new("M_WorldTreeTrunk")
mat_trunk.use_nodes = True
bsdf = mat_trunk.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs[0].default_value = (0.3, 0.18, 0.08, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.9

mat_canopy = bpy.data.materials.new("M_WorldTreeLeaf")
mat_canopy.use_nodes = True
bsdf2 = mat_canopy.node_tree.nodes.get("Principled BSDF")
if bsdf2:
    bsdf2.inputs[0].default_value = (0.1, 0.5, 0.2, 1.0)
    bsdf2.inputs['Roughness'].default_value = 0.7

mat_glow = bpy.data.materials.new("M_WorldTreeGlow")
mat_glow.use_nodes = True
bsdf3 = mat_glow.node_tree.nodes.get("Principled BSDF")
if bsdf3:
    bsdf3.inputs[0].default_value = (0.4, 0.9, 0.5, 1.0)
    bsdf3.inputs['Emission Color'].default_value = (0.5, 1.0, 0.6, 1.0)
    bsdf3.inputs['Emission Strength'].default_value = 5.0

for obj in bpy.data.objects:
    if 'Glow' in obj.name:
        obj.data.materials.append(mat_glow)
    elif 'Canopy' in obj.name:
        obj.data.materials.append(mat_canopy)
    else:
        obj.data.materials.append(mat_trunk)

bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = bpy.data.objects.get('Trunk')
bpy.ops.object.join()
bpy.context.active_object.name = "SM_World_Tree"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
""")
    export_fbx("SM_World_Tree")


# ============================================================
# 主程序
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("Forest Realm - 自然资产建模")
    print("=" * 50)

    os.makedirs(EXPORT_DIR, exist_ok=True)

    create_oak_tree()
    create_willow_tree()
    create_giant_mushroom()
    create_crystal()
    create_rock()
    create_bridge()
    create_altar()
    create_world_tree()

    print("\n" + "=" * 50)
    print("All nature assets created!")
    print("=" * 50)
