# Blender↔UE Bridge v2

AI 驱动的 Blender ↔ Unreal Engine 全流程桥接系统，通过 MCP 协议统一控制两个引擎。

**v2 核心升级**（对比 v1）：
- ✅ **自带 Blender Addon**（零依赖，线程安全）— 不再依赖外部 MCP 插件
- ✅ **分层工具**：宏层（墙/屋顶/门窗/楼梯）→ 原子层 → 验证层 → 视觉层
- ✅ **真实拓扑建模**：墙壁门窗开洞为四边面构造，非堆叠方块
- ✅ **网格质量检查**：非流形边/孤立顶点/零面积面/质量评分
- ✅ **测量与断言**：距离/间隙/对齐/接触验证
- ✅ **6 个专家提示词**：拓扑/尺度/PBR 材质/灯光/自审工作流
- ✅ **线程安全协议**：长度前缀 JSON + 主线程队列 + 大操作直连
- ✅ **62 个 MCP 工具**（v1 为 27 个）

## 架构

```
Claude Code / AI Client
        │
        ▼ (MCP stdio)
┌─────────────────────────┐
│  Blender↔UE Bridge      │
│  MCP Server (FastMCP)   │
├────────────┬────────────┤
│ Blender    │ UE         │
│ Client     │ Client     │  ← JSON over TCP
└──────┬─────┴──────┬─────┘
       │ TCP:9876  │ TCP:55557
       ▼           ▼
┌──────────────┐ ┌──────────┐
│ blender_addon│ │ Unreal   │
│ (Blender 插件)│ │ MCP 插件 │
│ 线程安全队列  │ │          │
└──────────────┘ └──────────┘
```

**Blender 通信协议**：4 字节大端长度头 + UTF-8 JSON
- 常规命令：入队 → 返回排号 → 客户端轮询（主线程安全）
- 大操作（导出/烘焙）：标记 `large` → 专用线程执行 → 直接回写
- 自动重试：addon 重启后可自动恢复连接

## 安装

### 前置要求
- Python 3.11+
- Blender 4.0+（只装了 `bpy` 就够 — addon 零依赖）
- Unreal Engine 5.3+（UnrealMCP 插件已启用）

### 步骤

1. **安装 Blender Addon**：
```bash
cd blender-ue-bridge
python scripts/install_addon.py          # 自动检测 Blender 版本目录
# 或指定: python scripts/install_addon.py --blender-version 4.2
# 或打包: python scripts/install_addon.py --zip blender_addon.zip
```
然后在 Blender 中启用：**编辑 > 偏好设置 > 插件 > 搜索 "BlenderUE Bridge" > 勾选**。
启用后 Sidebar 右侧出现 "Bridge" 面板显示服务器状态。

2. **安装 MCP 依赖**：
```bash
pip install mcp fastmcp
```

3. **配置 Claude Code MCP**：
```bash
python scripts/setup_mcp.py install
```

4. **测试连接**：
```bash
python scripts/test_bridge.py    # 端到端测试 (需 Blender 运行中)
python scripts/test_protocol.py  # 协议层测试 (无需 Blender)
```

5. **演示**：
```bash
python scripts/demo_precision.py         # 精确建模演示 (中世纪村庄)
python scripts/demo_precision.py --to-ue  # 构建后导入 UE
```

## MCP 工具总览 (62 个)

### 宏层 — LLM 首选（任务级，已验证拓扑）

| 工具 | 说明 |
|------|------|
| `create_wall` | 墙壁（真实门窗开洞，全四边面） |
| `create_roof` | 屋顶（gable/hip/flat/pyramid，带挑檐） |
| `create_door` / `create_window` | 门（框+扇+把手）/ 窗（框+玻璃+竖棂+窗台） |
| `create_staircase` | 楼梯（单一网格，全四边面） |
| `create_table` / `create_chair` | 家具 |
| `create_column` | 柱（柱身+柱头+柱基） |
| `create_tree` / `create_rock` | 程序化自然资产 |
| `build_medieval_house` | **完整房屋工作流**（墙开洞+门+窗+屋顶+烟囱+斜切+材质） |

### 原子层（精确控制）

