"""项目配置模块。

本模块集中管理后端运行所需配置。默认值用于本地开发，敏感信息应通过
backend/.env 或系统环境变量覆盖，禁止在代码中写入真实密钥。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """实验室化学试剂仓库管理系统配置。"""

    # 允许从 backend/.env 读取配置；未定义的额外变量会被忽略，便于本地扩展。
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # 项目基础信息
    PROJECT_NAME: str = "实验室化学试剂仓库管理系统"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    # 数据库配置：从 backend 目录启动时，数据库文件位于 backend/lab_reagent.db
    DATABASE_URL: str = "sqlite:///./lab_reagent.db"

    # 安全配置：生产环境必须通过 .env 覆盖默认 SECRET_KEY
    SECRET_KEY: str = "change-this-secret-key-in-env"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    DEBUG: bool = False

    # 生产环境下 SECRET_KEY 若仍为默认值则拒绝启动。
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    # 默认超级管理员：仅本地开发使用，生产必须通过环境变量覆盖。
    DEFAULT_SUPERADMIN_USERNAME: str = "superadmin"
    DEFAULT_SUPERADMIN_PASSWORD: str = "Admin@123456"
    ALLOW_DEFAULT_SUPERADMIN: bool = False

    # CORS 允许的前端域名，逗号分隔；开发环境可使用 *。
    CORS_ORIGINS: str = "*"
    FRONTEND_URL: str = "http://127.0.0.1:5173"

    # 库存与有效期提醒默认规则
    DEFAULT_LOW_STOCK_THRESHOLD: int = 10
    EXPIRY_WARNING_DAYS: int = 30

    # 腾讯文档同步配置：第一阶段可为空，后续同步模块再读取使用
    TENCENT_DOC_CLIENT_ID: str = ""
    TENCENT_DOC_CLIENT_SECRET: str = ""
    TENCENT_DOC_REDIRECT_URI: str = ""
    TENCENT_DOC_SCOPE: str = "all"
    TENCENT_DOC_OAUTH_AUTHORIZE_URL: str = "https://docs.qq.com/oauth/v2/authorize"
    TENCENT_DOC_OAUTH_TOKEN_URL: str = "https://docs.qq.com/oauth/v2/token"
    TENCENT_DOC_API_BASE_URL: str = "https://docs.qq.com/openapi"
    TENCENT_DOC_DOC_ID: str = ""
    TENCENT_DOC_SHEET_ID: str = ""
    TENCENT_DOC_SHEET_RANGE: str = "A1:M1000"
    TENCENT_DOC_READ_PATH: str = ""
    TENCENT_DOC_UPDATE_PATH: str = ""
    TENCENT_DOC_TOKEN_FILE: str = "tencent_doc_token.json"

    # 腾讯文档真实同步配置：优先使用 TENCENT_DOCS_*，旧 TENCENT_DOC_* 字段保留兼容。
    TENCENT_DOCS_MODE: str = "local"
    TENCENT_DOCS_CLIENT_ID: str = ""
    TENCENT_DOCS_CLIENT_SECRET: str = ""
    TENCENT_DOCS_REDIRECT_URI: str = ""
    TENCENT_DOCS_FILE_ID: str = ""
    TENCENT_DOCS_DEFAULT_YEAR: int = 2026

    # 本地同步配置：生产环境可通过 .env 设置为 false 隐藏/禁用 Mock 同步入口
    SYNC_MOCK_ENABLED: bool = True

    # 企业微信机器人通知 Webhook：未配置时通知模块应跳过发送
    WECHAT_WORK_WEBHOOK: str = ""


# 全局配置实例，后续模块统一通过 `from config import settings` 使用。
settings = Settings()
