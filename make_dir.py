# -*- coding: utf-8 -*-
"""
create_empty_project_structure.py

用途：
    在当前工作目录 lab-reagent-system/ 下创建项目空目录和空文件。

运行方式：
    python create_empty_project_structure.py

说明：
    1. 只创建目录和空文件
    2. 不写入任何业务代码
    3. 已存在的文件不会被覆盖
"""

from pathlib import Path


def create_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    print(f"[DIR]  {path}")


def create_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        print(f"[SKIP] {path} 已存在")
        return

    path.touch()
    print(f"[FILE] {path}")


def main() -> None:
    root = Path.cwd()

    print("=" * 80)
    print("实验室试剂仓库管理系统：空项目结构创建")
    print(f"当前工作目录：{root}")
    print("=" * 80)

    directories = [
        root / "backend",
        root / "miniprogram",
        root / "miniprogram" / "pages",
        root / "miniprogram" / "components",
        root / "miniprogram" / "utils",
        root / "admin-web",
        root / "admin-web" / "src",
        root / "docs",
    ]

    files = [
        # backend
        root / "backend" / "main.py",
        root / "backend" / "config.py",
        root / "backend" / "database.py",
        root / "backend" / "models.py",
        root / "backend" / "schemas.py",
        root / "backend" / "auth.py",
        root / "backend" / "users.py",
        root / "backend" / "reagents.py",
        root / "backend" / "inventory.py",
        root / "backend" / "alerts.py",
        root / "backend" / "reports.py",
        root / "backend" / "tencent_docs.py",
        root / "backend" / "notifications.py",
        root / "backend" / "scheduler.py",
        root / "backend" / "audit_logs.py",
        root / "backend" / "seed_data.py",
        root / "backend" / "requirements.txt",

        # miniprogram
        root / "miniprogram" / "app.json",

        # admin-web
        root / "admin-web" / "package.json",
        root / "admin-web" / "vite.config.ts",

        # docs
        root / "docs" / "api.md",
        root / "docs" / "database.md",
        root / "docs" / "tencent-docs-sync.md",

        # root
        root / "check_lab_reagent_env.py",
    ]

    for directory in directories:
        create_dir(directory)

    for file in files:
        create_file(file)

    print("=" * 80)
    print("项目空目录和空文件创建完成")
    print("=" * 80)


if __name__ == "__main__":
    main()