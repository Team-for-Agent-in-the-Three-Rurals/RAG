"""应用入口：python -m uvicorn app.main:app --reload --port 8000"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.errors import register_handlers
from app.routers.api import router as api_router
from app.retriever import get_retriever

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="三农智能工作台 · RAG 检索服务",
    version="0.1.0",
    description=(
        "第 2 位同学交付的 REST 检索服务（阶段 B/C 接口层）。\n\n"
        "- `POST /api/v1/search`：政策/案例检索，支持混合检索、检索前元数据过滤、可信引用输出；\n"
        "- `GET /healthz`：健康检查（供部署与前端探活）；\n"
        "- `POST /api/v1/documents`：mock 后端演示入库。\n\n"
        "当前后端：**mock（北京库演示数据）**；切换 Milvus：`.env` 设 `RETRIEVER_BACKEND=milvus`。"
    ),
)
register_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/healthz", tags=["ops"], summary="健康检查")
def healthz():
    retriever = get_retriever()
    return {
        "ok": True,
        "service": "rag-rest-service",
        "version": app.version,
        "retriever": retriever.health(),
    }
