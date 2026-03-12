"""
mcp/action_mcp.py
──────────────────
Action MCP Server —— 写工具集（含审计 + 人工审批触发）
对应 Palantir Ontology MCP（运行态·写入端）

设计原则：
  1. 每个写工具对应一个 Action Type
  2. 写入前校验业务规则（库存、授信额度等）
  3. 高风险操作写入 approval_status=pending，等待人工确认
  4. 所有操作强制写入 ActionLog（不可绕过）
  5. 返回结构统一：{success, object_id, action_id, status, message}
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime
from typing import Optional

from mcp.server.fastmcp import FastMCP
from ontology.schema import ACTION_TYPE_REGISTRY, ApprovalStatus

_storage  = None
_notifier = None   # 审批通知器，启动时注入

mcp = FastMCP("GenkiActionMCP")


def set_dependencies(storage, notifier=None):
    global _storage, _notifier
    _storage  = storage
    _notifier = notifier


def _should_require_approval(action_name: str, payload: dict) -> bool:
    """根据 Action Type 定义和 payload 判断是否需要人工审批"""
    action_def = ACTION_TYPE_REGISTRY.get(action_name)
    if not action_def:
        return False
    if not action_def.requires_approval:
        return False
    # 检查阈值条件
    threshold = action_def.approval_threshold
    for field, limit in threshold.items():
        value = payload.get(field, 0)
        if isinstance(limit, (int, float)):
            if limit < 0 and value < limit:   # 负向阈值（如库存调减）
                return True
            if limit >= 0 and value >= limit:  # 正向阈值（如金额）
                return True
    # 有 requires_approval=True 但 threshold 为空 → 始终审批
    return action_def.requires_approval and not threshold


async def _notify(action_id: str, action_type: str, payload: dict):
    """触发外部审批通知（飞书/钉钉/邮件）"""
    if _notifier:
        await _notifier.send(action_id, action_type, payload)
    else:
        print(f"[APPROVAL NEEDED] action_id={action_id} type={action_type}")


def _ok(object_id: str, action_id: str, status: str, message: str) -> str:
    return json.dumps({
        "success":   True,
        "object_id": object_id,
        "action_id": action_id,
        "status":    status,
        "message":   message,
    }, ensure_ascii=False)


def _err(message: str) -> str:
    return json.dumps({"success": False, "error": message}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
#  销售订单
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def create_sales_order(
    store_id:       str,
    distributor_id: str,
    sku_id:         str,
    quantity:       int,
    notes:          str = "",
    performed_by:   str = "agent",
) -> str:
    """
    创建销售订单（门店向经销商下单）。
    总金额 ≥ 5万 或 经销商授信不足时触发人工审批。

    Args:
        store_id:       门店 ID
        distributor_id: 经销商 ID
        sku_id:         SKU ID
        quantity:       下单数量
        notes:          备注
        performed_by:   执行方（agent ID 或 user ID）
    """
    # ── 前置校验 ──────────────────────────────────────────────
    store   = await _storage.get_object(store_id)
    distrib = await _storage.get_object(distributor_id)
    sku     = await _storage.get_object(sku_id)

    if not store:
        return _err(f"门店 {store_id} 不存在")
    if not distrib:
        return _err(f"经销商 {distributor_id} 不存在")
    if distrib.get("status") != "active":
        return _err(f"经销商 {distrib.get('name')} 已暂停合作，无法下单")
    if not sku:
        return _err(f"SKU {sku_id} 不存在")

    # 校验库存
    inv_list = await _storage.query_objects(
        "InventoryRecord",
        {"distributor_id": distributor_id, "sku_id": sku_id}
    )
    if not inv_list:
        return _err("该经销商没有此 SKU 的库存记录")
    inv = inv_list[0]
    if inv.get("available_quantity", 0) < quantity:
        return _err(
            f"库存不足：可售 {inv.get('available_quantity')} 件，"
            f"下单 {quantity} 件"
        )

    # 计算金额
    unit_price   = float(sku.get("unit_price", 0))
    total_amount = unit_price * quantity

    # 校验授信
    credit_limit      = float(distrib.get("credit_limit",       0))
    outstanding       = float(distrib.get("outstanding_amount", 0))
    if outstanding + total_amount > credit_limit:
        return _err(
            f"超出授信额度：已用 {outstanding}，"
            f"本单 {total_amount}，额度 {credit_limit}"
        )

    # ── 写入 Object ───────────────────────────────────────────
    order_id = str(uuid.uuid4())
    payload  = {
        "store_id":       store_id,
        "distributor_id": distributor_id,
        "sku_id":         sku_id,
        "quantity":       quantity,
        "unit_price":     unit_price,
        "total_amount":   total_amount,
        "status":         "pending",
        "notes":          notes,
    }
    await _storage.upsert_object("SalesOrder", order_id, payload)

    # ── 审批判断 ──────────────────────────────────────────────
    needs_approval = _should_require_approval(
        "create_sales_order", {"total_amount": total_amount}
    )
    approval_status = (
        ApprovalStatus.PENDING if needs_approval else ApprovalStatus.NOT_REQUIRED
    )

    action_id = await _storage.log_action(
        action_type="create_sales_order",
        object_type="SalesOrder",
        object_id=order_id,
        performed_by=performed_by,
        payload=payload,
        result={"order_id": order_id},
        approval_status=approval_status,
    )

    if needs_approval:
        await _notify(action_id, "create_sales_order", payload)
        return _ok(order_id, action_id, "pending_approval",
                   f"订单已创建（¥{total_amount:,.0f}），金额超 5 万，等待主管审批。"
                   f"审批 ID: {action_id}")

    # 不需审批 → 直接锁定库存
    await _lock_inventory(distributor_id, sku_id, quantity)
    return _ok(order_id, action_id, "confirmed",
               f"订单创建成功，已锁定库存 {quantity} 件，金额 ¥{total_amount:,.0f}")


@mcp.tool()
async def confirm_order_shipment(
    order_id:     str,
    performed_by: str = "agent",
) -> str:
    """
    确认发货，订单状态变更为 shipped，库存实际扣减。

    Args:
        order_id:     销售订单 ID
        performed_by: 执行方
    """
    order = await _storage.get_object(order_id)
    if not order:
        return _err(f"订单 {order_id} 不存在")
    if order.get("status") not in ("pending", "confirmed"):
        return _err(f"订单状态 {order.get('status')} 不可发货")

    # 更新订单状态
    updated = {**order, "status": "shipped", "shipped_at": datetime.now()}
    await _storage.upsert_object("SalesOrder", order_id, updated)

    # 实际扣减库存
    await _deduct_inventory(
        order["distributor_id"], order["sku_id"], order["quantity"]
    )

    action_id = await _storage.log_action(
        "confirm_order_shipment", "SalesOrder", order_id,
        performed_by, {"order_id": order_id},
        {"new_status": "shipped"},
    )
    return _ok(order_id, action_id, "shipped", "发货确认成功，库存已扣减")


# ═══════════════════════════════════════════════════════════════
#  铺货任务
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def create_listing_task(
    sku_id:         str,
    store_id:       str,
    distributor_id: str,
    target_date:    str,
    performed_by:   str = "agent",
) -> str:
    """
    创建铺货任务（将某 SKU 铺入某门店）。

    Args:
        sku_id:         SKU ID
        store_id:       目标门店 ID
        distributor_id: 负责经销商 ID
        target_date:    目标完成日期，格式 YYYY-MM-DD
        performed_by:   执行方
    """
    task_id = str(uuid.uuid4())
    payload = {
        "sku_id":         sku_id,
        "store_id":       store_id,
        "distributor_id": distributor_id,
        "target_date":    target_date,
        "status":         "pending",
    }
    await _storage.upsert_object("ListingTask", task_id, payload)

    action_id = await _storage.log_action(
        "create_listing_task", "ListingTask", task_id,
        performed_by, payload, {"task_id": task_id},
    )
    return _ok(task_id, action_id, "created", f"铺货任务已创建，目标日期 {target_date}")


@mcp.tool()
async def update_listing_status(
    task_id:       str,
    status:        str,
    shelf_position: str = "",
    facings:       int  = 0,
    notes:         str  = "",
    performed_by:  str  = "agent",
) -> str:
    """
    更新铺货任务状态。

    Args:
        task_id:        铺货任务 ID
        status:         新状态：in_progress / listed / failed
        shelf_position: 货架位置（上架后填写）
        facings:        陈列面数
        notes:          备注
        performed_by:   执行方
    """
    task = await _storage.get_object(task_id)
    if not task:
        return _err(f"铺货任务 {task_id} 不存在")

    updated = {
        **task,
        "status":         status,
        "shelf_position": shelf_position or task.get("shelf_position", ""),
        "facings":        facings or task.get("facings", 0),
        "notes":          notes or task.get("notes", ""),
    }
    if status == "listed":
        updated["listed_at"] = datetime.now().isoformat()

    await _storage.upsert_object("ListingTask", task_id, updated)

    action_id = await _storage.log_action(
        "update_listing_status", "ListingTask", task_id,
        performed_by, {"status": status}, {"task_id": task_id},
    )
    return _ok(task_id, action_id, status, f"铺货任务状态更新为 {status}")


# ═══════════════════════════════════════════════════════════════
#  促销活动
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def create_promotion(
    name:                str,
    promo_type:          str,
    start_date:          str,
    end_date:            str,
    discount_rate:       float,
    budget:              float,
    min_quantity:        int  = 0,
    applicable_channels: str  = "[]",
    performed_by:        str  = "agent",
) -> str:
    """
    创建促销活动。预算 ≥ 10 万触发人工审批。

    Args:
        name:                活动名称
        promo_type:          类型：discount/bundled/gift/rebate
        start_date:          开始日期 YYYY-MM-DD
        end_date:            结束日期 YYYY-MM-DD
        discount_rate:       折扣率（0.85 = 八五折）
        budget:              预算（元）
        min_quantity:        最低起购量
        applicable_channels: JSON 数组字符串，如 '["KA","CVS"]'
        performed_by:        执行方
    """
    promo_id = str(uuid.uuid4())
    channels = json.loads(applicable_channels) if applicable_channels else []
    payload  = {
        "name":                name,
        "promo_type":          promo_type,
        "start_date":          start_date,
        "end_date":            end_date,
        "discount_rate":       discount_rate,
        "budget":              budget,
        "spent":               0.0,
        "min_quantity":        min_quantity,
        "applicable_channels": channels,
        "status":              "draft",
    }
    await _storage.upsert_object("Promotion", promo_id, payload)

    needs_approval = _should_require_approval("create_promotion", {"budget": budget})
    approval_status = (
        ApprovalStatus.PENDING if needs_approval else ApprovalStatus.NOT_REQUIRED
    )
    action_id = await _storage.log_action(
        "create_promotion", "Promotion", promo_id,
        performed_by, payload, {"promo_id": promo_id},
        approval_status=approval_status,
    )

    if needs_approval:
        await _notify(action_id, "create_promotion", payload)
        return _ok(promo_id, action_id, "pending_approval",
                   f"促销活动预算 ¥{budget:,.0f} 超 10 万，等待审批。ID: {action_id}")

    return _ok(promo_id, action_id, "draft",
               f"促销活动「{name}」已创建（draft 状态），可激活后生效")


# ═══════════════════════════════════════════════════════════════
#  审批操作（Human-in-loop 回调）
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def approve_action(
    action_id:        str,
    approved_by:      str,
    approved:         bool = True,
    rejection_reason: str  = "",
) -> str:
    """
    审批一个待处理的 Action。
    审批通过后，系统自动执行对应的后续操作。

    Args:
        action_id:        来自 ActionLog 的 ID
        approved_by:      审批人 ID 或姓名
        approved:         True=通过，False=拒绝
        rejection_reason: 拒绝原因（拒绝时必填）
    """
    success = await _storage.resolve_approval(
        action_id, approved, approved_by, rejection_reason
    )
    if not success:
        return _err(f"action_id {action_id} 不存在或已处理")

    status  = "approved" if approved else "rejected"
    message = (
        f"Action {action_id} 已{('通过' if approved else '拒绝')}审批"
        + (f"，拒绝原因：{rejection_reason}" if not approved else "")
    )
    return json.dumps({
        "success":   True,
        "action_id": action_id,
        "status":    status,
        "message":   message,
    }, ensure_ascii=False)


@mcp.tool()
async def get_pending_approvals(performed_by: str = "") -> str:
    """
    获取所有待审批的 Action 列表。
    审批人可调用此工具查看当前积压的审批项。
    """
    items = await _storage.get_pending_approvals()
    return json.dumps(items, default=str, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
#  内部辅助（不暴露给 Agent）
# ═══════════════════════════════════════════════════════════════

async def _lock_inventory(distributor_id: str, sku_id: str, quantity: int):
    records = await _storage.query_objects(
        "InventoryRecord", {"distributor_id": distributor_id, "sku_id": sku_id}
    )
    if records:
        rec = records[0]
        rec["locked_quantity"]    = rec.get("locked_quantity", 0) + quantity
        rec["available_quantity"] = rec.get("available_quantity", 0) - quantity
        await _storage.upsert_object("InventoryRecord", rec["id"], rec)


async def _deduct_inventory(distributor_id: str, sku_id: str, quantity: int):
    records = await _storage.query_objects(
        "InventoryRecord", {"distributor_id": distributor_id, "sku_id": sku_id}
    )
    if records:
        rec = records[0]
        rec["quantity"]        = max(0, rec.get("quantity",        0) - quantity)
        rec["locked_quantity"] = max(0, rec.get("locked_quantity", 0) - quantity)
        rec["last_updated"]    = datetime.now().isoformat()
        await _storage.upsert_object("InventoryRecord", rec["id"], rec)
