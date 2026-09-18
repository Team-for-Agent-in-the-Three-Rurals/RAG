"""接口测试：覆盖任务文档验收点（地区/时效过滤、授权、空结果分类、健康检查）。

运行：pytest tests/ -v
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["retriever"]["backend"] == "mock"


def test_search_hybrid_basic():
    r = client.post("/api/v1/search", json={
        "query": "高标准农田建设项目如何布局？",
        "top_k": 3,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    top = body["results"][0]
    # 引用输出规范字段齐全
    for key in ("title", "issuer", "issued_date", "source_id", "snippet", "page", "clause"):
        assert key in top
    assert top["is_demo"] is True  # 模拟数据必须明确标注


def test_region_filter_prefix_match():
    # “北京市”应命中 “北京市/海淀区” 下的文档
    r = client.post("/api/v1/search", json={
        "query": "集体经济组织 盘活闲置宅基地",
        "filters": {"region": ["北京市/海淀区"], "doc_types": ["政策"]},
    })
    assert r.status_code == 200
    results = r.json()["results"]
    assert results, "海淀区前缀过滤不应为空"
    assert all(x["region"].startswith("北京市/海淀区") for x in results)


def test_expired_policy_excluded_when_valid_only():
    # demo-bj-0006 已于 2022-12-31 失效
    r = client.post("/api/v1/search", json={
        "query": "耕地保护责任目标考核",
        "filters": {"valid_only": True},
    })
    body = r.json()
    assert all(x["source_id"] != "demo-bj-0006" for x in body["results"])


def test_unauthorized_doc_excluded():
    # demo-bj-0005 authorization=internal，authorized_only=True 时必须被过滤（检索前）
    r = client.post("/api/v1/search", json={
        "query": "项目资金使用 手续不全 内部评估",
        "filters": {"authorized_only": True},
    })
    body = r.json()
    assert all(x["authorization"] == "authorized" for x in body["results"])
    # 显式关闭授权过滤即可命中
    r2 = client.post("/api/v1/search", json={
        "query": "项目资金使用 手续不全 内部评估",
        "filters": {"authorized_only": False},
    })
    assert any(x["source_id"] == "demo-bj-0005" for x in r2.json()["results"])


def test_empty_result_classification_region_mismatch():
    r = client.post("/api/v1/search", json={
        "query": "高标准农田",
        "filters": {"region": ["上海市"]},
    })
    body = r.json()
    assert body["total"] == 0
    assert body["empty_reason"] == "REGION_OR_TIME_MISMATCH"
    assert body["message"]


def test_empty_result_classification_no_access():
    r = client.post("/api/v1/search", json={
        "query": "集体经济 补贴",
        "filters": {"tenant_id": "tenant-x"},
    })
    body = r.json()
    assert body["total"] == 0
    assert body["empty_reason"] == "NO_ACCESS"


def test_min_score_no_reliable_basis():
    r = client.post("/api/v1/search", json={
        "query": "量子计算机在农村的应用",
        "filters": {"min_score": 0.9},
    })
    body = r.json()
    assert body["total"] == 0
    assert body["empty_reason"] in ("NO_RELIABLE_BASIS", "NO_MATCH")


def test_keyword_mode_exact_lookup():
    r = client.post("/api/v1/search", json={
        "query": "数字乡村建设行动方案",
        "mode": "keyword",
        "top_k": 2,
    })
    body = r.json()
    assert body["total"] >= 1
    assert body["results"][0]["title"] == "北京市数字乡村建设行动方案"


def test_document_ingest_roundtrip():
    r = client.post("/api/v1/documents", json={
        "title": "测试区县联调文档", "issuer": "测试县农业农村局",
        "issued_date": "2026-01-01", "region": "北京市/测试区",
        "doc_type": "政策", "content": "测试区县联调专用内容：设施农业补贴政策条款。",
        "is_demo": True,
    })
    assert r.status_code == 201
    doc_id = r.json()["doc_id"]
    r2 = client.post("/api/v1/search", json={
        "query": "设施农业补贴政策条款", "filters": {"region": ["北京市/测试区"]}})
    assert any(x["source_id"] == doc_id for x in r2.json()["results"])


def test_validation_error_shape():
    r = client.post("/api/v1/search", json={"query": ""})
    assert r.status_code == 422
