"""
api/main.py
────────────
FastAPI 主入口
提供：
  POST /chat          — 与 Agent 对话
  POST /approve       — 人工审批回调
  GET  /approvals     — 查看待审批列表
  POST /seed          — 写入示例数据（开发用）
"""

from __future__ import annotations
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ontology.storage import OntologyStorage
from agents.orchestrator import GenkiOrchestrator
from agents.tool_definitions import TOOLS
from mcp import ontology_mcp, action_mcp


# ── 全局对象 ───────────────────────────────────────────────────
storage:     OntologyStorage | None = None
agent:       GenkiOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage, agent

    # 初始化存储
    dsn     = os.getenv("DATABASE_URL", "postgresql://genki:genki@localhost:5432/genki")
    storage = OntologyStorage(dsn)
    await storage.init()

    # 注入依赖
    ontology_mcp.set_storage(storage)
    action_mcp.set_dependencies(storage, notifier=None)

    # 初始化 Agent
    agent = GenkiOrchestrator(tools=TOOLS)

    print("✅ GenkiAgent 启动完成")
    yield

    await storage.close()


app = FastAPI(
    title="GenkiAgent — 元气森林渠道管理",
    description="基于 Ontology + MCP + Agent 的渠道管理智能助手",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ── Request / Response Models ──────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    reset:   bool = False   # True 则清空对话历史

class ChatResponse(BaseModel):
    reply:    str
    tool_calls: list[dict] = []

class ApprovalRequest(BaseModel):
    action_id:        str
    approved_by:      str
    approved:         bool = True
    rejection_reason: str  = ""


# ── API Endpoints ──────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """与渠道管理 Agent 对话"""
    if req.reset:
        agent.reset()

    reply = await agent.chat(req.message)
    return ChatResponse(reply=reply, tool_calls=agent.call_log[-10:])


@app.post("/approve")
async def approve(req: ApprovalRequest):
    """人工审批回调（来自审批面板或 Webhook）"""
    from mcp.action_mcp import approve_action
    result = await approve_action(
        action_id        = req.action_id,
        approved_by      = req.approved_by,
        approved         = req.approved,
        rejection_reason = req.rejection_reason,
    )
    import json
    return json.loads(result)


@app.get("/approvals")
async def get_approvals():
    """查看待审批列表"""
    items = await storage.get_pending_approvals()
    return {"items": items, "count": len(items)}


@app.post("/seed")
async def seed_data():
    """写入示例数据（开发/演示用）"""
    from api.seed import run_seed
    await run_seed(storage)
    return {"message": "示例数据已写入"}


@app.get("/health")
async def health():
    return {"status": "ok"}
