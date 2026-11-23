# -*- coding: utf-8 -*-
"""把礼品库打包成单个 exe（可选）。

使用前先安装 PyInstaller：
    pip install pyinstaller

运行方式：
    python build_exe.py            # 自动递增补丁号：1.1.0 -> 1.1.1 -> 1.1.2 ...
    python build_exe.py 1.2.0      # 指定版本号（小版本功能迭代用）

版本号唯一来源是 gm/__init__.py 里的 __version__，打包时会：
  1) 递增/写入新的版本号
  2) 生成 Windows 版本资源（exe 右键属性 -> 详细信息 能看到文件版本/产品版本）
  3) 后台侧边栏和浏览器标题也会显示这个版本（由 /api/ping 返回）

产物在 dist/gift-mall.exe，双击即可启动（无需管理员权限）。
"""
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INIT_PY = os.path.join(HERE, "gm", "__init__.py")

NAME = "gift-mall"
# 打成英文名，避免部分老系统 / 压缩包对中文 exe 名的兼容问题


def read_version() -> str:
    with open(INIT_PY, "r", encoding="utf-8") as f:
        m = re.search(r'__version__\s*=\s*"([\d.]+)"', f.read())
    return m.group(1) if m else "1.0.0"


def bump_patch(ver: str) -> str:
    parts = [int(x) for x in re.findall(r"\d+", ver)[:3]] or [1, 0, 0]
    while len(parts) < 3:
        parts.append(0)
    parts[2] += 1
    return "%d.%d.%d" % tuple(parts)


def write_version(ver: str):
    with open(INIT_PY, "r", encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'__version__\s*=\s*"[\d.]+"', '__version__ = "%s"' % ver, src)
    with open(INIT_PY, "w", encoding="utf-8") as f:
        f.write(src)


def make_version_file(ver: str, path: str):
    """生成 PyInstaller 的版本资源文件（写入 exe 属性）。"""
    nums = [int(x) for x in re.findall(r"\d+", ver)[:3]]
    while len(nums) < 3:
        nums.append(0)
    quad = "(%d, %d, %d, 0)" % tuple(nums)
    body = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=%s, prodvers=%s, mask=0x3f, flags=0x0,
    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404B0', [
        StringStruct('CompanyName', 'GiftMall Project'),
        StringStruct('FileDescription', '礼品库特卖管理系统'),
        StringStruct('FileVersion', '%s'),
        StringStruct('InternalName', 'gift-mall'),
        StringStruct('LegalCopyright', '内部使用'),
        StringStruct('OriginalFilename', 'gift-mall.exe'),
        StringStruct('ProductName', '礼品库特卖管理系统'),
        StringStruct('ProductVersion', '%s')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
""" % (quad, quad, ver, ver)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def main():
    if not shutil.which("pyinstaller") and not os.path.exists(
            os.path.join(os.path.dirname(sys.executable), "pyinstaller.exe")):
        print("未找到 pyinstaller，请先执行： pip install pyinstaller")
        sys.exit(1)

    old = read_version()
    want = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    if want:
        if not re.match(r"^\d+(\.\d+){0,2}$", want):
            print("版本号格式不对，示例：python build_exe.py 1.2.0")
            sys.exit(1)
        ver = want
    else:
        ver = bump_patch(old)
    write_version(ver)
    print("版本：%s -> %s" % (old, ver))

    vf = os.path.join(HERE, "_version_info.txt")
    make_version_file(ver, vf)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile",
        "--name", NAME,
        "--version-file", vf,
        "--add-data", os.path.join(HERE, "web") + ";web",
        "--hidden-import", "gm",
        os.path.join(HERE, "run.py"),
    ]
    print(" ".join(cmd))
    r = subprocess.call(cmd, cwd=HERE)
    try:
        os.remove(vf)
    except OSError:
        pass
    if r != 0:
        print("打包失败，请把上面的报错发给信息部或 AI 助手")
        sys.exit(r)
    print("\n打包完成 -> %s\\dist\\%s.exe   版本 v%s" % (HERE, NAME, ver))
    print("把 exe 拷到任意目录双击运行即可（无需管理员权限）。")
    print("注意：首次启动会自动生成 data 文件夹（数据库 + 上传图片），请勿删除。")


if __name__ == "__main__":
    main()
