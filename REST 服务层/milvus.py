"""Milvus 后端（北京库 / 未来全国库通用）。

接入说明（把北京库接进本服务的唯一需要动手的文件）：
1. pip install pymilvus
2. 在下面 implement_here 标注处填入你已有的 embedding 函数；
3. 若你的集合字段名与 app/schemas.Citation 不一致，改 _FIELD_MAP 即可；
4. .env 设 RETRIEVER_BACKEND=milvus、MILVUS_HOST/PORT、MILVUS_COLLECTION，重启即切换。

重要原则（任务文档 5.2 第 9 款）：租户/组织/村庄/授权/地区/时效/版本过滤
全部写入 Milvus search 的 expr（向量召回前生效），而不是取回后过滤。
"""
import logging
from datetime import date
from typing import Optional

from app.config import settings
from app.errors import BackendUnavailable
from app.retriever.base import BaseRetriever, RetrievedDoc
from app.schemas import EmptyReason, SearchFilters, SearchRequest

logger = logging.getLogger("milvus")

# 你的 Milvus collection 字段名 -> 内部字段名（不一致时在这里改）
_FIELD_MAP = {
    "doc_id": "doc_id", "title": "title", "issuer": "issuer",
    "issued_date": "issued_date", "year": "year", "region": "region",
    "doc_type": "doc_type", "content": "content", "page": "page",
    "clause": "clause", "source_url": "source_url", "version": "version",
    "valid_from": "valid_from", "valid_until": "valid_until",
    "authorization": "authorization", "tenant_id": "tenant_id",
    "organization_id": "organization_id", "village_id": "village_id",
}


def _build_expr(f: SearchFilters, today: str) -> str:
    """把过滤条件翻译为 Milvus boolean expr（检索前过滤）。"""
    conds: list[str] = []
    if f.tenant_id:
        conds.append(f'tenant_id == "{f.tenant_id}"')
    if f.organization_id:
        conds.append(f'organization_id == "{f.organization_id}"')
    if f.village_id:
        conds.append(f'village_id == "{f.village_id}"')
    if f.authorized_only:
        conds.append('authorization == "authorized"')
    if f.valid_only:
        conds.append(f'(valid_until == "" or valid_until == null or valid_until >= "{today}")')
        conds.append(f'(valid_from == "" or valid_from == null or valid_from <= "{today}")')
    if f.region:
        # 前缀匹配：北京库/全国库统一按 “省/区县” 层级命名
        region_conds = [f'region like "{r}%"' for r in f.region]
        conds.append("(" + " or ".join(region_conds) + ")")
    if f.years:
        conds.append(f"year in {f.years}")
    if f.doc_types:
        quoted = ", ".join(f'"{d}"' for d in f.doc_types)
        conds.append(f"doc_type in [{quoted}]")
    if f.issuers:
        quoted = ", ".join(f'"{i}"' for i in f.issuers)
        conds.append(f"issuer in [{quoted}]")
    return " and ".join(conds) if conds else ""


class MilvusRetriever(BaseRetriever):
    name = "milvus"

    def __init__(self):
        self._client = None

    def _connect(self):
        if self._client is not None:
            return self._client
        try:
            from pymilvus import MilvusClient  # 延迟导入：mock 模式无需安装 pymilvus
        except ImportError as e:
            raise BackendUnavailable("服务端未安装 pymilvus，无法连接 Milvus",
                                     code="RETRIEVER_UNAVAILABLE", status_code=503) from e
        try:
            self._client = MilvusClient(uri=f"http://{settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
            self._client.describe_collection(settings.MILVUS_COLLECTION)  # 探活
        except Exception as e:
            self._client = None
            raise BackendUnavailable(
                f"无法连接 Milvus ({settings.MILVUS_HOST}:{settings.MILVUS_PORT})，请检查 Standalone 是否启动",
                details={"error": str(e)}) from e
        return self._client

    # ---- implement_here：把北京库已有的 embedding 函数贴进来 ----
    def _embed(self, text: str) -> list[float]:
        """TODO: 替换为你北京库实际使用的 embedding 调用，返回长度 EMBEDDING_DIM 的向量。"""
        raise BackendUnavailable(
            "Milvus 后端尚未接入 embedding 函数（app/retriever/milvus.py::_embed）",
            code="EMBEDDING_NOT_CONFIGURED", status_code=503)

    # ------------------------------------------------------------

    def search(self, req: SearchRequest) -> tuple[list[RetrievedDoc], Optional[EmptyReason]]:
        client = self._connect()
        today = date.today().isoformat()
        try:
            res = client.search(
                collection_name=settings.MILVUS_COLLECTION,
                data=[self._embed(req.query)],
                limit=req.top_k,
                output_fields=list(_FIELD_MAP.keys()),
                filter=_build_expr(req.filters, today),   # 向量召回前过滤
                search_params={"metric_type": "IP"},      # 按你北京库的实际 metric 调整
            )
        except BackendUnavailable:
            raise
        except Exception as e:
            raise BackendUnavailable(f"Milvus 检索失败: {e}") from e

        hits = res[0] if res else []
        docs: list[RetrievedDoc] = []
        for rank, h in enumerate(hits, start=1):
            raw = h.get("entity", {})
            doc = RetrievedDoc(
                {_FIELD_MAP.get(k, k): v for k, v in raw.items()}
                | {"score": float(h.get("distance", 0.0)), "rank": rank}
            )
            if doc["score"] >= req.filters.min_score:
                docs.append(doc)
        if not docs:
            # 粗略区分：过滤条件命中数为 0 视为地区/时效或权限问题，由调用方按 filters 判断
            return [], (EmptyReason.NO_RELIABLE_BASIS if req.filters.min_score > 0 else EmptyReason.NO_MATCH)
        return docs, None

    def health(self) -> dict:
        try:
            self._connect()
            return {"backend": "milvus",
                    "collection": settings.MILVUS_COLLECTION,
                    "ok": True}
        except BackendUnavailable as e:
            return {"backend": "milvus", "ok": False, "error": e.message}
