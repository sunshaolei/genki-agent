"""
api/seed.py
────────────
写入元气森林渠道管理示例数据
用于开发环境快速验证
"""

from __future__ import annotations
import uuid
from ontology.storage import OntologyStorage


async def run_seed(storage: OntologyStorage):
    print("🌱 写入示例数据...")

    # ── Brand ─────────────────────────────────────────────────
    brand_id = "brand-genki-001"
    await storage.upsert_object("Brand", brand_id, {
        "name": "元气森林", "description": "主打无糖健康的新消费饮料品牌",
        "launch_year": 2016, "is_active": True,
    })

    brand_alien_id = "brand-alien-001"
    await storage.upsert_object("Brand", brand_alien_id, {
        "name": "外星人", "description": "功能性能量饮料品牌",
        "launch_year": 2020, "is_active": True,
    })

    # ── Product ───────────────────────────────────────────────
    product_bubble_id = "prod-bubble-001"
    await storage.upsert_object("Product", product_bubble_id, {
        "brand_id": brand_id, "name": "气泡水",
        "category": "碳酸饮料", "description": "无糖气泡水系列",
        "is_active": True,
    })

    product_energy_id = "prod-energy-001"
    await storage.upsert_object("Product", product_energy_id, {
        "brand_id": brand_alien_id, "name": "外星人能量饮",
        "category": "能量饮料", "description": "维生素强化能量饮料",
        "is_active": True,
    })

    # ── SKU ───────────────────────────────────────────────────
    sku1_id = "sku-bt500-001"
    await storage.upsert_object("SKU", sku1_id, {
        "product_id": product_bubble_id,
        "sku_code": "GENKI-BT-500ML",
        "name": "气泡水白桃味 500ml",
        "spec": "500ml", "unit_price": 5.0, "retail_price": 6.0,
        "weight_g": 520, "reorder_threshold": 200, "is_active": True,
        "description": "白桃味无糖气泡水 500ml 单瓶",
    })

    sku2_id = "sku-lime500-001"
    await storage.upsert_object("SKU", sku2_id, {
        "product_id": product_bubble_id,
        "sku_code": "GENKI-LIME-500ML",
        "name": "气泡水青柠味 500ml",
        "spec": "500ml", "unit_price": 5.0, "retail_price": 6.0,
        "weight_g": 520, "reorder_threshold": 150, "is_active": True,
        "description": "青柠味无糖气泡水 500ml 单瓶",
    })

    sku3_id = "sku-alien330-001"
    await storage.upsert_object("SKU", sku3_id, {
        "product_id": product_energy_id,
        "sku_code": "ALIEN-ORIG-330ML",
        "name": "外星人能量饮原味 330ml",
        "spec": "330ml", "unit_price": 7.5, "retail_price": 10.0,
        "weight_g": 360, "reorder_threshold": 100, "is_active": True,
        "description": "外星人原味能量饮料 330ml",
    })

    # ── Channel ───────────────────────────────────────────────
    channel_ka_id = "ch-ka-001"
    await storage.upsert_object("Channel", channel_ka_id, {
        "name": "现代渠道（KA）", "channel_type": "KA",
        "description": "大型商超连锁，大润发/沃尔玛/家乐福",
    })

    channel_cvs_id = "ch-cvs-001"
    await storage.upsert_object("Channel", channel_cvs_id, {
        "name": "便利店", "channel_type": "CVS",
        "description": "全家/7-11/罗森等连锁便利店",
    })

    # ── Distributor ───────────────────────────────────────────
    dist1_id = "dist-sh-001"
    await storage.upsert_object("Distributor", dist1_id, {
        "name": "上海锐进贸易有限公司",
        "level": "city", "region": "华东",
        "province": "上海", "city": "上海",
        "contact_name": "王经理", "contact_phone": "13800138001",
        "credit_limit": 500000.0, "outstanding_amount": 120000.0,
        "status": "active",
    })

    dist2_id = "dist-sz-001"
    await storage.upsert_object("Distributor", dist2_id, {
        "name": "深圳汇达供应链有限公司",
        "level": "city", "region": "华南",
        "province": "广东", "city": "深圳",
        "contact_name": "李总", "contact_phone": "13900139002",
        "credit_limit": 800000.0, "outstanding_amount": 200000.0,
        "status": "active",
    })

    # ── Store ─────────────────────────────────────────────────
    store1_id = "store-sh-001"
    await storage.upsert_object("Store", store1_id, {
        "distributor_id": dist1_id, "channel_id": channel_cvs_id,
        "name": "全家便利店·人民广场店",
        "store_code": "SH-CVS-001",
        "province": "上海", "city": "上海", "district": "黄浦区",
        "address": "人民广场南京东路100号",
        "store_type": "全家", "tier": "A",
        "monthly_sales_target": 8000.0, "is_active": True,
    })

    store2_id = "store-sh-002"
    await storage.upsert_object("Store", store2_id, {
        "distributor_id": dist1_id, "channel_id": channel_ka_id,
        "name": "大润发·上海长宁店",
        "store_code": "SH-KA-001",
        "province": "上海", "city": "上海", "district": "长宁区",
        "address": "中山西路100号",
        "store_type": "大润发", "tier": "A",
        "monthly_sales_target": 50000.0, "is_active": True,
    })

    store3_id = "store-sz-001"
    await storage.upsert_object("Store", store3_id, {
        "distributor_id": dist2_id, "channel_id": channel_cvs_id,
        "name": "7-11·深圳南山科技园店",
        "store_code": "SZ-CVS-001",
        "province": "广东", "city": "深圳", "district": "南山区",
        "address": "科技园南区1栋",
        "store_type": "7-11", "tier": "B",
        "monthly_sales_target": 5000.0, "is_active": True,
    })

    # ── InventoryRecord ───────────────────────────────────────
    await storage.upsert_object("InventoryRecord", str(uuid.uuid4()), {
        "sku_id": sku1_id, "distributor_id": dist1_id,
        "quantity": 500, "available_quantity": 480, "locked_quantity": 20,
    })
    await storage.upsert_object("InventoryRecord", str(uuid.uuid4()), {
        "sku_id": sku2_id, "distributor_id": dist1_id,
        "quantity": 120, "available_quantity": 120, "locked_quantity": 0,
    })
    await storage.upsert_object("InventoryRecord", str(uuid.uuid4()), {
        "sku_id": sku3_id, "distributor_id": dist2_id,
        "quantity": 80, "available_quantity": 80, "locked_quantity": 0,
    })

    # ── ListingTask ───────────────────────────────────────────
    await storage.upsert_object("ListingTask", str(uuid.uuid4()), {
        "sku_id": sku1_id, "store_id": store1_id,
        "distributor_id": dist1_id,
        "target_date": "2025-04-01", "status": "listed",
        "shelf_position": "冷柜第2排", "facings": 4,
    })
    await storage.upsert_object("ListingTask", str(uuid.uuid4()), {
        "sku_id": sku3_id, "store_id": store3_id,
        "distributor_id": dist2_id,
        "target_date": "2025-04-15", "status": "pending",
    })

    # ── Links ─────────────────────────────────────────────────
    await storage.upsert_link("has_sku",      product_bubble_id, sku1_id)
    await storage.upsert_link("has_sku",      product_bubble_id, sku2_id)
    await storage.upsert_link("has_sku",      product_energy_id, sku3_id)
    await storage.upsert_link("contains_store", channel_cvs_id,  store1_id)
    await storage.upsert_link("contains_store", channel_ka_id,   store2_id)
    await storage.upsert_link("contains_store", channel_cvs_id,  store3_id)

    print("✅ 示例数据写入完成")
    return {
        "brands": 2, "products": 2, "skus": 3,
        "distributors": 2, "stores": 3,
    }
