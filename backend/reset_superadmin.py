"""重置本地超级管理员账号密码。

运行方式：
    python reset_superadmin.py

说明：
    该脚本只创建或更新 username=superadmin 的用户，不删除、不重建、不清空数据库，
    也不会影响试剂、库存流水、报警事件等业务数据。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from auth import hash_password
from database import SessionLocal, init_db
from models import User


DEFAULT_USERNAME = "superadmin"
DEFAULT_PASSWORD = "Admin@123456"


def reset_superadmin() -> None:
    """创建或重置默认超级管理员，确保本地后台可以登录。"""

    init_db()
    db = SessionLocal()
    try:
        user = db.execute(
            select(User).where(User.username == DEFAULT_USERNAME)
        ).scalar_one_or_none()

        if user is None:
            user = User(
                username=DEFAULT_USERNAME,
                full_name="默认超级管理员",
                role="superadmin",
                email=None,
                phone=None,
                wechat_openid=None,
                is_active=True,
            )
            db.add(user)
            action = "已创建默认超级管理员"
        else:
            action = "已重置默认超级管理员"

        # 只重置登录相关字段，避免影响其他用户和业务数据。
        user.password_hash = hash_password(DEFAULT_PASSWORD)
        user.role = "superadmin"
        user.is_active = True

        db.commit()
        print(action)
        print(f"用户名：{DEFAULT_USERNAME}")
        print(f"密码：{DEFAULT_PASSWORD}")
        print("身份：superadmin")
        print("正式部署前请立即修改默认密码，并在 .env 中配置强 SECRET_KEY。")
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    reset_superadmin()
