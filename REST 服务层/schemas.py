"""接口契约（Pydantic v2）。

设计原则（对应任务文档 5.2 条第 3/6/7/9 款）：
- 过滤条件在“检索前”生效，即 filters 直接进入检索层，而不是检索后由前端隐藏；
- 引用输出包含：文件标题、发布机关、发布时间、来源标识/链接、页码或条款、片段内容；
- 明确区分 “无可靠依据 / 地区或时效不匹配 / 无访问权限” 三类空结果。
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SearchMode(str, Enum):
    hybrid = "hybrid"      # 向量 + 关键词混合（默认）
    vector = "vector"      # 仅向量
    keyword = "keyword"    # 仅关键词（政策标题、条款号等精确问题）


class EmptyReason(str, Enum):
    NO_MATCH = "NO_MATCH"                          # 库中无相关材料
    NO_RELIABLE_BASIS = "NO_RELIABLE_BASIS"        # 有候选但得分低于可信阈值
    REGION_OR_TIME_MISMATCH = "REGION_OR_TIME_MISMATCH"  # 地区或时效过滤后无结果
    NO_ACCESS = "NO_ACCESS"                        # 权限/授权过滤后无结果


class SearchFilters(BaseModel):
    """检索前过滤条件。全部可选；不传 = 不限。"""
    tenant_id: Optional[str] = None
    organization_id: Optional[str] = None
    village_id: Optional[str] = None
    region: list[str] = Field(default_factory=list, description='支持前缀匹配，如 ["北京市"] 会命中 "北京市/海淀区"')
    years: list[int] = Field(default_factory=list, description="按发布年份过滤，如 [2023, 2024]")
    doc_types: list[str] = Field(default_factory=list, description="如 [\"政策\", \"案例\", \"授权材料\"]")
    issuers: list[str] = Field(default_factory=list, description="发布机关，如 [\"北京市农业农村局\"]")
    authorized_only: bool = Field(default=True, description="只返回授权状态为 authorized 的文档")
    valid_only: bool = Field(default=True, description="只返回在有效期内的文档（按 valid_from/valid_until 判断）")
    min_score: float = Field(default=0.05, ge=0.0, le=1.0, description="可信阈值，低于该值视为“无可靠依据”")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, description="用户问题或检索词")
    top_k: int = Field(default=5, ge=1, le=50)
    mode: SearchMode = SearchMode.hybrid
    filters: SearchFilters = Field(default_factory=SearchFilters)


class Citation(BaseModel):
    """引用输出规范（任务文档 5.2 第 6 款）。"""
    rank: int
    title: str
    issuer: str = Field(description="发布机关")
    issued_date: str = Field(description="发布时间，YYYY-MM-DD 或 YYYY-MM")
    year: int
    region: str
    doc_type: str
    source_id: str = Field(description="文件唯一标识（入库时生成）")
    source_url: Optional[str] = None
    page: Optional[int] = Field(default=None, description="页码（可定位时返回）")
    clause: Optional[str] = Field(default=None, description="条款号，如 第十二条 / 3.2")
    snippet: str = Field(description="命中片段原文")
    score: float
    version: str = "1.0"
    valid_until: Optional[str] = None
    authorization: str = Field(description="authorized | internal | confidential")
    is_demo: bool = Field(default=False, description="是否为模拟数据（正式数据必须为 false）")


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    total: int = Field(description="返回的引用条数")
    results: list[Citation] = []
    applied_filters: dict = Field(default_factory=dict, description="本次实际生效的过滤条件，便于联调排查")
    empty_reason: Optional[EmptyReason] = Field(
        default=None, description="total==0 时空结果的分类原因，供第 1 位同学的路由/回退节点使用")
    message: Optional[str] = Field(default=None, description="给用户可读的提示，如“知识库中未找到相关依据”")


class DocumentIn(BaseModel):
    """mock 后端的入库接口（演示管道用）。Milvus 后端请走你的入库脚本。"""
    title: str
    issuer: str
    issued_date: str
    region: str
    doc_type: str
    content: str = Field(min_length=1)
    page: Optional[int] = None
    clause: Optional[str] = None
    source_url: Optional[str] = None
    version: str = "1.0"
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    authorization: str = "authorized"
    tenant_id: Optional[str] = None
    organization_id: Optional[str] = None
    village_id: Optional[str] = None
    is_demo: bool = True


class DocumentOut(DocumentIn):
    doc_id: str
