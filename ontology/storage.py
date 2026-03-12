"""
ontology/storage.py
────────────────────
Object Storage V2 简化实现
PostgreSQL + pgvector

职责：
  1. Object CRUD（upsert / get / query）
  2. 语义向量检索（pgvector cosine similarity）
  3. Link 关系图谱（source → target 双向查询）
  4. Action Log 写入与审批状态更新
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime
from typing import Any

import asyncpg

from ontology.schema import ActionLog, ApprovalStatus


# ═══════════════════════════════════════════════════════════════
#  DDL
# ═══════════════════════════════════════════════════════════════

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Object 主表 ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ontology_objects (
    id           TEXT         PRIMARY KEY,
    object_type  TEXT         NOT NULL,
    properties   JSONB        NOT NULL DEFAULT '{}',
    embedding    vector(1536),
    created_at   TIMESTAMPTZ  DEFAULT now(),
    updated_at   TIMESTAMPTZ  DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_obj_type
    ON ontology_objects (object_type);
CREATE INDEX IF NOT EXISTS idx_obj_type_props
    ON ontology_objects USING GIN (properties);
CREATE INDEX IF NOT EXISTS idx_obj_embedding
    ON ontology_objects USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ── Link 关系表 ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ontology_links (
    id          TEXT  PRIMARY KEY,
    link_type   TEXT  NOT NULL,
    source_id   TEXT  NOT NULL,
    target_id   TEXT  NOT NULL,
    properties  JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_link_source ON ontology_links (source_id);
CREATE INDEX IF NOT EXISTS idx_link_target ON ontology_links (target_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_link_unique
    ON ontology_links (link_type, source_id, target_id);

-- ── Action 审计日志 ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS action_logs (
    id               TEXT        PRIMARY KEY,
    action_type      TEXT        NOT NULL,
    object_type      TEXT,
    object_id        TEXT,
    performed_by     TEXT,
    payload          JSONB       DEFAULT '{}',
    result           JSONB       DEFAULT '{}',
    approval_status  TEXT        DEFAULT 'not_required',
    approved_by      TEXT,
    approved_at      TIMESTAMPTZ,
    rejection_reason TEXT,
    timestamp        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alog_status
    ON action_logs (approval_status);
CREATE INDEX IF NOT EXISTS idx_alog_object
    ON action_logs (object_type, object_id);
"""


# ═══════════════════════════════════════════════════════════════
#  OntologyStorage
# ═══════════════════════════════════════════════════════════════

