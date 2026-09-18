"""内存演示后端：内置若干“北京库”样例文档（全部 is_demo=True）。

作用：让第 1/4/5 位同学今天就能基于真实 HTTP 契约联调；
切换到 Milvus（北京 Standalone 或全国库）时只需 RETRIEVER_BACKEND=milvus，
接口契约不变。
"""
import itertools
import re
import time
import uuid
from datetime import date
from typing import Optional

from app.retriever.base import BaseRetriever, RetrievedDoc
from app.schemas import EmptyReason, SearchFilters, SearchRequest


def _gen_id() -> str:
    return f"demo-{uuid.uuid4().hex[:12]}"


_DEMO_DOCS: list[RetrievedDoc] = [
    RetrievedDoc(
        doc_id="demo-bj-0001", title="北京市高标准农田建设管理办法（试行）",
        issuer="北京市农业农村局", issued_date="2024-03-15", year=2024,
        region="北京市", doc_type="政策", version="1.0",
        valid_from="2024-04-01", valid_until="2027-03-31",
        authorization="authorized", is_demo=True,
        page=3, clause="第六条",
        content="第六条 高标准农田建设项目应当集中连片、整体推进，"
                "优先在永久基本农田、粮食生产功能区布局。项目区应当完善灌排设施、"
                "机耕道路和农田防护体系，建成后原则上划入永久基本农田实行特殊保护。",
    ),
    RetrievedDoc(
        doc_id="demo-bj-0002", title="北京市支持农村集体经济组织发展若干措施",
        issuer="北京市农业农村局", issued_date="2023-09-01", year=2023,
        region="北京市/海淀区", doc_type="政策", version="1.2",
        valid_from="2023-10-01", valid_until="2026-09-30",
        authorization="authorized", is_demo=True,
        page=1, clause="第二条",
        content="第二条 区级财政应当安排专项资金，支持农村集体经济组织发展"
                "休闲农业、农产品加工和乡村服务业。集体经济组织可通过盘活闲置宅基地和闲置农房，"
                "发展乡村民宿、创意办公等业态，收益分配方案须经成员大会审议。",
    ),
    RetrievedDoc(
        doc_id="demo-bj-0003", title="通州区农村人居环境整治提升行动方案",
        issuer="通州区人民政府", issued_date="2022-05-20", year=2022,
        region="北京市/通州区", doc_type="政策", version="1.0",
        valid_from="2022-06-01", valid_until="2024-05-31",
        authorization="authorized", is_demo=True,
        page=5, clause="三、重点任务（二）",
        content="（二）推进农村厕所革命与生活污水治理。到2023年底，全区农村卫生户厕覆盖率"
                "达到99%以上，生活污水治理率达到75%。建立村庄保洁经费财政补贴与农户缴费相结合的机制。",
    ),
    RetrievedDoc(
        doc_id="demo-bj-0004", title="怀柔区雁栖镇北湾村乡村旅游发展案例",
        issuer="项目调研组", issued_date="2024-06-30", year=2024,
        region="北京市/怀柔区", doc_type="案例", version="1.0",
        valid_from=None, valid_until=None,
        authorization="authorized", is_demo=True,
        page=2, clause=None,
        content="北湾村依托长城文化资源，采用“村集体+专业运营公司+农户”模式发展精品民宿。"
                "实施主体为村集体经济合作社，改造闲置农宅23处，年接待游客4.2万人次，"
                "2023年集体经济收入达186万元，带动村民就业57人。资金来源为市级扶持资金120万元、"
                "社会资本480万元。风险点：淡季入住率不足40%，运营依赖单一运营方。",
    ),
    RetrievedDoc(
        doc_id="demo-bj-0005", title="某村集体经济项目内部评估纪要（未授权）",
        issuer="某区农业农村局", issued_date="2023-11-10", year=2023,
        region="北京市/丰台区", doc_type="案例", version="1.0",
        valid_from=None, valid_until=None,
        authorization="internal", is_demo=True,
        page=None, clause=None,
        content="（内部材料）该项目资金使用存在手续不全问题，暂不宜对外引用。",
    ),
    RetrievedDoc(
        doc_id="demo-bj-0006", title="北京市耕地保护责任目标考核办法（已废止）",
        issuer="北京市人民政府办公厅", issued_date="2018-02-08", year=2018,
        region="北京市", doc_type="政策", version="1.0",
        valid_from="2018-03-01", valid_until="2022-12-31",
        authorization="authorized", is_demo=True,
        page=1, clause="第一条",
        content="第一条 各区人民政府对本行政区域内的耕地保护责任目标履行情况负责，"
                "实行年度自查与期末考核相结合的考核方式。",
    ),
    RetrievedDoc(
        doc_id="demo-bj-0007", title="北京市数字乡村建设行动方案",
        issuer="中共北京市委网络安全和信息化委员会办公室", issued_date="2024-01-12", year=2024,
        region="北京市", doc_type="政策", version="1.0",
        valid_from="2024-02-01", valid_until="2027-01-31",
        authorization="authorized", is_demo=True,
        page=4, clause="第9条",
        content="第9条 推进农村地区数字基础设施提档升级，实现行政村5G网络覆盖率100%。"
                "建设市级农业农村大数据平台，推动涉农数据向区、乡镇两级回流共享，"
                "支持智能感知设备在高效设施农业、动物疫病防控中的应用。",
    ),
    RetrievedDoc(
        doc_id="demo-bj-0008", title="大兴区设施农业项目补贴实施细则",
        issuer="大兴区农业农村局", issued_date="2025-02-01", year=2025,
        region="北京市/大兴区", doc_type="政策", version="1.0",
        valid_from="2025-03-01", valid_until=None,
        authorization="authorized", is_demo=True,
        page=2, clause="第四条",
        content="第四条 对新建、改扩建的日光温室和连栋温室，按实际建设面积给予每亩最高3万元补贴；"
                "配套建设水肥一体化设施的，另按设备投资额的30%给予补贴。申报主体须为区内注册的"
                "农业生产经营主体，补贴资金通过“一卡通”直达账户。",
    ),
]

