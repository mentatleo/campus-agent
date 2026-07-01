"""
队友资料打包脚本
从项目目录筛选需要交付给队友的文件，排除临时文件/中间产物/本地配置，
压缩为带时间戳的 tar.gz 和 zip 双格式压缩包。
"""

import os
import tarfile
import zipfile
import datetime
import sys
import io

# 强制 UTF-8 输出，避免 Windows GBK 编码问题
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ========== 配置 ==========
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "teammate-packs")

# 直接在 include 列表里的文件路径（用于精确排除时豁免）
_INCLUDE_FILE_PATHS = set()

# 需要打包的文件和目录
INCLUDE_PATHS = [
    # 数据文件
    "data/courses.csv",
    "data/classrooms.csv",
    "data/consumption.csv",
    "data/library.csv",
    "data/notices.json",
    "data/competitions.json",
    # 知识库目录（空目录也要带过去）
    "data/knowledge/",
    # 队友任务包目录（含模板和说明）
    "teammate-packs/01-知识库填充/",
    "teammate-packs/02-素材与截图/",
    "teammate-packs/03-数据校准/",
    # 文档
    "分工方案.md",
    "方案框架.md",
    "report/项目报告书.md",
    # 前端（队友A做文案修正需要）
    "frontend/index.html",
    # 基础信息
    "README.md",
]

# 排除规则（文件/目录名匹配）
EXCLUDE_NAMES = [
    ".env",
    ".git",
    ".gitignore",
    ".impeccable.md",
    "CONTEXT.md",
    "self_check.py",
    "courses_real_backup.csv",  # 原始数据备份
    "pack_for_teammates.py",     # 本脚本自身
]

# 排除目录（递归排除）
EXCLUDE_DIRS = [
    "__pycache__",
    ".git",
    "chroma_db",
    "backend",
    "frontend",  # 只打包 index.html，不打包整个目录
]

# 排除扩展名
EXCLUDE_EXTENSIONS = [
    ".pyc",
    ".pyo",
    ".pyd",
    ".pickle",
    ".pkl",
    ".log",
    ".zip",    # 不包含旧的压缩包
    ".tar.gz",
]


def should_exclude(rel_path: str) -> bool:
    """判断文件是否应排除"""
    # 显式包含的文件不排除（即使它在排除目录下）
    norm = rel_path.replace("\\", "/")
    if norm in _INCLUDE_FILE_PATHS:
        return False

    name = os.path.basename(rel_path)
    parts = norm.split("/")

    # 按名称排除
    if name in EXCLUDE_NAMES:
        return True

    # 按目录排除
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True

    # 按扩展名排除
    _, ext = os.path.splitext(name)
    if ext in EXCLUDE_EXTENSIONS:
        return True

    # 排除 .tar.gz（多重后缀）
    if name.endswith(".tar.gz"):
        return True

    return False


def collect_files() -> list:
    """收集所有需要打包的文件"""
    # 预先记录显式包含的文件路径
    for path in INCLUDE_PATHS:
        if not path.endswith("/"):
            _INCLUDE_FILE_PATHS.add(path.replace("\\", "/"))

    files = []

    for path in INCLUDE_PATHS:
        full_path = os.path.join(PROJECT_ROOT, path)

        if path.endswith("/"):
            # 目录：递归收集
            if not os.path.isdir(full_path):
                print(f"  [跳过] 目录不存在: {path}")
                continue
            for root, dirs, filenames in os.walk(full_path):
                # 原地过滤排除目录
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for fname in filenames:
                    abs_path = os.path.join(root, fname)
                    rel = os.path.relpath(abs_path, PROJECT_ROOT)
                    if not should_exclude(rel):
                        files.append(abs_path)
        else:
            # 单个文件
            if not os.path.isfile(full_path):
                print(f"  [跳过] 文件不存在: {path}")
                continue
            rel = os.path.relpath(full_path, PROJECT_ROOT)
            if not should_exclude(rel):
                files.append(full_path)
            else:
                print(f"  [排除] {path}")

    return sorted(set(files))


def print_banner(text: str):
    print(f"\n{'='*50}")
    print(f"  {text}")
    print(f"{'='*50}")


def print_file_tree(files, project_root):
    """打印文件树"""
    by_dir = {}
    for f in files:
        rel = os.path.relpath(f, project_root).replace("\\", "/")
        d = os.path.dirname(rel) or "."
        by_dir.setdefault(d, []).append(os.path.basename(rel))

    print()
    for d in sorted(by_dir):
        if d == ".":
            print(d)
        else:
            print(f"{d}/")
        for fname in sorted(by_dir[d]):
            print(f"  {fname}")


def create_tar_gz(files, project_root, output_path):
    """创建 tar.gz 压缩包"""
    print_banner("创建 tar.gz")

    with tarfile.open(output_path, "w:gz") as tar:
        for f in files:
            rel = os.path.relpath(f, project_root)
            tar.add(f, arcname=rel)
            print(f"  + {rel}")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\n  生成: {output_path}")
    print(f"  大小: {size_mb:.2f} MB")
    print(f"  文件数: {len(files)}")


def create_zip(files, project_root, output_path):
    """创建 zip 压缩包"""
    print_banner("创建 zip")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            rel = os.path.relpath(f, project_root)
            zf.write(f, arcname=rel)
            print(f"  + {rel}")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\n  生成: {output_path}")
    print(f"  大小: {size_mb:.2f} MB")
    print(f"  文件数: {len(files)}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tar_path = os.path.join(OUTPUT_DIR, f"队友资料_{timestamp}.tar.gz")
    zip_path = os.path.join(OUTPUT_DIR, f"队友资料_{timestamp}.zip")

    print_banner("校园数据导航智能体 — 队友资料打包")
    print(f"  时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  项目: {PROJECT_ROOT}")

    # 收集文件
    print_banner("收集文件")
    files = collect_files()
    print(f"  共收集 {len(files)} 个文件")

    # 显示文件树
    print_file_tree(files, PROJECT_ROOT)

    # 创建压缩包
    create_tar_gz(files, PROJECT_ROOT, tar_path)
    create_zip(files, PROJECT_ROOT, zip_path)

    # 总结
    print_banner("打包完成")
    tar_size = os.path.getsize(tar_path) / (1024 * 1024)
    zip_size = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"  tar.gz: {tar_path}")
    print(f"          {tar_size:.2f} MB / {len(files)} 个文件")
    print(f"  zip:    {zip_path}")
    print(f"          {zip_size:.2f} MB / {len(files)} 个文件")
    print(f"\n  可直接发给队友的压缩包已就绪。")


if __name__ == "__main__":
    main()