class OntologyStorage:

    def __init__(self, dsn: str):
        self.dsn  = dsn
        self.pool: asyncpg.Pool | None = None

    # ── 初始化 ────────────────────────────────────────────────

    async def init(self):
        self.pool = await asyncpg.create_pool(self.dsn, min_size=2, max_size=10)
        async with self.pool.acquire() as conn:
            await conn.execute(DDL)

    async def close(self):
        if self.pool:
            await self.pool.close()

    # ── Object CRUD ───────────────────────────────────────────

    async def upsert_object(
        self,
        object_type: str,
        object_id:   str,
        properties:  dict,
        embedding:   list[float] | None = None,
    ) -> str:
        """写入或更新一个 Ontology Object"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ontology_objects
                    (id, object_type, properties, embedding, updated_at)
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (id) DO UPDATE
                    SET properties = $3,
                        embedding  = COALESCE($4, ontology_objects.embedding),
                        updated_at = now()
                """,
                object_id,
                object_type,
                json.dumps(properties, default=str),
                embedding,
            )
        return object_id

    async def get_object(self, object_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, object_type, properties, created_at, updated_at "
                "FROM ontology_objects WHERE id = $1",
                object_id,
            )
        if not row:
            return None
        return self._unpack_row(row)

    async def query_objects(
        self,
        object_type: str,
        filters:     dict | None = None,
        limit:       int = 50,
    ) -> list[dict]:
        """
        结构化过滤查询
        filters 示例：{"status": "active", "region": "华东"}
        支持 JSONB 精确匹配；如需范围查询可扩展
        """
        async with self.pool.acquire() as conn:
            if not filters:
                rows = await conn.fetch(
                    "SELECT id, object_type, properties, created_at, updated_at "
                    "FROM ontology_objects "
                    "WHERE object_type = $1 LIMIT $2",
                    object_type, limit,
                )
            else:
                # 动态拼接 JSONB 过滤条件
                conditions = []
                params: list[Any] = [object_type]
                for k, v in filters.items():
                    params.append(str(v))
                    conditions.append(
                        f"properties->>'{k}' = ${len(params)}"
                    )
                where = " AND ".join(conditions)
                rows = await conn.fetch(
                    f"SELECT id, object_type, properties, created_at, updated_at "
                    f"FROM ontology_objects "
                    f"WHERE object_type = $1 AND {where} LIMIT {limit}",
                    *params,
                )
        return [self._unpack_row(r) for r in rows]

    async def semantic_search(
        self,
        query_embedding: list[float],
        object_type:     str | None = None,
        top_k:           int = 8,
        min_similarity:  float = 0.4,
    ) -> list[dict]:
        """向量语义检索，返回 similarity 字段"""
        async with self.pool.acquire() as conn:
            type_cond = "AND object_type = $3" if object_type else ""
            extra     = [object_type] if object_type else []
            rows = await conn.fetch(
                f"""
                SELECT id, object_type, properties, created_at, updated_at,
                       1 - (embedding <=> $1) AS similarity
                FROM ontology_objects
                WHERE embedding IS NOT NULL
                  {type_cond}
                  AND 1 - (embedding <=> $1) >= {min_similarity}
                ORDER BY embedding <=> $1
                LIMIT $2
                """,
                query_embedding, top_k, *extra,
            )
        return [self._unpack_row(r, include_similarity=True) for r in rows]

    # ── Link 关系图谱 ─────────────────────────────────────────

    async def upsert_link(
        self,
        link_type:   str,
        source_id:   str,
        target_id:   str,
        properties:  dict | None = None,
    ) -> str:
        link_id = str(uuid.uuid4())
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ontology_links (id, link_type, source_id, target_id, properties)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (link_type, source_id, target_id) DO UPDATE
                    SET properties = $5
                """,
                link_id, link_type, source_id, target_id,
                json.dumps(properties or {}, default=str),
            )
        return link_id

    async def get_linked_objects(
        self,
        source_id: str,
        link_type: str | None = None,
    ) -> list[dict]:
        """获取 source_id 出发的所有关联对象"""
        async with self.pool.acquire() as conn:
            link_filter = "AND link_type = $2" if link_type else ""
            params      = [source_id] + ([link_type] if link_type else [])
            links = await conn.fetch(
                f"SELECT * FROM ontology_links "
                f"WHERE source_id = $1 {link_filter}",
                *params,
            )
            result = []
            for lnk in links:
                obj = await self.get_object(lnk["target_id"])
                if obj:
                    obj["_link_type"]       = lnk["link_type"]
                    obj["_link_properties"] = json.loads(lnk["properties"])
                    result.append(obj)
        return result

    # ── Action Log ────────────────────────────────────────────

    async def log_action(
        self,
        action_type:     str,
        object_type:     str,
        object_id:       str,
        performed_by:    str,
        payload:         dict,
        result:          dict,
        approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED,
    ) -> str:
        action_id = str(uuid.uuid4())
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO action_logs
                    (id, action_type, object_type, object_id, performed_by,
                     payload, result, approval_status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                action_id, action_type, object_type, object_id, performed_by,
                json.dumps(payload, default=str),
                json.dumps(result,  default=str),
                approval_status.value,
            )
        return action_id

    async def get_pending_approvals(self) -> list[dict]:
        """获取所有待审批的 Action"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM action_logs WHERE approval_status = 'pending' "
                "ORDER BY timestamp DESC"
            )
        return [dict(r) for r in rows]

    async def resolve_approval(
        self,
        action_id:        str,
        approved:         bool,
        approved_by:      str,
        rejection_reason: str = "",
    ) -> bool:
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE action_logs
                SET approval_status  = $2,
                    approved_by      = $3,
                    approved_at      = now(),
                    rejection_reason = $4
                WHERE id = $1
                """,
                action_id, status.value, approved_by, rejection_reason,
            )
        return result == "UPDATE 1"

    # ── 内部工具 ──────────────────────────────────────────────

    @staticmethod
    def _unpack_row(row, include_similarity: bool = False) -> dict:
        d = dict(row)
        if isinstance(d.get("properties"), str):
            d["properties"] = json.loads(d["properties"])
        # 把 properties 的字段提升到顶层，方便 Agent 直接引用
        props = d.pop("properties", {})
        d.update(props)
        if include_similarity:
            d["similarity"] = round(float(d.get("similarity", 0)), 4)
        return d
