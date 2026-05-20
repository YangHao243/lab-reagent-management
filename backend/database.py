"""数据库连接与会话管理模块。"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import settings


# SQLite 在 FastAPI 多线程请求场景下需要关闭同线程检查。
connect_args: dict[str, bool] = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}


# 创建数据库引擎。当前阶段使用同步 SQLAlchemy，保持本地 SQLite 简单稳定。
engine: Engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
)


if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        """设置 SQLite 本地开发参数，避免 Windows 下删除 journal 文件导致提交失败。"""

        _ = connection_record
        cursor = dbapi_connection.cursor()
        try:
            # PERSIST 会保留 journal 文件并清空头部，不依赖删除权限，更适合本地 Windows 调试。
            cursor.execute("PRAGMA journal_mode=PERSIST")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


# 每次请求创建一个数据库会话，请求结束后关闭。
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


# ORM 模型基类，后续 models.py 中的表模型都应继承 Base。
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖函数：提供数据库会话并确保使用后关闭。"""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建所有已注册的数据库表。

    注意：需要先导入 models 模块，让继承 Base 的模型注册到 Base.metadata。
    当前 models.py 还未实现时，执行本函数不会创建业务表。
    """

    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    try:
        from services.excel_inventory_sync import ensure_excel_sync_schema
        from services.tencent_docs_schema import ensure_tencent_docs_schema

        ensure_excel_sync_schema()
        ensure_tencent_docs_schema()
    except Exception:
        # 迁移失败时向上抛出，让启动日志暴露具体原因，避免旧表结构下静默运行。
        raise
