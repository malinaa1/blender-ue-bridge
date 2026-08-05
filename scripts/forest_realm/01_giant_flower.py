"""
Forest Realm - 巨花建模脚本
SM_Giant_Flower: 玩家苏醒点，巨大的花苞
"""
import socket
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mcp_server.blender_client import BlenderClient

def send_blender(code):
    """Execute Blender Python code"""
    client = BlenderClient()
    result = client.execute_code(code)
    print(f"  Blender: {result}")
    time.sleep(0.5)
    return result

def create_giant_flower():
    """创建巨花模型 - 玩家苏醒点"""
    print("\n=== 创建 SM_Giant_Flower ===")

    # 清空场景
    send_blender("""
import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
""")

    # 创建花茎
    send_blender("""
import bpy, bmesh, math, random
from mathutils import Vector

def bmesh_to_object(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

# 花茎 - 使用锥体模拟
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=12,
    radius1=0.4, radius2=0.25, depth=3.0)
stem = bmesh_to_object(bm, "Stem")
stem.location.z = 1.5

# 添加弯曲效果 - 修改顶点位置
for v in stem.data.vertices:
    z = v.co.z
    # 越高越弯曲
    bend = (z / 3.0) ** 2 * 0.3
    v.co.x += bend * 0.5
    v.co.y += bend * 0.3
""")

    # 创建花苞（外层花瓣）
    send_blender("""
import bpy, bmesh, math
from mathutils import Vector

def bmesh_to_object(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

# 外层花瓣 - 6片大花瓣
petals = []
num_petals = 6
for i in range(num_petals):
    angle = (2 * math.pi * i / num_petals)
    bm = bmesh.new()

    # 每片花瓣是一个弯曲的平面
    length = 1.8
    width = 0.8
    segments = 8

    for s in range(segments + 1):
        t = s / segments
        # 花瓣从底部到顶部逐渐张开
        spread = t ** 0.5 * 0.6
        w = width * (0.3 + 0.7 * math.sin(t * math.pi))

        for side in [-1, 1]:
            x = side * w * 0.5
            y = -spread
            z = t * length
            # 添加弯曲
            z += math.sin(t * math.pi) * 0.4
            bm.verts.new((x, y, z))

    # 创建面
    verts = list(bm.verts)
    for s in range(segments):
        i = s * 2
        bm.faces.new([verts[i], verts[i+1], verts[i+3], verts[i+2]])

    bm.normal_update()
    petal = bmesh_to_object(bm, f"Petal_{i}")

    # 旋转花瓣
    petal.rotation_euler = (math.radians(-15), 0, angle)
    petal.location = (
        math.cos(angle) * 0.3,
        math.sin(angle) * 0.3,
        2.8
    )
    petals.append(petal)
""")

    # 创建花蕊
    send_blender("""
import bpy, bmesh, math
from mathutils import Vector

def bmesh_to_object(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

# 花蕊 - 发光球体
bm = bmesh.new()
bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.5)
center = bmesh_to_object(bm, "FlowerCenter")
center.location.z = 3.2

# 花蕊上的小突起
for i in range(12):
    angle = 2 * math.pi * i / 12
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.08)
    dot = bmesh_to_object(bm, f"Stamen_{i}")
    dot.location = (
        math.cos(angle) * 0.35,
        math.sin(angle) * 0.35,
        3.3
    )
""")

    # 创建叶子
    send_blender("""
import bpy, bmesh, math
from mathutils import Vector

def bmesh_to_object(bm, name):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

# 底部大叶子
for i in range(4):
    angle = math.pi * 0.5 * i + 0.3
    bm = bmesh.new()

    # 叶子形状
    verts = [
        bm.verts.new((0, 0, 0)),           # 叶基
        bm.verts.new((0.3, -0.8, 0.1)),    # 左
        bm.verts.new((0.15, -1.6, 0.3)),   # 左中
        bm.verts.new((0, -2.0, 0.4)),      # 叶尖
        bm.verts.new((-0.15, -1.6, 0.3)),  # 右中
        bm.verts.new((-0.3, -0.8, 0.1)),   # 右
        bm.verts.new((0, -0.4, 0.15)),     # 中脉
    ]

    bm.faces.new([verts[0], verts[1], verts[6]])
    bm.faces.new([verts[1], verts[2], verts[6]])
    bm.faces.new([verts[2], verts[3], verts[6]])
    bm.faces.new([verts[3], verts[4], verts[6]])
    bm.faces.new([verts[4], verts[5], verts[6]])
    bm.faces.new([verts[5], verts[0], verts[6]])

    bm.normal_update()
    leaf = bmesh_to_object(bm, f"Leaf_{i}")
    leaf.rotation_euler = (math.radians(30), 0, angle)
    leaf.location = (
        math.cos(angle) * 0.5,
        math.sin(angle) * 0.5,
        0.3
    )
""")

    # 添加材质
    send_blender("""
import bpy

# 花瓣材质 - 粉色渐变
mat_petal = bpy.data.materials.new("M_Petal")
mat_petal.use_nodes = True
nodes = mat_petal.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.95, 0.4, 0.6, 1.0)
bsdf.inputs['Roughness'].default_value = 0.6
bsdf.inputs['Specular IOR Level'].default_value = 0.3

# 花蕊材质 - 金色发光
mat_center = bpy.data.materials.new("M_FlowerCenter")
mat_center.use_nodes = True
nodes = mat_center.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (1.0, 0.85, 0.2, 1.0)
bsdf.inputs['Emission Color'].default_value = (1.0, 0.9, 0.3, 1.0)
bsdf.inputs['Emission Strength'].default_value = 2.0
bsdf.inputs['Roughness'].default_value = 0.4

# 茎材质 - 绿色
mat_stem = bpy.data.materials.new("M_Stem")
mat_stem.use_nodes = True
nodes = mat_stem.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.2, 0.5, 0.15, 1.0)
bsdf.inputs['Roughness'].default_value = 0.8

# 叶子材质 - 深绿
mat_leaf = bpy.data.materials.new("M_Leaf")
mat_leaf.use_nodes = True
nodes = mat_leaf.node_tree.nodes
bsdf = nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.15, 0.45, 0.1, 1.0)
bsdf.inputs['Roughness'].default_value = 0.7

# 应用材质
for obj in bpy.data.objects:
    if 'Petal' in obj.name:
        if obj.data.materials:
            obj.data.materials[0] = mat_petal
        else:
            obj.data.materials.append(mat_petal)
    elif 'Flower' in obj.name or 'Stamen' in obj.name:
        if obj.data.materials:
            obj.data.materials[0] = mat_center
        else:
            obj.data.materials.append(mat_center)
    elif 'Stem' in obj.name:
        if obj.data.materials:
            obj.data.materials[0] = mat_stem
        else:
            obj.data.materials.append(mat_stem)
    elif 'Leaf' in obj.name:
        if obj.data.materials:
            obj.data.materials[0] = mat_leaf
        else:
            obj.data.materials.append(mat_leaf)
""")

    # 合并所有对象并导出
    send_blender("""
import bpy, os

# 选择所有对象
bpy.ops.object.select_all(action='SELECT')
bpy.context.view_layer.objects.active = bpy.data.objects.get('Stem')

# 合并
bpy.ops.object.join()

# 重命名
obj = bpy.context.active_object
obj.name = "SM_Giant_Flower"

# 应用变换
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# 设置原点到物体底部
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
obj.location.z = 0

print(f"Created: {obj.name}, Vertices: {len(obj.data.vertices)}, Faces: {len(obj.data.polygons)}")
""")

    # 导出 FBX
    send_blender("""
import bpy, os

export_dir = "D:/MOD/input/DONG/Content/ForestRealm/Models"
os.makedirs(export_dir, exist_ok=True)

filepath = os.path.join(export_dir, "SM_Giant_Flower.fbx")
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
print(f"Exported: {filepath}")
""")

    print("\n✅ SM_Giant_Flower 创建完成!")

if __name__ == "__main__":
    create_giant_flower()
