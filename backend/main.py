"""FastAPI 后端总入口。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib import import_module
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from scheduler import start_scheduler, stop_scheduler
from utils.timezone import now_beijing


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期：启动时初始化数据库并启动定时任务，关闭时停止定时任务。"""

    logger.info("正在初始化数据库表...")
    init_db()
    logger.info("数据库初始化完成")

    try:
        start_scheduler()
    except Exception:
        # 定时任务启动失败不应影响基础 API 服务运行。
        logger.exception("定时任务启动失败，API 服务将继续运行")

    try:
        yield
    finally:
        try:
            stop_scheduler()
        except Exception:
            # 关闭调度器失败只记录日志，避免影响应用关闭流程。
            logger.exception("定时任务停止失败")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="实验室化学试剂仓库管理系统后端 API",
    lifespan=lifespan,
)


# CORS 来源通过 CORS_ORIGINS 配置，开发环境默认 "＊"，生产环境填写具体域名。
origins = (
    ["*"]
    if settings.CORS_ORIGINS.strip() == "*"
    else [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def include_optional_router(module_name: str) -> None:
    """尝试挂载业务模块 router。

    第一阶段部分模块还没有实现 router，缺失时跳过，避免影响后端基础服务启动。
    """

    try:
        module = import_module(module_name)
    except Exception as exc:
        logger.warning("跳过模块 %s：导入失败，原因：%s", module_name, exc)
        return

    router = getattr(module, "router", None)
    if router is None:
        logger.info("跳过模块 %s：暂未定义 router", module_name)
        return

    app.include_router(router)
    logger.info("已挂载模块 %s.router", module_name)


for router_module in (
    "users",
    "reagents",
    "inventory",
    "alerts",
    "reports",
    "sync_api",
    "tencent_docs_api",
    "tencent_docs",
    "audit_logs",
):
    include_optional_router(router_module)


@app.get("/", summary="根接口")
def read_root() -> dict[str, str]:
    """返回后端服务基础信息。"""

    return {
        "message": "实验室化学试剂仓库管理系统后端服务正在运行",
        "project_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


@app.get("/health", summary="健康检查")
def health_check() -> dict[str, object]:
    """Render 健康检查接口：返回服务状态、数据库连接、环境信息。

    不返回 DATABASE_URL、SECRET_KEY 等敏感信息。
    """

    db_status = "unknown"
    try:
        from sqlalchemy import text

        from database import SessionLocal

        session = SessionLocal()
        try:
            session.execute(text("SELECT 1"))
            db_status = "connected"
        finally:
            session.close()
    except Exception:
        db_status = "disconnected"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "database": db_status,
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION,
        "project_name": settings.PROJECT_NAME,
        "timestamp": now_beijing().isoformat(),
    }
