"""
ontology/schema.py
──────────────────
元气森林渠道管理 —— Ontology Schema 定义
对应 Palantir OMS（Object Metadata Service）

设计原则：
  1. Object Type = 业务实体，有唯一 primary key
  2. Link Type   = 实体关系，可携带属性（如库存数量）
  3. Action Type = 变更意图，执行后写入 ActionLog
  4. 所有写操作经 ActionLog 审计，高风险操作需人工审批
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import uuid


# ═══════════════════════════════════════════════════════════════
#  Schema Registry  （对应 Palantir OMS 的类型注册表）
# ═══════════════════════════════════════════════════════════════

OBJECT_TYPE_REGISTRY: dict[str, type] = {}
LINK_TYPE_REGISTRY:   dict[str, type] = {}
ACTION_TYPE_REGISTRY: dict[str, "ActionTypeDef"] = {}


def ontology_object(cls):
    """装饰器：将 dataclass 注册为 Object Type"""
    OBJECT_TYPE_REGISTRY[cls.__name__] = cls
    return cls


def ontology_link(cls):
    """装饰器：将 dataclass 注册为 Link Type"""
    LINK_TYPE_REGISTRY[cls.__name__] = cls
    return cls


@dataclass
class ActionTypeDef:
    name: str
    description: str
    requires_approval: bool       # True → 写入 pending，等待人工确认
    approval_threshold: dict      # 触发人工审批的条件，e.g. {"amount": 100000}
    writable_object_types: list[str]


# ═══════════════════════════════════════════════════════════════
#  Object Types  （业务实体）
# ═══════════════════════════════════════════════════════════════

@ontology_object
@dataclass
class Brand:
    """品牌 —— 元气森林旗下品牌线"""
    id: str                  = field(default_factory=lambda: str(uuid.uuid4()))
    name: str                = ""        # 元气森林 / 外星人 / 北海牧场
    description: str         = ""
    launch_year: int         = 0
    is_active: bool          = True
    embedding: list[float]   = field(default_factory=list)
    created_at: datetime     = field(default_factory=datetime.now)

    # Ontology 元数据
    _object_type: str        = field(default="Brand", init=False, repr=False)
    _primary_key: str        = field(default="id",    init=False, repr=False)


@ontology_object
@dataclass
class Product:
    """产品线 —— 气泡水 / 能量饮料 / 乳茶"""
    id: str                  = field(default_factory=lambda: str(uuid.uuid4()))
    brand_id: str            = ""
    name: str                = ""        # 气泡水·白桃味
    category: str            = ""        # 碳酸饮料 / 能量饮料 / 乳品
    description: str         = ""
    is_active: bool          = True
    embedding: list[float]   = field(default_factory=list)
    created_at: datetime     = field(default_factory=datetime.now)

    _object_type: str        = field(default="Product", init=False, repr=False)
    _primary_key: str        = field(default="id",      init=False, repr=False)


@ontology_object
@dataclass
class SKU:
    """最小库存单位 —— 具体规格/包装"""
    id: str                  = field(default_factory=lambda: str(uuid.uuid4()))
    product_id: str          = ""
    sku_code: str            = ""        # GENKI-BT-500ML
    name: str                = ""        # 气泡水白桃味 500ml
    spec: str                = ""        # 500ml / 1L / 6罐装
    unit_price: float        = 0.0       # 出厂价（元）
    retail_price: float      = 0.0       # 建议零售价
    weight_g: int            = 0
    reorder_threshold: int   = 100       # 库存预警线
    is_active: bool          = True
    embedding: list[float]   = field(default_factory=list)
    created_at: datetime     = field(default_factory=datetime.now)

    _object_type: str        = field(default="SKU", init=False, repr=False)
    _primary_key: str        = field(default="id",  init=False, repr=False)


@ontology_object
@dataclass
class Channel:
    """渠道类型 —— 现代渠道 / 传统渠道 / 电商 / 餐饮"""
    id: str                  = field(default_factory=lambda: str(uuid.uuid4()))
    name: str                = ""        # 现代渠道（KA）/ 便利店 / 电商
    channel_type: str        = ""        # KA / CVS / Ecom / HoReCa / TT
    description: str         = ""
    embedding: list[float]   = field(default_factory=list)

    _object_type: str        = field(default="Channel", init=False, repr=False)
    _primary_key: str        = field(default="id",      init=False, repr=False)


@ontology_object
@dataclass
class Distributor:
    """经销商 —— 省级 / 市级代理"""
    id: str                  = field(default_factory=lambda: str(uuid.uuid4()))
    name: str                = ""
    level: str               = ""        # provincial / city / district
    region: str              = ""        # 华东 / 华南 / 华北
    province: str            = ""
    city: str                = ""
    contact_name: str        = ""
    contact_phone: str       = ""
    credit_limit: float      = 0.0       # 授信额度（元）
    outstanding_amount: float = 0.0      # 当前应收账款
    status: str              = "active"  # active / suspended / terminated
    embedding: list[float]   = field(default_factory=list)
    created_at: datetime     = field(default_factory=datetime.now)

    _object_type: str        = field(default="Distributor", init=False, repr=False)
    _primary_key: str        = field(default="id",          init=False, repr=False)


@ontology_object
@dataclass
class Store:
    """门店 —— 终端零售网点"""
    id: str                  = field(default_factory=lambda: str(uuid.uuid4()))
    distributor_id: str      = ""
    channel_id: str          = ""
    name: str                = ""
    store_code: str          = ""
    province: str            = ""
    city: str                = ""
    district: str            = ""
    address: str             = ""
    store_type: str          = ""        # 大润发 / 7-11 / 全家 / 盒马
    tier: str                = "A"       # A/B/C 门店分级
    monthly_sales_target: float = 0.0
    is_active: bool          = True
    embedding: list[float]   = field(default_factory=list)
    created_at: datetime     = field(default_factory=datetime.now)

    _object_type: str        = field(default="Store", init=False, repr=False)
    _primary_key: str        = field(default="id",    init=False, repr=False)


@ontology_object
@dataclass
class InventoryRecord:
    """
    库存快照 —— SKU × 经销商 的库存数量
    同时充当 SKU → Distributor 的 Link Object
    """
    id: str                  = field(default_factory=lambda: str(uuid.uuid4()))
    sku_id: str              = ""
    distributor_id: str      = ""
    quantity: int            = 0
    available_quantity: int  = 0         # 可售数量（扣除锁定）
    locked_quantity: int     = 0         # 订单锁定数量
    last_updated: datetime   = field(default_factory=datetime.now)

    _object_type: str        = field(default="InventoryRecord", init=False, repr=False)
    _primary_key: str        = field(default="id",              init=False, repr=False)


@ontology_object
@dataclass
class SalesOrder:
    """销售订单 —— 门店向经销商下单"""
    id: str                  = field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str            = ""
    distributor_id: str      = ""
    sku_id: str              = ""
    quantity: int            = 0
    unit_price: float        = 0.0
    total_amount: float      = 0.0
    status: str              = "pending"  # pending/confirmed/shipped/completed/cancelled
    promotion_id: str        = ""
    discount_amount: float   = 0.0
    notes: str               = ""
    created_at: datetime     = field(default_factory=datetime.now)
    confirmed_at: datetime   = None
    shipped_at: datetime     = None

    _object_type: str        = field(default="SalesOrder", init=False, repr=False)
    _primary_key: str        = field(default="id",         init=False, repr=False)


@ontology_object
@dataclass
class Promotion:
    """促销活动"""
    id: str                  = field(default_factory=lambda: str(uuid.uuid4()))
    name: str                = ""
    promo_type: str          = ""        # discount / bundled / gift / rebate
    start_date: datetime     = field(default_factory=datetime.now)
    end_date: datetime       = field(default_factory=datetime.now)
    discount_rate: float     = 0.0       # 折扣率，e.g. 0.85 = 八五折
    min_quantity: int        = 0         # 最低起购量
    applicable_channels: list[str] = field(default_factory=list)
    budget: float            = 0.0
    spent: float             = 0.0
    status: str              = "draft"   # draft/active/paused/ended
    embedding: list[float]   = field(default_factory=list)
    created_at: datetime     = field(default_factory=datetime.now)

    _object_type: str        = field(default="Promotion", init=False, repr=False)
    _primary_key: str        = field(default="id",        init=False, repr=False)


@ontology_object
@dataclass
class ListingTask:
    """
    铺货任务 —— 追踪某 SKU 在某门店的上架状态
    渠道管理的核心 KPI 载体
    """
    id: str                  = field(default_factory=lambda: str(uuid.uuid4()))
    sku_id: str              = ""
    store_id: str            = ""
    distributor_id: str      = ""
    target_date: datetime    = field(default_factory=datetime.now)
    status: str              = "pending"  # pending/in_progress/listed/failed
    listed_at: datetime      = None
    shelf_position: str      = ""         # 货架位置
    facings: int             = 0          # 面数（陈列数量）
    notes: str               = ""
    created_at: datetime     = field(default_factory=datetime.now)

    _object_type: str        = field(default="ListingTask", init=False, repr=False)
    _primary_key: str        = field(default="id",          init=False, repr=False)


# ═══════════════════════════════════════════════════════════════
#  Action Types  （业务变更意图注册表）
# ═══════════════════════════════════════════════════════════════

ACTION_TYPE_REGISTRY.update({

    "create_sales_order": ActionTypeDef(
        name="create_sales_order",
        description="门店向经销商创建销售订单",
        requires_approval=True,
        approval_threshold={"total_amount": 50000},  # 5万以上需审批
        writable_object_types=["SalesOrder", "InventoryRecord"]
    ),

    "confirm_sales_order": ActionTypeDef(
        name="confirm_sales_order",
        description="经销商确认订单并锁定库存",
        requires_approval=False,
        approval_threshold={},
        writable_object_types=["SalesOrder", "InventoryRecord"]
    ),

    "update_listing_status": ActionTypeDef(
        name="update_listing_status",
        description="更新铺货任务状态（完成/失败）",
        requires_approval=False,
        approval_threshold={},
        writable_object_types=["ListingTask"]
    ),

    "create_promotion": ActionTypeDef(
        name="create_promotion",
        description="创建促销活动",
        requires_approval=True,
        approval_threshold={"budget": 100000},       # 预算 10 万以上需审批
        writable_object_types=["Promotion"]
    ),

    "adjust_inventory": ActionTypeDef(
        name="adjust_inventory",
        description="手工调整库存数量（盘点/损耗）",
        requires_approval=True,
        approval_threshold={"delta": -500},          # 负向调整超 500 件需审批
        writable_object_types=["InventoryRecord"]
    ),

    "suspend_distributor": ActionTypeDef(
        name="suspend_distributor",
        description="暂停经销商合作（欠款/违规）",
        requires_approval=True,
        approval_threshold={},                        # 始终需要审批
        writable_object_types=["Distributor"]
    ),
})


# ═══════════════════════════════════════════════════════════════
#  Action Log  （审计追踪，对应 Palantir Action Log）
# ═══════════════════════════════════════════════════════════════

class ApprovalStatus(Enum):
    NOT_REQUIRED = "not_required"
    PENDING      = "pending"
    APPROVED     = "approved"
    REJECTED     = "rejected"


@dataclass
class ActionLog:
    id: str                        = field(default_factory=lambda: str(uuid.uuid4()))
    action_type: str               = ""
    object_type: str               = ""
    object_id: str                 = ""
    performed_by: str              = ""          # agent_id 或 user_id
    payload: dict                  = field(default_factory=dict)
    result: dict                   = field(default_factory=dict)
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    approved_by: str               = ""
    approved_at: datetime          = None
    rejection_reason: str          = ""
    timestamp: datetime            = field(default_factory=datetime.now)
