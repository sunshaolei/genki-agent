"""
mcp/ontology_mcp.py
────────────────────
Ontology MCP Server —— 读工具集
对应 Palantir Ontology MCP（运行态·只读端）

工具清单：
  search_objects      结构化过滤查询
  get_object          按 ID 精确查询
  semantic_search     自然语言语义检索
  get_inventory       库存查询（含预警）
  get_linked_objects  关系图谱遍历
  get_channel_coverage 渠道覆盖分析
  get_distributor_orders 经销商订单汇总
"""

from __future__ import annotations
import json
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

# storage 在 server 启动时注入
_storage = None

mcp = FastMCP(
    "GenkiOntologyMCP",
    instructions="""
你正在访问元气森林渠道管理本体（Ontology）。
可查询的 Object Type：
  Brand / Product / SKU / Channel / Distributor /
  Store / InventoryRecord / SalesOrder / Promotion / ListingTask

查询规则：
1. 执行写操作前，必须先用读工具确认对象存在且状态正确
2. 涉及 Distributor 的操作需先确认其 status = active
3. 库存相关操作先用 get_inventory 确认 available_quantity
""",
)


def set_storage(storage):
    global _storage
    _storage = storage


# ═══════════════════════════════════════════════════════════════
#  基础查询工具
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def search_objects(
    object_type: str,
    filters: Optional[str] = None,
    limit: int = 20,
) -> str:
    """
    按类型和条件查询 Ontology 对象。

    Args:
        object_type: Brand/Product/SKU/Channel/Distributor/Store/
                     InventoryRecord/SalesOrder/Promotion/ListingTask
        filters:     JSON 字符串，键值精确匹配。
                     示例: '{"status":"active","region":"华东"}'
        limit:       最多返回条数，默认 20

    Returns:
        JSON 数组，每个元素为一个 Object 的完整属性
    """
    parsed_filters = json.loads(filters) if filters else None
    results = await _storage.query_objects(object_type, parsed_filters, limit)
    return json.dumps(results, default=str, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_object(object_id: str) -> str:
    """
    按 ID 精确获取单个 Ontology 对象。

    Args:
        object_id: 对象的唯一 ID（UUID）

    Returns:
        对象的完整属性 JSON，不存在则返回 null
    """
    obj = await _storage.get_object(object_id)
    return json.dumps(obj, default=str, ensure_ascii=False, indent=2)


@mcp.tool()
async def semantic_search(
    query: str,
    object_type: Optional[str] = None,
    top_k: int = 6,
) -> str:
    """
    自然语言语义检索 Ontology 对象。
    适合模糊查询，如"华东地区高分级门店"、"碳酸类产品"。

    Args:
        query:       自然语言描述
        object_type: 限定类型（可选），不填则全类型检索
        top_k:       返回最相似的 top_k 个结果

    Returns:
        JSON 数组，含 similarity 字段（0-1，越高越相关）
    """
    from ontology.embeddings import get_embedding
    embedding = await get_embedding(query)
    results   = await _storage.semantic_search(embedding, object_type, top_k)
    return json.dumps(results, default=str, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
#  业务专用查询工具
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def get_inventory(
    distributor_id: Optional[str] = None,
    sku_id: Optional[str] = None,
    low_stock_only: bool = False,
) -> str:
    """
    查询库存状态。

    Args:
        distributor_id: 指定经销商（为空则查全部）
        sku_id:         指定 SKU（为空则查全部）
        low_stock_only: True 则仅返回库存低于预警线的记录

    Returns:
        库存记录列表，含 sku_name、available_quantity、reorder_threshold
    """
    filters: dict = {}
    if distributor_id:
        filters["distributor_id"] = distributor_id
    if sku_id:
        filters["sku_id"] = sku_id

    records = await _storage.query_objects("InventoryRecord", filters or None)

    enriched = []
    for rec in records:
        # 关联查询 SKU 的预警阈值和名称
        sku = await _storage.get_object(rec.get("sku_id", ""))
        if sku:
            rec["sku_name"]          = sku.get("name", "")
            rec["sku_code"]          = sku.get("sku_code", "")
            rec["reorder_threshold"] = sku.get("reorder_threshold", 100)
            rec["is_low_stock"]      = (
                rec.get("available_quantity", 0) <= rec["reorder_threshold"]
            )

        if low_stock_only and not rec.get("is_low_stock"):
            continue
        enriched.append(rec)

    return json.dumps(enriched, default=str, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_linked_objects(
    source_id: str,
    link_type: Optional[str] = None,
) -> str:
    """
    遍历 Ontology 关系图谱，获取与 source_id 关联的对象。

    常用 link_type：
      has_sku            Product → SKU
      covers_channel     Distributor → Channel
      contains_store     Channel → Store
      holds_inventory    Distributor → InventoryRecord
      in_promotion       SKU → Promotion

    Args:
        source_id: 源对象 ID
        link_type: 关系类型（为空则返回所有关联）

    Returns:
        关联对象列表，含 _link_type 字段
    """
    results = await _storage.get_linked_objects(source_id, link_type)
    return json.dumps(results, default=str, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_channel_coverage(
    distributor_id: str,
) -> str:
    """
    分析某经销商的渠道覆盖情况。
    返回：渠道数、门店总数、各渠道门店分布、铺货完成率

    Args:
        distributor_id: 经销商 ID
    """
    distributor = await _storage.get_object(distributor_id)
    if not distributor:
        return json.dumps({"error": "经销商不存在"}, ensure_ascii=False)

    # 查该经销商下所有门店
    stores = await _storage.query_objects(
        "Store", {"distributor_id": distributor_id})

    # 查铺货任务完成情况
    listing_tasks = await _storage.query_objects(
        "ListingTask", {"distributor_id": distributor_id})

    total    = len(listing_tasks)
    listed   = sum(1 for t in listing_tasks if t.get("status") == "listed")
    pending  = sum(1 for t in listing_tasks if t.get("status") == "pending")
    failed   = sum(1 for t in listing_tasks if t.get("status") == "failed")

    # 按门店分级统计
    tier_dist = {}
    for s in stores:
        tier = s.get("tier", "C")
        tier_dist[tier] = tier_dist.get(tier, 0) + 1

    summary = {
        "distributor_id":   distributor_id,
        "distributor_name": distributor.get("name"),
        "region":           distributor.get("region"),
        "total_stores":     len(stores),
        "store_tier_distribution": tier_dist,
        "listing_tasks": {
            "total":             total,
            "listed":            listed,
            "pending":           pending,
            "failed":            failed,
            "completion_rate":   f"{listed/total*100:.1f}%" if total else "N/A",
        },
    }
    return json.dumps(summary, default=str, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_sales_summary(
    distributor_id: Optional[str] = None,
    sku_id: Optional[str] = None,
    status: Optional[str] = None,
) -> str:
    """
    查询销售订单汇总。

    Args:
        distributor_id: 经销商 ID（可选）
        sku_id:         SKU ID（可选）
        status:         订单状态 pending/confirmed/shipped/completed（可选）

    Returns:
        订单列表 + 汇总统计（总金额、总数量）
    """
    filters: dict = {}
    if distributor_id:
        filters["distributor_id"] = distributor_id
    if sku_id:
        filters["sku_id"] = sku_id
    if status:
        filters["status"] = status

    orders = await _storage.query_objects("SalesOrder", filters or None, limit=100)

    total_amount   = sum(o.get("total_amount",  0) for o in orders)
    total_quantity = sum(o.get("quantity",       0) for o in orders)

    return json.dumps({
        "orders":         orders,
        "summary": {
            "count":          len(orders),
            "total_amount":   total_amount,
            "total_quantity": total_quantity,
        }
    }, default=str, ensure_ascii=False, indent=2)