# 内存库：mock 后端可动态入库，便于演示完整管道
DOCS: list[RetrievedDoc] = list(_DEMO_DOCS)

# ---------------------------------------------------------------------------
# 过滤与打分
# ---------------------------------------------------------------------------

def _passes_filters(doc: RetrievedDoc, f: SearchFilters, today: date) -> tuple[bool, Optional[EmptyReason]]:
    # 租户/组织/村庄
    for key in ("tenant_id", "organization_id", "village_id"):
        want = getattr(f, key)
        if want is not None and doc.get(key) != want:
            return False, EmptyReason.NO_ACCESS
    # 授权（放在内容范围过滤之后判定：地区/时效等范围过滤失败优先归类为 REGION_OR_TIME_MISMATCH）
    # 有效期
    if f.valid_only:
        vf = doc.get("valid_from")
        vu = doc.get("valid_until")
        if vf and date.fromisoformat(vf) > today:
            return False, EmptyReason.REGION_OR_TIME_MISMATCH
        if vu and date.fromisoformat(vu) < today:
            return False, EmptyReason.REGION_OR_TIME_MISMATCH
    # 地区（前缀匹配：["北京市"] 命中 "北京市/海淀区"）
    if f.region:
        if not any(doc.get("region", "").startswith(r) for r in f.region):
            return False, EmptyReason.REGION_OR_TIME_MISMATCH
    # 年份 / 文档类型 / 发布机关
    if f.years and doc.get("year") not in f.years:
        return False, EmptyReason.REGION_OR_TIME_MISMATCH
    if f.doc_types and doc.get("doc_type") not in f.doc_types:
        return False, EmptyReason.REGION_OR_TIME_MISMATCH
    if f.issuers and doc.get("issuer") not in f.issuers:
        return False, EmptyReason.REGION_OR_TIME_MISMATCH
    # 授权（最后判定：范围过滤失败优先归类为 REGION_OR_TIME_MISMATCH）
    if f.authorized_only and doc.get("authorization") != "authorized":
        return False, EmptyReason.NO_ACCESS
    return True, None


_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> set[str]:
    """简单中英混合分词：ASCII 词 + 汉字 2-gram（演示用，Milvus 后端由 embedding/分词器替代）。"""
    tokens: set[str] = set(_TOKEN_RE.findall(text.lower()))
    han = re.sub(r"[^\u4e00-\u9fff]", "", text)
    tokens.update(han[i:i + 2] for i in range(len(han) - 1))
    if han:
        tokens.add(han)
    return tokens


def _score(query: str, doc: RetrievedDoc, mode: str) -> float:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0
    body = doc.get("content", "")
    title = doc.get("title", "")
    body_hits = len(q_tokens & _tokenize(body))
    title_hits = len(q_tokens & _tokenize(title))
    # 标题命中权重更高；hybrid 模式给标题额外加成模拟“混合检索”语义
    raw = (title_hits * 2.0 + body_hits) / (len(q_tokens) * (2.0 if mode != "keyword" else 1.0))
    score = min(1.0, raw)
    if mode == "vector":  # 演示：模拟向量召回的平滑效应
        score = max(score, 0.0 if title_hits == 0 and body_hits == 0 else min(1.0, raw * 0.9 + 0.05))
    return round(score, 4)


class MockRetriever(BaseRetriever):
    name = "mock"

    def search(self, req: SearchRequest) -> tuple[list[RetrievedDoc], Optional[EmptyReason]]:
        today = date.today()
        reasons: list[Optional[EmptyReason]] = []
        candidates: list[tuple[RetrievedDoc, float]] = []
        total_before_rank = 0
        for doc in DOCS:
            ok, why = _passes_filters(doc, req.filters, today)
            if not ok:
                reasons.append(why)
                continue
            s = _score(req.query, doc, req.mode.value)
            total_before_rank += 1
            if s > 0:
                candidates.append((doc, s))
        if not candidates:
            if total_before_rank == 0 and reasons:
                # 全部被过滤掉：取“最严格”的原因（权限 > 地区时效 > 无匹配）
                if any(r == EmptyReason.NO_ACCESS for r in reasons):
                    return [], EmptyReason.NO_ACCESS
                return [], EmptyReason.REGION_OR_TIME_MISMATCH
            return [], EmptyReason.NO_MATCH
        candidates.sort(key=lambda x: x[1], reverse=True)
        top = candidates[: req.top_k]
        if req.filters.min_score > 0 and top[0][1] < req.filters.min_score:
            return [], EmptyReason.NO_RELIABLE_BASIS
        return [doc | {"score": s} for doc, s in top], None

    def add(self, item) -> RetrievedDoc:
        doc = RetrievedDoc(
            item.model_dump() | {"doc_id": _gen_id(), "year": int(item.issued_date[:4])}
        )
        DOCS.append(doc)
        return doc

    def health(self) -> dict:
        return {"backend": "mock", "docs": len(DOCS), "ok": True}

