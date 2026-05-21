"""FastAPI 接口使用的 Pydantic 数据结构。

本文件只定义请求与响应数据格式，不包含库存计算、权限校验等业务逻辑。
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMResponseModel(BaseModel):
    """响应模型基类，允许从 SQLAlchemy ORM 对象读取字段。"""

    model_config = ConfigDict(from_attributes=True)


class ReagentBase(BaseModel):
    """试剂通用字段。"""

    name_cn: str = Field(..., description="试剂中文名称")
    name_en: str | None = Field(default=None, description="试剂英文名称")
    cas_no: str | None = Field(default=None, description="CAS 编号")
    # Excel 主数据迁移补充字段，便于保留预置试剂的标准名称、别名和排序信息。
    standard_name: str | None = Field(default=None, description="标准名称，例如 丙酮")
    purity_grade: str | None = Field(default=None, description="纯度等级，例如 MOS、AR")
    alias_name: str | None = Field(default=None, description="试剂别名，例如 三氯乙烯、n甲基吡咯烷酮")
    display_order: int = Field(default=0, description="显示排序，数值越小越靠前")
    is_preset: bool = Field(default=False, description="是否系统预置试剂")
    category: str | None = Field(default=None, description="试剂分类")
    specification: str | None = Field(default=None, description="规格，例如 500ml、100g")
    unit: str = Field(default="瓶", description="库存单位，例如 瓶、盒、克、毫升")
    current_quantity: float = Field(default=0.0, description="当前库存数量，删除历史流水后可能短暂为负数")
    warning_threshold: float = Field(default=10.0, ge=0, description="低库存报警阈值")
    location: str | None = Field(default=None, description="存放位置")
    supplier: str | None = Field(default=None, description="供应商")
    hazard_level: str | None = Field(default=None, description="危险等级")
    expiry_date: date | None = Field(default=None, description="有效期")
    msds_url: str | None = Field(default=None, description="MSDS 文件或网页地址")
    remark: str | None = Field(default=None, description="备注")


class ReagentCreate(ReagentBase):
    """创建试剂请求。"""


class ReagentUpdate(BaseModel):
    """更新试剂请求，所有字段均可选。"""

    name_cn: str | None = Field(default=None, description="试剂中文名称")
    name_en: str | None = Field(default=None, description="试剂英文名称")
    cas_no: str | None = Field(default=None, description="CAS 编号")
    standard_name: str | None = Field(default=None, description="标准名称，例如 丙酮")
    purity_grade: str | None = Field(default=None, description="纯度等级，例如 MOS、AR")
    alias_name: str | None = Field(default=None, description="试剂别名，例如 三氯乙烯、n甲基吡咯烷酮")
    display_order: int | None = Field(default=None, description="显示排序，数值越小越靠前")
    is_preset: bool | None = Field(default=None, description="是否系统预置试剂")
    category: str | None = Field(default=None, description="试剂分类")
    specification: str | None = Field(default=None, description="规格，例如 500ml、100g")
    unit: str | None = Field(default=None, description="库存单位，例如 瓶、盒、克、毫升")
    current_quantity: float | None = Field(default=None, description="当前库存数量，删除历史流水后可能短暂为负数")
    warning_threshold: float | None = Field(default=None, ge=0, description="低库存报警阈值")
    location: str | None = Field(default=None, description="存放位置")
    supplier: str | None = Field(default=None, description="供应商")
    hazard_level: str | None = Field(default=None, description="危险等级")
    expiry_date: date | None = Field(default=None, description="有效期")
    msds_url: str | None = Field(default=None, description="MSDS 文件或网页地址")
    remark: str | None = Field(default=None, description="备注")


class ReagentResponse(ReagentBase, ORMResponseModel):
    """试剂响应数据。"""

    id: int = Field(..., description="试剂 ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class ReagentOptionResponse(BaseModel):
    """试剂选择器响应数据，供 Web Select 和小程序 Picker/Search 使用。"""

    id: int = Field(..., description="试剂 ID")
    label: str = Field(..., description="下拉显示文本，优先使用试剂中文名")
    value: int = Field(..., description="下拉选项值，等于试剂 ID")
    name_cn: str = Field(..., description="试剂中文名称")
    standard_name: str | None = Field(default=None, description="标准名称")
    category: str | None = Field(default=None, description="试剂分类")
    current_quantity: float = Field(..., description="当前库存数量")
    unit: str = Field(..., description="库存单位")
    warning_threshold: float = Field(..., description="低库存报警阈值")
    location: str | None = Field(default=None, description="存放位置")
    hazard_level: str | None = Field(default=None, description="危险等级")


class InventoryOperationRequest(BaseModel):
    """库存操作请求，入库、出库、校正接口可复用。"""

    reagent_id: int = Field(..., gt=0, description="试剂 ID")
    quantity: int = Field(..., gt=0, description="操作数量，必须为大于 0 的整数")
    operator_id: int | None = Field(default=None, gt=0, description="操作人用户 ID")
    operator_name: str | None = Field(default=None, min_length=1, max_length=50, description="操作员姓名")
    reason: str | None = Field(default=None, description="操作原因")
    remark: str | None = Field(default=None, description="备注")


class InventoryEditRequest(BaseModel):
    """库存流水编辑请求，允许修改数量、操作员、原因、备注。"""

    quantity: int = Field(..., gt=0, description="操作数量，必须为大于 0 的整数")
    operator_name: str | None = Field(default=None, min_length=1, max_length=50, description="操作员姓名")
    reason: str | None = Field(default=None, description="操作原因")
    remark: str | None = Field(default=None, description="备注")


class InventoryBatchDeleteRequest(BaseModel):
    """库存流水批量删除请求。"""

    record_ids: list[int] = Field(default_factory=list, description="要删除的库存流水记录 ID 列表")


class InventoryBatchDeleteResponse(BaseModel):
    """库存流水批量删除响应。"""

    deleted_count: int = Field(..., description="实际删除的库存流水记录数量")
    affected_reagent_ids: list[int] = Field(..., description="受影响并已重新计算库存的试剂 ID")


class InventoryRecordResponse(ORMResponseModel):
    """库存变动记录响应数据。"""

    id: int = Field(..., description="库存记录 ID")
    year_display_id: int | None = Field(default=None, description="年度显示编号，每年从 1 开始")
    reagent_id: int = Field(..., description="试剂 ID")
    operation_type: str = Field(..., description="操作类型：in / out / adjust")
    quantity_change: float = Field(..., description="库存变化数量")
    before_quantity: float = Field(..., description="操作前库存数量")
    after_quantity: float = Field(..., description="操作后库存数量")
    operator_id: int | None = Field(default=None, description="操作人用户 ID")
    operator_name: str | None = Field(default=None, description="操作员姓名")
    reason: str | None = Field(default=None, description="操作原因")
    remark: str | None = Field(default=None, description="备注")
    event_date: date | None = Field(default=None, description="业务发生日期，Excel 导入时来自表格日期")
    source: str | None = Field(default=None, description="数据来源，例如 excel")
    source_sheet: str | None = Field(default=None, description="来源工作表")
    source_row: int | None = Field(default=None, description="来源行号")
    source_col: int | None = Field(default=None, description="来源列号")
    source_hash: str | None = Field(default=None, description="来源去重哈希")
    created_at: datetime = Field(..., description="创建时间")


class InventoryOperationResponse(InventoryRecordResponse):
    """库存操作响应数据，附带前端展示所需的试剂名称、单位和低库存状态。"""

    reagent_name: str = Field(..., description="试剂中文名称")
    unit: str = Field(..., description="库存单位")
    low_stock: bool = Field(..., description="操作后库存是否小于或等于报警阈值")
    warning_threshold: float = Field(..., description="低库存报警阈值")


class ReagentStockResponse(BaseModel):
    """单个试剂库存余量响应数据。"""

    reagent_id: int = Field(..., description="试剂 ID")
    name_cn: str = Field(..., description="试剂中文名称")
    category: str | None = Field(default=None, description="试剂分类")
    current_quantity: float = Field(..., description="当前库存数量")
    unit: str = Field(..., description="库存单位")
    warning_threshold: float = Field(..., description="低库存报警阈值")
    low_stock: bool = Field(..., description="是否低库存")
    location: str | None = Field(default=None, description="存放位置")
    hazard_level: str | None = Field(default=None, description="危险等级")
    updated_at: datetime = Field(..., description="最近更新时间")


class UserCreate(BaseModel):
    """创建用户请求。"""

    username: str = Field(..., description="用户名")
    full_name: str | None = Field(default=None, description="用户姓名")
    password: str = Field(..., min_length=6, description="登录密码，后端保存前需要哈希")
    role: str = Field(default="member", description="用户角色")
    email: str | None = Field(default=None, description="邮箱")
    phone: str | None = Field(default=None, description="手机号")
    wechat_openid: str | None = Field(default=None, description="微信 OpenID")
    is_active: bool = Field(default=True, description="是否启用")


class UserResponse(ORMResponseModel):
    """用户响应数据，不返回 password_hash。"""

    id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    full_name: str | None = Field(default=None, description="用户姓名")
    role: str = Field(..., description="用户角色")
    email: str | None = Field(default=None, description="邮箱")
    phone: str | None = Field(default=None, description="手机号")
    wechat_openid: str | None = Field(default=None, description="微信 OpenID")
    is_active: bool = Field(..., description="是否启用")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class UserUpdate(BaseModel):
    """更新用户请求，所有字段均可选。"""

    full_name: str | None = Field(default=None, description="用户姓名")
    role: str | None = Field(default=None, description="用户角色")
    email: str | None = Field(default=None, description="邮箱")
    phone: str | None = Field(default=None, description="手机号")
    wechat_openid: str | None = Field(default=None, description="微信 OpenID")
    is_active: bool | None = Field(default=None, description="是否启用")


class UserLogin(BaseModel):
    """用户登录请求。"""

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="登录密码")


class UserLoginResponse(BaseModel):
    """用户登录响应。"""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token 类型")
    user: UserResponse = Field(..., description="当前登录用户信息")


class AlertEventResponse(ORMResponseModel):
    """报警事件响应数据。"""

    id: int = Field(..., description="报警事件 ID")
    year_display_id: int | None = Field(default=None, description="年度显示编号，每年从 1 开始")
    reagent_id: int = Field(..., description="试剂 ID")
    alert_type: str = Field(..., description="报警类型：低库存 / 即将过期 / 异常消耗")
    level: str = Field(..., description="报警级别")
    message: str = Field(..., description="报警消息")
    is_resolved: bool = Field(..., description="是否已处理")
    resolved_at: datetime | None = Field(default=None, description="处理时间")
    created_at: datetime = Field(..., description="创建时间")


class ReportSummaryResponse(ORMResponseModel):
    """报表概览响应数据，后续报表模块可继续扩展。"""

    total_reagents: int = Field(default=0, description="试剂总数")
    low_stock_count: int = Field(default=0, description="低库存试剂数量")
    expiring_count: int = Field(default=0, description="即将过期试剂数量")
    inventory_record_count: int = Field(default=0, description="库存变动记录数量")
