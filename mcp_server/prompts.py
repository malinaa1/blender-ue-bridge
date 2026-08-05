"""专家提示词 — 引导 LLM 达到专业建模水准 (fastmcp 3.x @mcp.prompt 装饰器)

用法: register_prompts(mcp) 在 server.py 中调用。
"""


# 每个提示词的内容定义 — (函数名, 标题, 内容)
_PROMPT_DEFS = [
    ("blender_best_practices", "Blender 精确建模最佳实践", """\
## Blender 精确建模最佳实践

### 尺寸
- 始终使用米 (m) 作为单位。UE 中 1 单位 = 1cm, 1m = 100 单位。
- 创建前先规划整体尺寸, 用 create_wall/floor/roof 等宏工具传精确参数。
- 放置对象时用 set_blender_transform 指定精确位置, 不要靠"看起来对"。

### 拓扑
- 优先四边面 (quad): 我们的宏工具 (墙壁/楼梯) 自动保证。
- 硬边加 Bevel 修改器 (width 0.01-0.03m, segments 1-2), 不要留尖锐边缘。
- 建模后运行 check_mesh_quality 验证: 目标 quality_score >= 90。
  - 非流形边、孤立顶点、零面积面、重复顶点都会拉低分数。

### 工作流
1. 宏工具优先: create_wall/create_roof/create_door 等 (已验证拓扑)
2. 需要细节时用原子工具: extrude_blender_face/inset_blender_face/bevel_blender_edges/boolean_blender
3. 复杂场景: 每步完成后 measure/assert 验证关键尺寸
4. 传输前: check_mesh_quality + capture_blender_screenshot 目检

### 材质
- 用 set_blender_material 设置 PBR 参数 (base_color/metallic/roughness)
- 金属: metallic 0.8-1.0, roughness 0.1-0.4
- 木材/石材: metallic 0, roughness 0.6-0.95
- 发光物: emission_strength 1-5

### 原点与放置
- 宏工具创建的对象原点在底部中心 — 直接放地面即可
- 原子创建的对象用 set_blender_origin(mode='bottom') 后放置
- 验证放置: measure_gap 检查接触, assert_contact 确认贴合"""),

    ("topology_best_practices", "四边面拓扑原则", """\
## 拓扑原则 (Topology Best Practices)

- 四边面 (quads) 是黄金标准: 变形、细分、UV 都依赖它
- 极点 (poles, 3/5 边汇聚点): 控制在 < 3 个, 放在平面区域
- N-gon (>4 边面): 禁止出现在可见/可变形区域
- 三角面: 允许在最终低模烘焙/游戏资产, 建模阶段避免
- 边流 (edge flow): 沿曲面曲率方向布线

我们的宏工具 (create_wall 等) 构造时保证全四边面。
检查: check_mesh_quality 报告的 quad_ratio 应 >= 0.9。"""),

    ("scale_reference_guide", "真实世界尺寸参考表 (米)", """\
## 真实世界尺寸参考 (米)

| 物体 | 尺寸 |
|------|------|
| 门 | 宽 0.9-1.0, 高 2.0-2.1, 厚 0.05-0.08 |
| 窗 | 宽 0.9-1.2, 高 1.0-1.4, 窗台离地 0.85-1.0 |
| 室内层高 | 2.7-3.0 |
| 桌子 | 高 0.72-0.78, 桌面厚 0.03-0.06 |
| 椅子 | 座高 0.42-0.48, 靠背高 0.85-0.95 |
| 床 | 1.6x2.0, 高 0.45 |
| 人 | 高 1.7-1.8 |
| 楼梯 | 踏面 0.25-0.30, 踢面 0.15-0.18, 宽 1.0-1.2 |
| 屋顶坡度 | 30-45° (瓦片), 60-75° (茅草) |
| 墙厚 | 砖 0.2-0.3, 木构 0.1-0.15 |
| 树干 | 直径 0.3-0.8 (橡树), 高 4-8 |
| 岩石 | 直径 0.5-2 |

UE 单位: 1m = 100 UE units。spawn_ue_actor 时 location 乘 100。"""),

    ("material_workflow_guide", "PBR 材质配方", """\
## PBR 材质配方 (Principled BSDF)

### 金属
- 金/铜: base (0.8, 0.6, 0.3), metallic 1.0, roughness 0.3
- 银/钢: base (0.8, 0.8, 0.85), metallic 1.0, roughness 0.2
- 拉丝铝: base (0.9, 0.9, 0.92), metallic 1.0, roughness 0.5

### 非金属
- 白墙灰泥: base (0.86, 0.83, 0.78), roughness 0.9
- 红砖: base (0.6, 0.25, 0.2), roughness 0.95
- 橡木: base (0.42, 0.28, 0.16), roughness 0.55
- 松木/浅木: base (0.8, 0.65, 0.4), roughness 0.6
- 深色木 (家具): base (0.25, 0.15, 0.08), roughness 0.45
- 花岗岩: base (0.55, 0.53, 0.5), roughness 0.95
- 玻璃: base (0.72, 0.82, 0.9), roughness 0.1, metallic 0

### 发光
- 火/灯: emission (1.0, 0.6, 0.2), strength 2-5
- 魔法蓝: emission (0.3, 0.5, 1.0), strength 2-4

### FBX → UE 注意
- FBX 导出不支持 transmission/clearcoat 输入 → 玻璃用低粗糙度亮色模拟
- 材质名会成为 UE 资产名: 用有意义的名称 (M_Wall_Plaster)"""),

    ("lighting_principles", "三点布光原则", """\
## 三点布光 (Three-Point Lighting)

- 主光 (Key): 45° 侧上, 强度 2-5 (PointLight) 或定向光
- 补光 (Fill): 相反侧, 强度 30-50% 主光
- 轮廓光 (Rim): 背后, 强度 60-80% 主光, 形成边缘分离

### 光色温
- 暖白 (室内/火光): 3000K, 颜色 (1.0, 0.9, 0.7)
- 冷白 (月光): 6500K, 颜色 (0.7, 0.8, 1.0)
- 黄昏: (1.0, 0.6, 0.3)

UE: spawn_ue_actor PointLight, 强度单位 1000 (1W 灯泡 = 1000 lumens)"""),

    ("auto_critique_workflow", "视觉反馈闭环", """\
## 自动批评工作流 (Auto-Critique)

建模过程中定期执行:
1. capture_blender_screenshot(tag=阶段名)
2. 审视截图, 检查: 比例失调? 硬边未斜切? 材质粗糙? 位置错误?
3. 用测量工具验证: measure_dimensions / measure_gap / assert_contact
4. 修正: 调整参数 → 重新截图对比

每完成一个主要部分 (墙体/屋顶/家具) 执行一次, 最多 3 轮。
最后 check_mesh_quality 确认质量分 >= 90 再传输。"""),
]


def register_prompts(mcp):
    """注册所有专家提示词 (fastmcp 3.x)"""
    for name, _title, content in _PROMPT_DEFS:
        def make_prompt(content=content):
            def _prompt() -> str:
                return content
            _prompt.__name__ = name
            _prompt.__doc__ = f"专家提示词: {name}"
            return _prompt
        mcp.prompt()(make_prompt())
