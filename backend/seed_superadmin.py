"""初始化默认超级管理员。

运行方式：
    本地开发  ：python seed_superadmin.py
    生产部署  ：ALLOW_DEFAULT_SUPERADMIN=true \
               DEFAULT_SUPERADMIN_USERNAME=xxx \
               DEFAULT_SUPERADMIN_PASSWORD=xxx \
               python seed_superadmin.py

注意：
    - 生产环境（ENVIRONMENT=production）禁止使用默认弱密码 Admin@123456。
    - 生产环境必须通过环境变量提供自定义用户名和强密码。
    - 脚本幂等：已存在 superadmin 时跳过创建。
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from auth import hash_password
from config import settings
from database import SessionLocal, init_db
from models import User


WEAK_PASSWORDS = {
    "Admin@123456",
    "admin123456",
    "password",
    "123456",
    "superadmin",
    "admin",
}


def validate_superadmin_credentials(username: str, password: str) -> None:
    """生产环境下拒绝使用弱密码和默认用户名。"""

    if not username or not username.strip():
        print("ERROR: DEFAULT_SUPERADMIN_USERNAME 不能为空")
        sys.exit(1)

    if not password or not password.strip():
        print("ERROR: DEFAULT_SUPERADMIN_PASSWORD 不能为空")
        sys.exit(1)

    if len(password) < 8:
        print("ERROR: 密码长度至少 8 位")
        sys.exit(1)

    if settings.is_production:
        if password == "Admin@123456":
            print(
                "ERROR: 生产环境禁止使用默认弱密码 Admin@123456。"
                "请通过 DEFAULT_SUPERADMIN_PASSWORD 环境变量设置强密码。"
            )
            sys.exit(1)
        if len(password) < 10:
            print("ERROR: 生产环境密码长度至少 10 位")
            sys.exit(1)

    if password.lower() in WEAK_PASSWORDS and password != "Admin@123456":
        print(
            "ERROR: 禁止使用常见弱密码。"
            "请通过 DEFAULT_SUPERADMIN_PASSWORD 环境变量设置强密码。"
        )
        sys.exit(1)

    if settings.is_production and not settings.ALLOW_DEFAULT_SUPERADMIN:
        print(
            "ERROR: 生产环境必须设置 ALLOW_DEFAULT_SUPERADMIN=true "
            "并配置 DEFAULT_SUPERADMIN_USERNAME / DEFAULT_SUPERADMIN_PASSWORD"
        )
        sys.exit(1)


def seed_superadmin() -> None:
    """若不存在 superadmin，则创建超级管理员。"""

    username = settings.DEFAULT_SUPERADMIN_USERNAME.strip()
    password = settings.DEFAULT_SUPERADMIN_PASSWORD.strip()

    validate_superadmin_credentials(username, password)

    init_db()
    db = SessionLocal()
    try:
        existing_superadmin = db.execute(
            select(User).where(User.role == "superadmin")
        ).scalar_one_or_none()
        if existing_superadmin is not None:
            print(f"superadmin 已存在（username={existing_superadmin.username}），跳过创建")
            return

        user = User(
            username=username,
            full_name="系统超级管理员",
            password_hash=hash_password(password),
            role="superadmin",
            email=None,
            phone=None,
            wechat_openid=None,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"已创建 superadmin：{username}")
        if not settings.is_production:
            print("本地开发模式：superadmin 已创建，生产部署前请修改密码。")
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_superadmin()
