"""
视觉反馈闭环 — 截图 → AI 分析 → 迭代修正

支持 Blender 和 UE 的视口截图，以及基于描述的迭代修正循环。
"""

import os
import logging
from datetime import datetime

from .blender_client import BlenderClient
from .ue_client import UEClient

logger = logging.getLogger(__name__)


class VisionFeedback:
    """视觉反馈闭环系统"""

    def __init__(self, blender: BlenderClient, ue: UEClient,
                 screenshot_dir: str = ""):
        self.blender = blender
        self.ue = ue
        if not screenshot_dir:
            screenshot_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "shared_assets", "screenshots")
        self.screenshot_dir = screenshot_dir
        os.makedirs(screenshot_dir, exist_ok=True)

    def capture_blender(self, tag: str = "", width: int = 800, height: int = 600) -> dict:
        """截取 Blender 视口 (OpenGL 快速截图)"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"blender_{tag}_{timestamp}.png" if tag else f"blender_{timestamp}.png"
        filepath = os.path.join(self.screenshot_dir, filename)

        result = self.blender.get_screenshot(filepath, width, height)
        if result.get("status") == "success":
            return {
                "success": True,
                "engine": "blender",
                "filepath": filepath,
                "width": width,
                "height": height
            }
        return {"success": False, "error": result.get("message", "截图失败")}

    def get_blender_scene_description(self) -> dict:
        """获取 Blender 场景的文字描述（用于 Vision 分析上下文）"""
        scene_info = self.blender.get_scene_info()
        if scene_info.get("status") == "error":
            return {"error": scene_info.get("message")}

        objects = scene_info.get("result", {}).get("objects", [])
        desc_parts = []
        for obj in objects:
            desc_parts.append(
                f"- {obj['name']} (类型: {obj['type']}, "
                f"位置: {obj.get('location', '未知')})"
            )

        return {
            "scene_name": scene_info.get("result", {}).get("name", ""),
            "object_count": scene_info.get("result", {}).get("object_count", 0),
            "description": "\n".join(desc_parts)
        }

    def get_ue_scene_description(self) -> dict:
        """获取 UE 场景的文字描述"""
        actors_result = self.ue.get_actors()
        if "error" in str(actors_result).lower():
            return {"error": str(actors_result)}

        return {"actors": actors_result}

    def compare_scenes(self) -> dict:
        """对比两个引擎的场景状态"""
        blender_desc = self.get_blender_scene_description()
        ue_desc = self.get_ue_scene_description()

        return {
            "blender": blender_desc,
            "unreal": ue_desc
        }

    def iterative_refine_blender(self, target_description: str,
                                  correction_callback=None,
                                  max_iterations: int = 5,
                                  match_threshold: float = 0.9) -> dict:
        """
        Blender 迭代修正循环

        1. 截图
        2. 调用 correction_callback 分析截图并返回修正代码
        3. 执行修正
        4. 重复直到匹配度达标或达到最大迭代次数

        Args:
            target_description: 目标描述
            correction_callback: async fn(screenshot_path, target, scene_info) -> {code, match_score}
            max_iterations: 最大迭代次数
            match_threshold: 匹配度阈值
        """
        history = []

        for i in range(max_iterations):
            logger.info(f"迭代 {i + 1}/{max_iterations}")

            # 截图
            screenshot = self.capture_blender(tag=f"refine_{i}")
            if not screenshot["success"]:
                return {"success": False, "error": "截图失败", "history": history}

            # 获取场景信息
            scene_info = self.get_blender_scene_description()

            # 如果没有回调，返回截图和场景信息供外部分析
            if correction_callback is None:
                history.append({
                    "iteration": i + 1,
                    "screenshot": screenshot["filepath"],
                    "scene_info": scene_info
                })
                return {
                    "success": True,
                    "status": "needs_analysis",
                    "iteration": i + 1,
                    "screenshot": screenshot["filepath"],
                    "scene_info": scene_info,
                    "history": history,
                    "message": "请提供 correction_callback 或使用返回的截图进行外部分析"
                }

            # 调用分析回调
            analysis = correction_callback(screenshot["filepath"], target_description, scene_info)
            match_score = analysis.get("match_score", 0)
            correction_code = analysis.get("code", "")

            history.append({
                "iteration": i + 1,
                "screenshot": screenshot["filepath"],
                "match_score": match_score,
                "corrections": analysis.get("corrections", [])
            })

            logger.info(f"匹配度: {match_score:.1%}")

            # 检查是否达标
            if match_score >= match_threshold:
                return {
                    "success": True,
                    "status": "completed",
                    "iterations": i + 1,
                    "final_score": match_score,
                    "history": history
                }

            # 执行修正
            if correction_code:
                exec_result = self.blender.execute_code(correction_code)
                if exec_result.get("status") == "error":
                    logger.warning(f"修正执行失败: {exec_result.get('message')}")

        return {
            "success": True,
            "status": "max_iterations",
            "iterations": max_iterations,
            "history": history,
            "message": f"达到最大迭代次数 ({max_iterations})，最终匹配度: {history[-1].get('match_score', 0):.1%}"
        }
