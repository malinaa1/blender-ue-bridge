"""
Blender↔UE 资产管线 — 自动化模型/材质/纹理的导出和导入

核心流程:
1. Blender 导出 FBX/glTF → shared_assets/
2. 烘焙程序化材质 → PNG 纹理
3. UE 导入 FBX + 纹理 → 项目 Content/
"""

import os
import json
import logging
from datetime import datetime

from .blender_client import BlenderClient
from .ue_client import UEClient

logger = logging.getLogger(__name__)

# 加载配置
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
def _load_config():
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class AssetPipeline:
    """Blender ↔ UE 资产流转管线"""

    def __init__(self, blender: BlenderClient, ue: UEClient,
                 shared_dir: str = "",
                 ue_content_dir: str = ""):
        self.blender = blender
        self.ue = ue
        if not shared_dir:
            # 默认使用项目内 shared_assets/
            shared_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "shared_assets")
        self.shared_dir = shared_dir
        self.models_dir = os.path.join(shared_dir, "models")
        self.textures_dir = os.path.join(shared_dir, "textures")
        self.materials_dir = os.path.join(shared_dir, "materials")

        # 确保目录存在
        for d in [self.models_dir, self.textures_dir, self.materials_dir]:
            os.makedirs(d, exist_ok=True)

        # UE 项目 Content 目录
        if not ue_content_dir:
            cfg = _load_config()
            ue_content_dir = cfg.get("unreal", {}).get("content_dir", "")
        self.ue_content_dir = ue_content_dir

    def _import_to_ue_project(self, file_path: str, ue_destination: str) -> dict:
        """
        通过文件复制将资产导入 UE 项目 Content 目录
        UE 会自动检测新文件并导入
        """
        import shutil

        if not self.ue_content_dir:
            # 尝试自动检测 UE 项目 Content 目录
            return {"success": False, "error": "未配置 UE 项目 Content 目录，请在 config.json 中设置 unreal.content_dir"}

        # 解析 UE 路径 → 文件系统路径
        # /Game/BridgeTest/ → Content/BridgeTest/
        relative_path = ue_destination.replace("/Game/", "").strip("/")
        dest_dir = os.path.join(self.ue_content_dir, relative_path)
        os.makedirs(dest_dir, exist_ok=True)

        # 复制文件
        filename = os.path.basename(file_path)
        dest_path = os.path.join(dest_dir, filename)
        shutil.copy2(file_path, dest_path)

        # 同时复制关联的纹理文件（如果有）
        tex_dir = os.path.join(os.path.dirname(file_path), "textures")
        if os.path.exists(tex_dir):
            for tex_file in os.listdir(tex_dir):
                src = os.path.join(tex_dir, tex_file)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(dest_dir, tex_file))

        return {
            "success": True,
            "source": file_path,
            "destination": dest_path,
            "ue_path": ue_destination
        }

    def transfer_model(self, object_name: str, ue_destination: str = "/Game/Assets/",
                       format: str = "fbx", bake_textures: bool = True,
                       texture_resolution: int = 2048) -> dict:
        """
        完整的模型传输流程: Blender 导出 → (烘焙纹理) → UE 导入

        Args:
            object_name: Blender 中的对象名称
            ue_destination: UE 中的目标路径
            format: 导出格式 (fbx / glb)
            bake_textures: 是否烘焙材质纹理
            texture_resolution: 烹焙纹理分辨率
        """
        result = {"steps": [], "success": False}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        asset_name = f"{object_name}_{timestamp}"

        # Step 1: 从 Blender 导出
        logger.info(f"Step 1: 从 Blender 导出 {object_name} ({format})")
        if format == "fbx":
            export_path = os.path.join(self.models_dir, f"{asset_name}.fbx")
            export_result = self.blender.export_fbx(object_name, export_path)
        else:
            export_path = os.path.join(self.models_dir, f"{asset_name}.glb")
            export_result = self.blender.export_gltf(object_name, export_path)

        result["steps"].append({"action": "blender_export", "result": export_result})

        if export_result.get("status") == "error":
            result["error"] = f"Blender 导出失败: {export_result.get('message')}"
            return result

        # 检查文件是否生成
        if not os.path.exists(export_path):
            result["error"] = f"导出文件未生成: {export_path}"
            return result

        result["export_path"] = export_path

        # Step 2: 烘焙纹理（可选）
        if bake_textures:
            logger.info(f"Step 2: 烘焙材质纹理 ({texture_resolution}px)")
            tex_dir = os.path.join(self.textures_dir, asset_name)
            bake_result = self.blender.bake_textures(
                object_name, tex_dir, texture_resolution
            )
            result["steps"].append({"action": "bake_textures", "result": bake_result})
            result["texture_dir"] = tex_dir

        # Step 3: 导入到 UE（通过文件复制到 Content 目录）
        logger.info(f"Step 3: 导入到 UE ({ue_destination})")
        import_result = self._import_to_ue_project(export_path, ue_destination)
        result["steps"].append({"action": "ue_import", "result": import_result})

        if not import_result.get("success"):
            result["error"] = f"UE 导入失败: {import_result.get('error', '未知错误')}"
            return result

        result["success"] = True
        result["ue_path"] = f"{ue_destination}{asset_name}"
        logger.info(f"传输完成: {object_name} → {result['ue_path']}")
        return result

    def transfer_all(self, ue_destination: str = "/Game/Assets/",
                     format: str = "fbx") -> dict:
        """导出整个 Blender 场景并导入 UE"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_path = os.path.join(self.models_dir, f"scene_{timestamp}.fbx")

        # 导出整个场景
        export_result = self.blender.export_all_fbx(export_path)
        if export_result.get("status") == "error":
            return {"success": False, "error": export_result.get("message")}

        # 导入到 UE
        import_result = self.ue.import_asset(export_path, ue_destination)
        return {
            "success": True,
            "export_path": export_path,
            "import_result": import_result
        }

    def sync_material(self, object_name: str, ue_actor_name: str = "",
                       texture_resolution: int = 2048) -> dict:
        """
        同步 Blender 对象的材质到 UE

        1. 烘焙 Blender 材质为纹理
        2. 将纹理应用到 UE Actor
        """
        # 获取对象材质信息
        obj_info = self.blender.get_object_info(object_name)
        if obj_info.get("status") == "error":
            return {"success": False, "error": f"无法获取对象信息: {object_name}"}

        materials = obj_info.get("result", {}).get("materials", [])
        if not materials:
            return {"success": False, "error": f"对象 {object_name} 没有材质"}

        # 烘焙纹理
        tex_dir = os.path.join(self.textures_dir, object_name)
        bake_result = self.blender.bake_textures(
            object_name, tex_dir, texture_resolution
        )

        return {
            "success": True,
            "object": object_name,
            "materials": materials,
            "texture_dir": tex_dir,
            "bake_result": bake_result
        }

    def batch_transfer(self, object_names: list, ue_destination: str = "/Game/Assets/",
                       format: str = "fbx") -> dict:
        """批量传输多个对象"""
        results = {}
        for name in object_names:
            results[name] = self.transfer_model(name, ue_destination, format)
        return results

    def list_shared_assets(self) -> dict:
        """列出共享资产目录中的所有文件"""
        assets = {"models": [], "textures": [], "materials": []}

        for category, dir_path in [
            ("models", self.models_dir),
            ("textures", self.textures_dir),
            ("materials", self.materials_dir)
        ]:
            if os.path.exists(dir_path):
                for f in os.listdir(dir_path):
                    fpath = os.path.join(dir_path, f)
                    assets[category].append({
                        "name": f,
                        "path": fpath,
                        "size": os.path.getsize(fpath) if os.path.isfile(fpath) else 0
                    })

        return assets

    def cleanup_shared(self, max_age_hours: int = 24) -> dict:
        """清理超过指定时间的共享资产"""
        import time
        cleaned = []
        cutoff = time.time() - (max_age_hours * 3600)

        for dir_path in [self.models_dir, self.textures_dir, self.materials_dir]:
            if not os.path.exists(dir_path):
                continue
            for f in os.listdir(dir_path):
                fpath = os.path.join(dir_path, f)
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    cleaned.append(fpath)

        return {"cleaned": cleaned, "count": len(cleaned)}
