# 三农政策 RAG 检索服务 · 对接文档

**交付人**：第 2 位成员（RAG / Milvus / 可信引用）
**面向对象**：第 1 位（LangGraph 主流程）、第 4 位（相似村对标）、第 5 位（前端）
**版本**：v1.0（2026-09-19）
**配合交付**：REST 服务层（阶段 B/C 接口层）

---

## 0. 两种调用方式，先选对

| 你是谁 | 推荐方式 | 说明 |
|---|---|---|
| 第 1 位（LangGraph 主流程） | Python 直连（`rag_adapter.py`） | 已接好，走 `retrieve_policy()`；需要全量 21 字段审核规则时可直接用 `hybrid_search + format_citations` |
| 第 4 位（相似村对标） | HTTP REST | 不用连 Milvus，`POST /api/v1/search` 带 `doc_types=["案例"]` 即可 |
| 第 5 位（前端） | HTTP REST | 引用卡片字段直接渲染，`/healthz` 做探活 |

两种方式**地区/时效过滤语义一致、无结果约定一致**，只是返回字段详略不同（REST 每条结果是 21 字段引用的展示子集）。

---

## 1. 接口地址

### 1.1 HTTP（成员 4 / 5）

| 项 | 值 |
|---|---|
| Base URL | `http://127.0.0.1:8000`（联调本机；部署后替换为服务器地址） |
| 健康检查 | `GET /healthz` |
| 检索接口 | `POST /api/v1/search` |
| 交互式文档 | `http://127.0.0.1:8000/docs`（Swagger，可在线调试） |
| 鉴权 | 未设 `API_TOKEN` 环境变量时免鉴权；设置了则请求头需携带 |

启动方式（服务提供方维护）：

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# 或 docker compose up --build
```

### 1.2 Python 直连（成员 1）

主流程统一入口（已接好，不要自己写 Milvus 查询）：

```python
from rag_adapter import retrieve_policy

citations = retrieve_policy(
    query="大兴区有哪些农业补贴政策？",
    filters={"county": "大兴区"},   # 适配器自动转成 region_code 精确过滤
    top_k=8,
)
```

需要**全量 21 字段**（如做失效政策审核规则）时，直接用底层接口：

```python
from retriever import hybrid_search, format_citations, FilterParams