| 工具 | 说明 |
|------|------|
| `create_blender_object` | 精确尺寸几何体（米） |
| `set_blender_transform` / `set_blender_origin` | 变换 / 原点（bottom/center/top） |
| `extrude_blender_face` / `inset_blender_face` | 挤出 / 内缩 |
| `loop_cut_blender` / `bevel_blender_edges` | 环切 / 斜切 |
| `boolean_blender` | 布尔（union/difference/intersect） |
| `add_blender_modifier` / `apply_blender_modifier` | bevel/solidify/subdivision/mirror/... |
| `set_blender_material` | PBR 材质 |

### 验证层（质量保证）

| 工具 | 说明 |
|------|------|
| `check_mesh_quality` / `check_scene_quality` | 非流形/孤立顶点/零面积/质量分（目标 ≥90） |
| `measure_distance` / `measure_gap` / `measure_alignment` | 距离/间隙/对齐 |
| `assert_dimensions` / `assert_contact` | 尺寸/接触断言 |

### 视觉层

| 工具 | 说明 |
|------|------|
| `capture_blender_screenshot` | OpenGL 快速截图（毫秒级，用于自审） |
| `export_blender_model` | 导出 FBX/GLB（正确轴/单位/嵌入纹理） |

### UE 层 + 传输层

| 工具 | 说明 |
|------|------|
| `spawn_ue_actor` / `set_ue_actor_transform` / `delete_ue_actor` | Actor 管理 |
| `create_ue_blueprint` + 组件/变量/编译 | Blueprint 结构化操作 |
| `apply_ue_material` / `get_ue_materials` | 材质 |
| `transfer_model` / `batch_transfer_models` | Blender→UE 完整管线 |
| `create_ue_town` / `create_ue_castle` / `create_ue_maze` | 场景生成 |

### 专家提示词（6 个）

`blender_best_practices` · `topology_best_practices` · `scale_reference_guide` ·
`material_workflow_guide` · `lighting_principles` · `auto_critique_workflow`

## 使用示例

```
"检查 Blender 和 UE 的连接状态"                     → bridge_status

"在 Blender 建一栋 6x5x3m 的中世纪房屋，
 门宽1m 高2.1m 在中间，3个窗，山墙屋顶"              → build_medieval_house

"检查刚才的房屋网格质量，然后截图看看"               → check_scene_quality + capture_blender_screenshot

"墙宽0.2m，验证厚度对不对"                          → assert_dimensions

"把房屋导出FBX并导入UE的 /Game/VillageDemo/"         → transfer_model / export_blender_model
```

## 配置

`config.json`：
- `unreal.content_dir`：UE 项目 Content 目录（可用环境变量 `UE_CONTENT_DIR` 覆盖，多项目）
- `shared_assets.base_dir`：留空 = 项目内 `shared_assets/`（可用 `BRIDGE_SHARED_DIR` 覆盖）
- Blender 端口 9876（addon 固定），UE 端口 55557

## 项目结构

```
blender-ue-bridge/
├── blender_addon/             # Blender 插件 (零依赖)
│   ├── __init__.py            # 注册 + 启停
│   ├── server.py              # TCP 服务器 + 线程安全队列
│   ├── protocol.py            # 长度前缀协议
│   ├── commands.py            # 原子命令 (创建/变换/网格编辑/材质/测量/质量)
│   ├── macros.py              # 宏命令 (墙/屋顶/门窗/楼梯/家具/房屋工作流)
│   └── ui.py                  # Sidebar 面板
├── mcp_server/
│   ├── server.py              # MCP 主服务器 (62 工具)
│   ├── blender_tools.py       # 分层工具注册
│   ├── blender_client.py      # 新协议客户端 (排队/轮询/重试)
│   ├── ue_client.py           # UE 客户端
│   ├── asset_pipeline.py      # 资产管线
│   ├── vision_feedback.py     # 视觉反馈
│   └── prompts.py             # 专家提示词
├── scripts/
│   ├── install_addon.py       # Addon 安装器
│   ├── setup_mcp.py           # MCP 配置
│   ├── test_bridge.py         # 端到端测试
│   ├── test_protocol.py       # 协议层测试 (无需 Blender)
│   └── demo_precision.py      # 精确建模演示
├── shared_assets/             # 资产交换目录
├── config.json
└── pyproject.toml
```

## 许可证

MIT License
