"""安装 BlenderUE Bridge Addon 到 Blender

用法:
    python scripts/install_addon.py             # 自动检测 Blender 版本目录
    python scripts/install_addon.py --path <addons_dir>   # 手动指定
    python scripts/install_addon.py --blender-version 4.2  # 指定版本

原理: 复制 blender_addon/ 包到 Blender 的 addons 目录,
      然后在 Blender 中启用 (Preferences > Add-ons > 搜索 "BlenderUE Bridge")
"""

import argparse
import glob
import os
import shutil
import sys
import zipfile

BRIDGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_SRC = os.path.join(BRIDGE_ROOT, "blender_addon")
ADDON_NAME = "blender_addon"


def find_addons_dirs():
    """查找所有可能的 Blender addons 目录"""
    home = os.path.expanduser("~")
    candidates = []
    # Windows: %APPDATA%/Blender Foundation/Blender/<version>/scripts/addons
    appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
    bf = os.path.join(appdata, "Blender Foundation", "Blender")
    if os.path.isdir(bf):
        for ver in sorted(os.listdir(bf), reverse=True):
            p = os.path.join(bf, ver, "scripts", "addons")
            if os.path.isdir(p):
                candidates.append((ver, p))
    # Linux: ~/.config/blender/<version>/scripts/addons
    for ver_dir in glob.glob(os.path.join(home, ".config", "blender", "*")):
        p = os.path.join(ver_dir, "scripts", "addons")
        if os.path.isdir(p):
            candidates.append((os.path.basename(ver_dir), p))
    # macOS: ~/Library/Application Support/Blender/<version>/scripts/addons
    for ver_dir in glob.glob(os.path.join(home, "Library", "Application Support",
                                          "Blender", "*")):
        p = os.path.join(ver_dir, "scripts", "addons")
        if os.path.isdir(p):
            candidates.append((os.path.basename(ver_dir), p))
    return candidates


def install(target_dir: str):
    dest = os.path.join(target_dir, ADDON_NAME)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(ADDON_SRC, dest)
    print(f"✅ 已安装到: {dest}")
    print("   然后在 Blender 中: 编辑 > 偏好设置 > 插件 > 搜索 'BlenderUE Bridge' > 勾选启用")
    print("   或使用 blender --python 自动启用")


def make_zip(zip_path: str):
    """打包为 zip (Blender 手动安装用)"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(ADDON_SRC):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.join(ADDON_NAME, os.path.relpath(full, ADDON_SRC))
                zf.write(full, rel)
    print(f"✅ 已打包: {zip_path}")


def enable_in_blender(addons_dir: str):
    """通过 blender --python 自动启用插件 (需要 blender 在 PATH)"""
    import subprocess
    import tempfile
    script = f"""
import bpy
import addon_utils
addon_utils.enable("blender_addon", default_set=True)
bpy.ops.wm.save_userpref()
print("ADDON ENABLED")
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(script)
        tmp = f.name
    try:
        r = subprocess.run(["blender", "--background", "--python", tmp],
                           capture_output=True, text=True, timeout=60)
        if "ADDON ENABLED" in r.stdout:
            print("✅ 插件已在 Blender 中启用")
            return True
        print(f"⚠️ 自动启用失败 (请手动启用):\n{r.stderr[-500:]}")
        return False
    except FileNotFoundError:
        print("⚠️ 未找到 blender 命令, 请手动启用插件")
        return False
    finally:
        os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser(description="Install BlenderUE Bridge addon")
    ap.add_argument("--path", help="手动指定 addons 目录")
    ap.add_argument("--blender-version", help="指定 Blender 版本 (如 4.2)")
    ap.add_argument("--zip", metavar="OUT", help="打包为 zip 并退出")
    ap.add_argument("--enable", action="store_true", help="安装后尝试自动启用")
    args = ap.parse_args()

    if args.zip:
        make_zip(args.zip)
        return

    if args.path:
        install(args.path)
        if args.enable:
            enable_in_blender(args.path)
        return

    dirs = find_addons_dirs()
    if not dirs:
        print("❌ 未找到 Blender addons 目录")
        print("   请手动指定: python scripts/install_addon.py --path <addons目录>")
        sys.exit(1)

    # 版本过滤
    if args.blender_version:
        target = None
        for ver, p in dirs:
            if ver.startswith(args.blender_version):
                target = (ver, p)
                break
        if target is None:
            print(f"❌ 未找到 Blender {args.blender_version} 目录, 可用:")
            for ver, p in dirs:
                print(f"   {ver} → {p}")
            sys.exit(1)
    else:
        target = dirs[0]

    print(f"检测到 Blender {target[0]}: {target[1]}")
    install(target[1])
    if args.enable:
        enable_in_blender(target[1])


if __name__ == "__main__":
    main()