response = hybrid_search(
    query="大兴区农机购置补贴",
    top_k=5,
    filters=FilterParams(
        region_code="110115",       # 大兴区
        only_valid=True,            # 时效：只要当前有效
        exclude_abolished=True,     # 时效：排除已废止
    ),
)
citations = format_citations(response.results)   # 21 字段引用列表
```

环境变量：`SANONG_RAG_BACKEND=auto`（默认，优先 Milvus、失败回退本地 JSONL）。

---

## 2. 请求参数

### 2.1 REST 请求体

```json
{
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
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `query` | ✅ | 用户问题/检索词，不能为空 |
| `top_k` | — | 返回条数，默认 5，上限 50 |
| `mode` | — | `hybrid`（默认）/ `vector` / `keyword`。文号、条款号等**精确问题用 `keyword`**（如"东政发〔2011〕55号"） |
| `filters.region` | — | **地区过滤，前缀匹配**：`["北京市"]` 命中 `北京市/海淀区`；多地区传列表 |
| `filters.years` | — | 发布年份过滤 |
| `filters.doc_types` | — | 文档类型：`政策` / `案例` |
| `filters.issuers` | — | 发布机关 |
| `filters.tenant_id / organization_id / village_id` | — | 租户/组织/村庄上下文。**检索前过滤**（召回前生效），不是检索后隐藏。第 1 位同学请把会话上下文原样传入 |
| `filters.authorized_only` | — | 只返回已授权材料，默认 `true` |
| `filters.valid_only` | — | **时效过滤**：只返回当前在有效期内（`is_currently_valid == true`）的材料，默认 `true` |
| `filters.min_score` | — | 可信阈值，低于它的候选按"无可靠依据"处理（`NO_RELIABLE_BASIS`） |

### 2.2 时效过滤怎么传（重点）

| 你想要 | REST 传法 | Python 传法 |
|---|---|---|
| 只要当前有效 | `filters.valid_only = true`（默认已开） | `FilterParams(only_valid=True)` |
| 排除已废止 | `filters.authorized_only` 配合授权；废止排除在服务端默认开启 | `FilterParams(exclude_abolished=True)` |
| 放开时效限制 | `filters.valid_only = false` | `FilterParams(only_valid=False, exclude_abolished=False)` |

每条结果自带时效状态字段（`expiry_status`，见 §3），取值：`有效 / 已过期 / 已废止 / 已失效 / 未生效`。前端拿到 `expiry_status != "有效"` 的结果请打"已失效"角标，不要当现行政策展示。

### 2.3 地区过滤怎么传（重点）

- **REST**：`filters.region` 是**前缀匹配**，`["北京市"]` 命中全市含各区，`["北京市/海淀区"]` 只命中海淀。
- **Python 精确到区县**：传 `region_code`（6 位行政区划码），适配器内置北京 16 区映射，也可直接传 `filters={"county": "大兴区"}` 自动转换：

| 区县 | region_code | 区县 | region_code |
|---|---|---|---|
| 东城区 | 110101 | 通州区 | 110112 |
| 西城区 | 110102 | 顺义区 | 110113 |
| 朝阳区 | 110105 | 昌平区 | 110114 |
| 海淀区 | 110108 | 大兴区 | 110115 |
| 丰台区 | 110106 | 怀柔区 | 110116 |
| 石景山区 | 110107 | 平谷区 | 110117 |
| 门头沟区 | 110109 | 密云区 | 110118 |
| 房山区 | 110111 | 延庆区 | 110119 |

- 多区县用 `region_codes=["110115", "110112"]`。
- 用户问题里提到区县时**务必传**，否则会串到其他区县的政策。

---

## 3. 返回结果：21 个引用字段

### 3.1 REST 响应结构

```json
{
  "query": "...",
  "mode": "hybrid",
  "total": 2,
  "results": [ { ...每条为一个可展示引用，字段见 3.3 对照... } ],
  "applied_filters": {"region": ["北京市"], "valid_only": true, "min_score": 0.05},
  "empty_reason": null,
  "message": null
}
```

### 3.2 21 个引用字段字典（`format_citations` 输出，Python 直连返回全量）

| # | 字段 | 类型 | 含义 | 示例 |
|---|---|---|---|---|
| 1 | `title` | str | 政策标题 | 北京市支持农村集体经济组织发展若干措施 |
| 2 | `doc_id` | str | 政策编码（同一政策多个片段时相同） | bj-2023-0002 |
| 3 | `publish_org` | str | 发布机关 | 北京市农业农村局 |
| 4 | `publish_date` | str | 发布日期 `YYYY-MM-DD` | 2023-09-01 |
| 5 | `doc_number` | str | 文号，精确检索的主键依据 | 东政发〔2011〕55号 |
| 6 | `source_url` | str | 原文链接，可能为 `null` | https://… |
| 7 | `chunk_id` | str | 政策片段唯一编码（引用去重/回查用） | 64 位以内字符串 |
| 8 | `section_title` | str | 所属章节/条款标题 | 第二条 资金支持 |
| 9 | `content` | str | **原文片段，≤500 字**（超长自动在句末截断）。不是全文 | 第二条 区级财政应当安排专项资金…… |
| 10 | `county` | str | 区县 | 大兴区 |
| 11 | `valid_from` | str | 有效期开始 `YYYY-MM-DD` | 2023-09-01 |
| 12 | `valid_to` | str | 有效期结束，**空 = 长期有效** | 2026-09-30 |
| 13 | `expiry_status` | str | 时效状态：`有效/已过期/已废止/已失效/未生效` | 有效 |
| 14 | `is_currently_valid` | bool | 当前是否在有效期内（按今天日期计算） | true |
| 15 | `is_abolished` | bool | 是否已废止 | false |
| 16 | `doc_status` | str | 文档状态：`有效/废止/失效` | 有效 |
| 17 | `org_level` | str | 发布机关层级：`国家级/市级/区级/区级部门` | 市级 |
| 18 | `policy_level` | str | 同 `org_level`（别名，兼容旧字段名） | 市级 |
| 19 | `target_audience` | str | 适用对象 | 村集体经济组织 |
| 20 | `source_credibility` | int | 来源可信度 1–5（官方源为 5） | 5 |
| 21 | `relevance_score` | float | 相关性得分，**已归一化到 0–1**，混合检索下两路第一名约为 1.0 | 0.6471 |

**分工提示**：

- 第 1 位：用 `is_currently_valid / is_abolished / expiry_status / doc_status / source_credibility` 做审核规则；`relevance_score` 低于阈值走回退节点。
- 第 4 位：`doc_id + chunk_id + section_title + content` 作为对标案例的引用依据。
- 第 5 位：引用卡片渲染 `title / publish_org / publish_date / doc_number / county / source_url / content / expiry_status`。

### 3.3 REST 结果字段 ↔ 引用字段对照

REST 每条 `results[]` 是引用的展示子集，对应关系：

| REST 字段 | 对应引用字段 | 说明 |
|---|---|---|
| `rank` | — | 排序序号，从 1 开始 |
| `title` | `title` | |
| `issuer` | `publish_org` | |
| `issued_date` / `year` | `publish_date` | |
| `region` | `county` 所在行政区划 | `北京市/海淀区` 格式 |
| `doc_type` | `doc_type_normalized` | 政策 / 案例 |
| `source_id` | `doc_id` / `chunk_id` | 演示数据为 `demo-bj-xxxx` |
| `source_url` | `source_url` | 可为 `null` |
| `page` / `clause` | `section_title` | 页码 / 条款号 |
| `snippet` | `content` | ≤500 字片段 |
| `score` | `relevance_score` | |
| `valid_until` | `valid_to` | |
| `version` / `authorization` / `is_demo` | — | 演示后端附加字段；**`is_demo=true` 表示当前是北京库演示数据**，切 Milvus 正式库后消失，前端可忽略或打"演示"标记 |

---

## 4. 无结果时的处理约定

### 4.1 REST：`total == 0` 时读 `empty_reason`（四分类）

| empty_reason | 含义 | 建议处理 |
|---|---|---|
| `NO_MATCH` | 库中无相关材料 | 回复"知识库中无依据"，**禁止模型自由发挥** |
| `NO_RELIABLE_BASIS` | 有候选但低于可信阈值（`min_score`） | 同上；可提示用户换一种问法或放宽 `min_score` |
| `REGION_OR_TIME_MISMATCH` | 地区或时效过滤后无结果 | 提示用户更换地区/年份，或确认是否要含已失效政策 |
| `NO_ACCESS` | 权限/授权过滤后无结果 | 提示无权限，走人工审核节点 |

同时 `message` 会带可直接展示的中文提示（如"⚠️ 暂无结果：知识库中未检索到适用于指定地区（北京市）的可靠材料。"）。

### 4.2 Python 直连：`response.no_result_reason`

无结果时该字段给出原因诊断，取值组合：`地区不匹配`、`时效限制（文档已过期或已废止）`、`无访问权限`、`来源可信度不满足要求`、`知识库中未找到与该问题相关的政策或案例材料`。
可直接调用 `format_no_result_message(response)` 拿到统一文案。

### 4.3 通用红线（三位成员都适用）

1. **无结果 ≠ 报错**：`total == 0` 是正常业务返回，HTTP 仍是 200，按 `empty_reason` 分支处理即可。
2. 无可靠依据时**不允许让大模型凭空回答**——这是全组的质量底线。
3. 建议前端在无结果时展示"已自动排除已废止/过期政策，是否查看历史文件？"的引导。

---

## 5. 错误码（REST）

| HTTP | code | 场景 |
|---|---|---|
| 401 | `UNAUTHORIZED` | 设置了 `API_TOKEN` 但未携带/不匹配 |
| 403 | `PERMISSION_DENIED` | 预留：组织外访问拦截 |
| 422 | `INVALID_PARAMS` | 参数校验失败（query 为空等） |
| 500 | `INTERNAL_ERROR` | 未预期异常 |
| 503 | `RETRIEVER_UNAVAILABLE` / `EMBEDDING_NOT_CONFIGURED` | Milvus 连不上 / 后端未接好 |
| 501 | `NOT_IMPLEMENTED` | 在 milvus 后端调用了 mock 专属接口 |

---

## 6. 最小可运行示例

### 6.1 curl（成员 4：对标案例）

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "村集体经济 盘活闲置宅基地 民宿",
    "top_k": 5,
    "mode": "hybrid",
    "filters": {"doc_types": ["案例"], "region": ["北京市"], "valid_only": true}
  }'
