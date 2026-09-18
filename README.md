# RAG 检索 REST 服务（第 2 位同学 · 阶段 B/C 接口层）

**一句话**：把 RAG 检索能力用 HTTP 暴露出来，让第 1（LangGraph）、4（相似村对标）、5（前端）位同学**不连 Milvus、不知道库结构**也能对接调试。平台反代挡 gRPC 的现状下，联调统一走本服务。

- 当前内置 **mock 后端（北京库演示数据，全部标注 `is_demo=true`）**——今天就可用；
- 切换到 Milvus 北京 Standalone / 全国库：**只改 3 个环境变量 + 1 个函数**（见下文），接口契约完全不变。

## 启动

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# 自测
pytest tests/ -v
# 交互式文档（Swagger）
open http://127.0.0.1:8000/docs
```

Docker：见文末。

## 接口

### `GET /healthz` — 健康检查

```json
{"ok": true, "service": "rag-rest-service", "version": "0.1.0",
 "retriever": {"backend": "mock", "docs": 8, "ok": true}}
```

### `POST /api/v1/search` — 检索（核心接口）

请求：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "集体经济 盘活闲置宅基地 发展乡村民宿",
    "top_k": 5,
    "mode": "hybrid",
    "filters": {
      "region": ["北京市"],
      "years": [2023, 2024, 2025],
      "doc_types": ["政策", "案例"],
      "authorized_only": true,
      "valid_only": true,
      "min_score": 0.05
    }
  }'
```

| 字段 | 说明 |
|---|---|
| `query` | 用户问题/检索词 |
| `top_k` | 返回条数（默认 5，上限 50） |
| `mode` | `hybrid`（默认）/ `vector` / `keyword`（政策标题、条款号等精确问题用 keyword） |
| `filters.tenant_id / organization_id / village_id` | 租户/组织/村庄上下文（**检索前过滤**，不是检索后隐藏） |
| `filters.region` | 地区，**前缀匹配**：`["北京市"]` 命中 `北京市/海淀区`；全国库同规则 |
| `filters.years` | 发布年份 |
| `filters.doc_types / issuers` | 文档类型 / 发布机关 |
| `filters.authorized_only` | 只返回已授权材料（默认 true） |
| `filters.valid_only` | 只返回有效期内的材料（默认 true） |
| `filters.min_score` | 可信阈值，低于它按“无可靠依据”处理 |

响应（每条结果都是**可直接展示的引用**）：

```json
{
  "query": "...",
  "mode": "hybrid",
  "total": 2,
  "results": [
    {"rank": 1,
     "title": "北京市支持农村集体经济组织发展若干措施",
     "issuer": "北京市农业农村局", "issued_date": "2023-09-01", "year": 2023,
     "region": "北京市/海淀区", "doc_type": "政策",
     "source_id": "demo-bj-0002", "source_url": null,
     "page": 1, "clause": "第二条",
     "snippet": "第二条 区级财政应当安排专项资金……",
     "score": 0.6471, "version": "1.2", "valid_until": "2026-09-30",
     "authorization": "authorized", "is_demo": true}
  ],
  "applied_filters": {"region": ["北京市"], "authorized_only": true, "valid_only": true, "min_score": 0.05},
  "empty_reason": null,
  "message": null
}
```

**空结果分类**（`total == 0` 时第 1 位同学的回退节点直接读 `empty_reason`）：

| empty_reason | 含义 | 建议处理 |
|---|---|---|
| `NO_MATCH` | 库中无相关材料 | 回复“知识库中无依据”，禁止模型自由发挥 |
| `NO_RELIABLE_BASIS` | 有候选但低于可信阈值 | 同上，可提示用户放宽条件 |
| `REGION_OR_TIME_MISMATCH` | 地区或时效过滤后无结果 | 提示用户更换地区/年份 |
| `NO_ACCESS` | 权限/授权过滤后无结果 | 提示无权限，走人工审核 |

### `POST /api/v1/documents` — 演示入库（仅 mock 后端）

联调时可现场造数据；正式入库走入库脚本（阶段 B 交付物）。

### 错误码

| HTTP | code | 场景 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 设置了 `API_TOKEN` 但未携带/不匹配 |
| 403 | `PERMISSION_DENIED` | 预留：组织外访问拦截 |
| 422 | `INVALID_PARAMS` | 参数校验失败（query 为空等） |
| 500 | `INTERNAL_ERROR` | 未预期异常 |
| 503 | `RETRIEVER_UNAVAILABLE` / `EMBEDDING_NOT_CONFIGURED` | Milvus 连不上 / 后端未接好 |
| 501 | `NOT_IMPLEMENTED` | 在 milvus 后端调用 mock 专属接口 |

## 其他成员怎么接

- **第 1 位（LangGraph）**：把 `POST /api/v1/search` 注册为 Tool；`empty_reason` 映射到你的异常回退/人工审核节点；建议把用户会话里的租户/组织/村庄上下文原样放进 `filters`。
- **第 4 位（相似村）**：对标案例证据请带 `filters={"doc_types": ["案例"], "region": [...]}`；`snippet + page/clause + source_id` 即对标报告的引用依据。
- **第 5 位（前端）**：`results[].snippet/title/issuer/issued_date/page/clause/source_id` 直接渲染引用卡片；`/healthz` 做探活。

## 切换到 Milvus（北京 Standalone → 全国库）

1. `.env`（复制 `.env.example`）里设：

   ```
   RETRIEVER_BACKEND=milvus
   MILVUS_HOST=<standalone 地址>
   MILVUS_PORT=19530
   MILVUS_COLLECTION=sannong_kb
   EMBEDDING_DIM=1024
   ```

2. 在 `app/retriever/milvus.py::_embed` 填入你北京库现有的 embedding 函数（唯一必须动手的地方）；
3. 若集合字段名不同，改同文件的 `_FIELD_MAP`；
4. 过滤会自动翻译成 Milvus `search(filter=...)` 表达式，**在向量召回前生效**（任务文档 5.2 第 9 款要求），地区用 `region like "北京市%"` 前缀匹配，全国库无需改代码。

> 注意：mock 的打分只是演示排序；Milvus 后端的 `score` 是向量相似度，`min_score` 阈值接入后需用检索测试集重新标定。

## Docker

```bash
docker compose up --build   # 服务跑在 8000，不暴露 Milvus 端口
```

## 交付对照（任务文档）

| 文档要求 | 本服务覆盖 |
|---|---|
| 阶段 B：检索与重排模块、过滤策略 | `mode=hybrid` 检索路径 + 检索前过滤（mock/Milvus 双实现） |
| 阶段 C：引用模块、无依据处理 | `Citation` 输出规范 + `empty_reason` 四分类 |
| 5.2-3：Milvus 元数据设计 | `SearchFilters`/`DocumentIn` 字段即元数据字典（tenant/组织/村庄/授权/有效期/版本/地区/年份/发布机关） |
| 5.2-9：召回前过滤 | `milvus.py::_build_expr` + mock `_passes_filters` |
| 必交：接口说明、测试样例 | 本 README + `tests/`（11 个用例） |
