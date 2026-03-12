"""
agents/tool_definitions.py
───────────────────────────
所有 MCP 工具的 Anthropic Tool 格式定义
Agent 初始化时加载，传给 Claude API
"""

TOOLS: list[dict] = [

    # ══════════════════════════════════════════════════════════
    #  读工具
    # ══════════════════════════════════════════════════════════

    {
        "name": "search_objects",
        "description": (
            "按类型和条件查询 Ontology 对象。"
            "支持类型：Brand/Product/SKU/Channel/Distributor/"
            "Store/InventoryRecord/SalesOrder/Promotion/ListingTask"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "object_type": {
                    "type": "string",
                    "description": "对象类型名称",
                },
                "filters": {
                    "type": "string",
                    "description": (
                        "JSON 字符串，键值精确匹配过滤条件。"
                        "示例：'{\"status\":\"active\",\"region\":\"华东\"}'"
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回条数，默认 20",
                    "default": 20,
                },
            },
            "required": ["object_type"],
        },
    },

    {
        "name": "get_object",
        "description": "按 ID 精确获取单个 Ontology 对象的完整属性",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_id": {
                    "type": "string",
                    "description": "对象的唯一 ID（UUID）",
                }
            },
            "required": ["object_id"],
        },
    },

    {
        "name": "semantic_search",
        "description": (
            "自然语言语义检索 Ontology 对象。"
            "适合模糊查询，如'华东地区高分级门店'、'碳酸类产品'、"
            "'库存紧张的 SKU'。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "自然语言描述",
                },
                "object_type": {
                    "type": "string",
                    "description": "限定对象类型（可选）",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回最相似的 top_k 个，默认 6",
                    "default": 6,
                },
            },
            "required": ["query"],
        },
    },

    {
        "name": "get_inventory",
        "description": (
            "查询库存状态，可按经销商/SKU过滤，"
            "支持只返回低于预警线的库存记录"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "distributor_id": {
                    "type": "string",
                    "description": "经销商 ID（可选）",
                },
                "sku_id": {
                    "type": "string",
                    "description": "SKU ID（可选）",
                },
                "low_stock_only": {
                    "type": "boolean",
                    "description": "True 则仅返回库存低于预警线的记录",
                    "default": False,
                },
            },
        },
    },

    {
        "name": "get_linked_objects",
        "description": (
            "遍历 Ontology 关系图谱，获取关联对象。"
            "常用 link_type：has_sku / covers_channel / "
            "contains_store / holds_inventory / in_promotion"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "源对象 ID",
                },
                "link_type": {
                    "type": "string",
                    "description": "关系类型（可选，为空返回全部关联）",
                },
            },
            "required": ["source_id"],
        },
    },

    {
        "name": "get_channel_coverage",
        "description": (
            "分析某经销商的渠道覆盖情况："
            "返回渠道数、门店分级分布、铺货完成率"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "distributor_id": {
                    "type": "string",
                    "description": "经销商 ID",
                }
            },
            "required": ["distributor_id"],
        },
    },

    {
        "name": "get_sales_summary",
        "description": "查询销售订单汇总，可按经销商/SKU/状态过滤",
        "input_schema": {
            "type": "object",
            "properties": {
                "distributor_id": {"type": "string"},
                "sku_id":         {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "confirmed", "shipped", "completed"],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════
    #  写工具（Action）
    # ══════════════════════════════════════════════════════════

    {
        "name": "create_sales_order",
        "description": (
            "创建销售订单（门店向经销商下单）。"
            "⚠️ 执行前必须先用 get_inventory 确认库存充足。"
            "总金额 ≥ 5 万时触发人工审批。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id":       {"type": "string", "description": "门店 ID"},
                "distributor_id": {"type": "string", "description": "经销商 ID"},
                "sku_id":         {"type": "string", "description": "SKU ID"},
                "quantity":       {"type": "integer", "description": "下单数量"},
                "notes":          {"type": "string",  "description": "备注"},
                "performed_by":   {"type": "string",  "description": "执行方 ID"},
            },
            "required": ["store_id", "distributor_id", "sku_id", "quantity"],
        },
    },

    {
        "name": "confirm_order_shipment",
        "description": "确认发货，订单状态 → shipped，库存实际扣减",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id":     {"type": "string"},
                "performed_by": {"type": "string"},
            },
            "required": ["order_id"],
        },
    },

    {
        "name": "create_listing_task",
        "description": "创建铺货任务（将某 SKU 铺入某门店）",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku_id":         {"type": "string", "description": "SKU ID"},
                "store_id":       {"type": "string", "description": "目标门店 ID"},
                "distributor_id": {"type": "string", "description": "负责经销商 ID"},
                "target_date":    {"type": "string", "description": "目标完成日期 YYYY-MM-DD"},
                "performed_by":   {"type": "string"},
            },
            "required": ["sku_id", "store_id", "distributor_id", "target_date"],
        },
    },

    {
        "name": "update_listing_status",
        "description": "更新铺货任务状态（in_progress/listed/failed）",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id":        {"type": "string"},
                "status":         {
                    "type": "string",
                    "enum": ["in_progress", "listed", "failed"],
                },
                "shelf_position": {"type": "string", "description": "货架位置"},
                "facings":        {"type": "integer", "description": "陈列面数"},
                "notes":          {"type": "string"},
                "performed_by":   {"type": "string"},
            },
            "required": ["task_id", "status"],
        },
    },

    {
        "name": "create_promotion",
        "description": (
            "创建促销活动。"
            "⚠️ 预算 ≥ 10 万时触发人工审批。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name":                {"type": "string"},
                "promo_type":          {
                    "type": "string",
                    "enum": ["discount", "bundled", "gift", "rebate"],
                },
                "start_date":          {"type": "string", "description": "YYYY-MM-DD"},
                "end_date":            {"type": "string", "description": "YYYY-MM-DD"},
                "discount_rate":       {"type": "number", "description": "折扣率，0.85=八五折"},
                "budget":              {"type": "number", "description": "预算（元）"},
                "min_quantity":        {"type": "integer", "description": "最低起购量"},
                "applicable_channels": {"type": "string", "description": "渠道列表 JSON 数组"},
                "performed_by":        {"type": "string"},
            },
            "required": ["name", "promo_type", "start_date", "end_date",
                         "discount_rate", "budget"],
        },
    },

    {
        "name": "approve_action",
        "description": (
            "审批一个待处理的 Action（人工审批回调）。"
            "审批通过后系统自动执行对应操作。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action_id":        {"type": "string", "description": "ActionLog ID"},
                "approved_by":      {"type": "string", "description": "审批人"},
                "approved":         {"type": "boolean", "description": "True=通过，False=拒绝"},
                "rejection_reason": {"type": "string",  "description": "拒绝原因"},
            },
            "required": ["action_id", "approved_by"],
        },
    },

    {
        "name": "get_pending_approvals",
        "description": "获取所有待审批的 Action 列表，审批人用于查看积压审批项",
        "input_schema": {
            "type": "object",
            "properties": {
                "performed_by": {"type": "string"},
            },
        },
    },
]