```

### 6.2 Python（成员 1：全量 21 字段 + 审核规则）

```python
from retriever import hybrid_search, format_citations, format_no_result_message, FilterParams

resp = hybrid_search(
    query="大兴区农机购置补贴",
    top_k=5,
    filters=FilterParams(region_code="110115", only_valid=True, exclude_abolished=True),
)
if not resp.results:
    print(format_no_result_message(resp))        # 统一无结果文案
else:
    for c in format_citations(resp.results):     # 21 字段
        if not c["is_currently_valid"] or c["is_abolished"]:
            print("【已失效，需审核】", c["title"], c["expiry_status"])
```

### 6.3 前端（成员 5）

1. 启动时 `GET /healthz` 探活，`ok=true` 再渲染搜索框；
2. 检索后用 `results[].snippet / title / issuer / issued_date / clause / source_id` 渲染引用卡片；
3. `total == 0` 时按 `empty_reason` 显示 §4.1 的提示文案。

---

## 7. 联调注意事项

1. **当前 REST 内置 mock 后端**（北京库演示数据，结果全部 `is_demo=true`），今天就可用；切 Milvus 北京 Standalone / 全国库只改服务端环境变量，**接口契约不变**，成员代码无需改动。
2. 切到 Milvus 后 `score` 为真实向量相似度，`min_score` 阈值需要用检索测试集**重新标定**（mock 的分数仅演示排序）。
3. 单份政策最多返回 2 个片段（`RAG_MAX_CHUNKS_PER_DOCUMENT=2`），Top-K 不会全被同一政策占满。
4. `content/snippet` 一律 ≤500 字，需要全文请拿 `doc_id`/`source_url` 回查原文，不要指望接口吐整篇。
5. 精确问题（含文号 `〔2011〕55号`、`第X条`）建议 `mode="keyword"`，会自动提升关键词检索权重。
6. 权限字段（`tenant_id / organization_id / village_id / authorized_only`）是**召回前过滤**，传了不匹配的值会直接查不到，联调时先确认上下文再怀疑库。
7. 遇到问题先看 `/healthz` 的 `retriever.backend` 和 `ok`，再看响应 `empty_reason / message`，最后找成员 2。
