"""
agents/orchestrator.py
───────────────────────
渠道管理 Orchestrator Agent
对应 Palantir AIP Orchestrator

职责：
  1. 接收用户自然语言指令
  2. 通过 MCP 工具与 Ontology 交互（读/写）
  3. 多轮推理直到任务完成或需要人工介入
  4. 维护对话历史（支持追问）

工具调用模式：Native Tool Calling（并行调用）
"""

from __future__ import annotations
import json
import os
from typing import Any

import anthropic

# ── System Prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
你是元气森林渠道管理智能助手，代号 GenkiAgent。

## 你的核心职责
- 渠道数据查询与分析（经销商、门店、库存、销售）
- 铺货任务创建与状态追踪
- 销售订单管理
- 促销活动创建与分析
- 渠道覆盖率分析和异常预警

## 工具使用规则（严格遵守）
1. **写操作前必须先读**：执行任何写操作（create_*/update_*）前，
   先用 search_objects 或 get_object 确认相关对象存在且状态正确
2. **经销商状态校验**：涉及经销商的操作，先确认 status = "active"
3. **库存检查**：下单前必须调用 get_inventory 确认 available_quantity 充足
4. **审批透明**：写操作返回 pending_approval 时，明确告知用户等待审批，
   并提供 action_id 便于追踪
5. **并行查询**：多个独立查询可以并行调用（工具名之间没有依赖时）

## 返回格式
- 查询结果：结构清晰，关键数字加粗标注
- 写操作结果：明确说明执行结果和后续步骤
- 异常情况：清楚说明原因和建议操作
- 涉及金额时，使用"¥xxx,xxx"格式

## 你无法做的事
- 直接修改 Ontology Schema（只读 Object，不改类型定义）
- 绕过审批流程
- 访问你没有工具权限的数据
"""


class GenkiOrchestrator:
    """
    渠道管理 Orchestrator Agent
    支持多轮对话，工具调用循环直到 end_turn
    """

    def __init__(self, tools: list[dict]):
        """
        Args:
            tools: 从 MCP Server 获取的工具列表（Anthropic tool format）
        """
        self.client  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.tools   = tools
        self.history: list[dict] = []
        self.call_log: list[dict] = []   # 记录每次工具调用，便于调试

    # ── 主入口 ────────────────────────────────────────────────

    async def chat(self, user_message: str) -> str:
        """
        接收用户消息，执行推理-工具调用循环，返回最终文本回复
        """
        self.history.append({"role": "user", "content": user_message})

        loop_count = 0
        max_loops  = 15   # 防止死循环

        while loop_count < max_loops:
            loop_count += 1

            response = self.client.messages.create(
                model      = "claude-sonnet-4-6",
                max_tokens = 4096,
                system     = SYSTEM_PROMPT,
                tools      = self.tools,
                messages   = self.history,
            )

            # ── 纯文本回复 → 结束 ────────────────────────────
            if response.stop_reason == "end_turn":
                text = next(
                    (b.text for b in response.content if hasattr(b, "text")), ""
                )
                self.history.append({"role": "assistant", "content": text})
                return text

            # ── Tool Use → 执行工具，继续推理 ────────────────
            if response.stop_reason == "tool_use":
                # 把 LLM 的完整响应（含 tool_use blocks）加入历史
                self.history.append({
                    "role":    "assistant",
                    "content": response.content,
                })

                # 并行执行所有工具调用
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    print(f"  ▶ [Tool] {block.name}  params={block.input}")
                    result = await self._dispatch_tool(block.name, block.input)
                    print(f"  ◀ [Tool] {block.name}  result_len={len(result)}")

                    self.call_log.append({
                        "tool":   block.name,
                        "input":  block.input,
                        "result": result,
                    })
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })

                self.history.append({
                    "role":    "user",
                    "content": tool_results,
                })

        return "⚠️ 推理轮数超限，请简化问题或分步提问。"

    def reset(self):
        """清空对话历史（开始新会话）"""
        self.history  = []
        self.call_log = []

    # ── 工具分发 ──────────────────────────────────────────────

    async def _dispatch_tool(self, tool_name: str, params: dict) -> str:
        """
        将工具调用路由到对应的 MCP Server
        实际生产中通过 mcp.ClientSession 调用，
        这里直接调用函数简化演示
        """
        from mcp.ontology_mcp import (
            search_objects, get_object, semantic_search,
            get_inventory, get_linked_objects,
            get_channel_coverage, get_sales_summary,
        )
        from mcp.action_mcp import (
            create_sales_order, confirm_order_shipment,
            create_listing_task, update_listing_status,
            create_promotion, approve_action, get_pending_approvals,
        )

        tool_map = {
            # 读工具
            "search_objects":       search_objects,
            "get_object":           get_object,
            "semantic_search":      semantic_search,
            "get_inventory":        get_inventory,
            "get_linked_objects":   get_linked_objects,
            "get_channel_coverage": get_channel_coverage,
            "get_sales_summary":    get_sales_summary,
            # 写工具
            "create_sales_order":   create_sales_order,
            "confirm_order_shipment": confirm_order_shipment,
            "create_listing_task":  create_listing_task,
            "update_listing_status": update_listing_status,
            "create_promotion":     create_promotion,
            "approve_action":       approve_action,
            "get_pending_approvals": get_pending_approvals,
        }

        fn = tool_map.get(tool_name)
        if fn is None:
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

        try:
            return await fn(**params)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
