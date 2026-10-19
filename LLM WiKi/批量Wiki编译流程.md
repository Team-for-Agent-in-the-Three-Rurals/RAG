# 已有整篇政策 → 批量 Wiki（离线正式流程 v1）

此流程将已有全文、逐字段原文选段和旧结论统一编译为不可覆盖的待复核版本。
第一批为2026-10-19盘点的10份材料。运行只依赖Python标准库，不调用模型、网络或生产接口。
它是可复跑的批量加工流程，尚不包含任意新政策的模型语义抽取、人工审批或生产发布。

## 输入契约与复用

- 项目根下 `outputs/policy_material_inventory_20261019_v2/full_text_first_batch.jsonl`：10项整篇材料；拒绝重复ID、片段输入、缺失或不匹配的规格。
- `batch_policy_specs.json`：按文档ID配置专题与字段选段，支持唯一原文 `quote` 或唯一 `start` 加后续 `stop`；`to_end`须显式声明。缺锚点、多义锚点和顺序错误立即失败，不静默生成空字段。
- `sources.json`、`knowledge.json`：复用2份国家快照和4条已有结论，连同县区范围依据重新定位。
- `local_wiki_drafts_20261018_v2/claims.json`：复用8份地方档案的13条结论，逐条复核正文哈希、原文偏移和既有真实chunk链。
- 复用`EvidenceStore`验证档案gzip、解压文本和公开chunk导出指纹，复用`temporal_audit.assess`检查时间条款与库内日期差异。

四类必需字段：适用对象与范围、条件与要求、限制/排除/例外、时间与期限。
可选字段：程序与材料、扶持与标准、责任与管护。
选段保持原文，避免把“符合条件”“不重复”“如有调整”等条件从金额和措施中拆掉。
字段选段尚未经过穷尽性验收，整篇快照必须保留供复核；选段为空不推断原文没有此类内容。
时间另记`time_kind`，区分生效/期限、相对生效、阶段目标、年度工作程序和实施要求。

## 运行

在项目根目录 `/Users/hannah/Documents/RAG`：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 sichuan_policy_wiki/batch_compile.py compile \
  --inventory outputs/policy_material_inventory_20261019_v2/full_text_first_batch.jsonl \
  --specs sichuan_policy_wiki/batch_policy_specs.json \
  --build-root sichuan_policy_wiki/batch_builds \
  --as-of 2026-10-19
```

命令返回`build`实际路径。核验该路径：

```sh
python3 sichuan_policy_wiki/batch_compile.py verify \
  --build <实际构建路径> --check-inputs
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s sichuan_policy_wiki -p 'test_batch_compile.py' -v
```

相同内容复跑会先核验并复用原版本；版本由输入、选段规格、复用知识、编译代码和参考时点共同生成。
修改规格或代码后产生新版本，不覆盖旧版。输入原文与盘点哈希不符时先重做盘点，再编译。
这只提供批量流程的版本基础；跨批次受影响内容分析和增量重编译仍属于后续第三步。

## 输出契约

每个`batch_builds/<version>/`包含：

| 路径 | 内容 |
|---|---|
| `sources/*.txt` | 10份逐字文本快照，不从chunk重拼 |
| `bundle.json` | 冻结规格、输入台账、已有知识、字段、引用、时间审计和输入指纹 |
| `wiki/policies/*.md` | 10个政策页；每字段和复用结论有稳定证据锚点 |
| `wiki/topics/*.md` | 专题页；按政策、地区分列，链接到逐条证据 |
| `wiki/regions/*.md` | 温江与蒲江索引；区分国家历史范围关联与本地档案来源关联 |
| `wiki/index.md` | 总入口 |
| `review_queue.json` | 每文档待复核条目及日期冲突 |
| `validation.json` | 机械校验结果及实质核验边界 |
| `manifest.json` | 所有构建产物的SHA-256收据 |
| `build_report.md` | 数量、版本、运行方式和完成范围 |

每条引用包括：来源标题/URL/文号、来源类型、原档案文件与行号/字段、构建快照位置、文本SHA-256、原始Unicode字符区间`[start,end)`、行号、原文摘录和真实chunk映射状态。未映射的国家文档保留`doc_id=null`、`chunk_ids=[]`。

所有本地Markdown链接及证据锚点逐个检查。编译先在临时目录进行，全部输入/摘录/链接校验通过后才封存；失败不会留下可误用的半成品版本。
单独搬运构建目录可用`verify`核对快照、引用、链接和产物指纹；`--check-inputs`还核对原工作区输入是否变化。
指纹是完整性收据，不是来源真实性的独立认证，也不是防恶意重签的数字签名。

## 复核边界与扩批

所有产物为`draft_review_required`，保留`may_answer_current_policy=false`和`production_ready=false`。
机械校验不自动确认摘要语义、附件完整、适用条件穷尽或现行效力。未打开当前官网核验的来源不能标成重新核验通过。
专题关联是已有人工作业的阅读组织方式，不意味着所有文件均为国家试验区的直接配套政策。
当前不修改`knowledge.json`、旧builds、查询节点或生产库，也不自动发布。

扩批步骤：取回入库前整篇文本及来源收据 → 新盘点 → 显式增加字段规格/待审知识 → 编译新版本 → 看逐文待办与错误 → 实质复核。仅有片段或商业转载的记录不进入首批正式文本层。
需要模型自动抽取或批量生成新摘要时，另行确认模型与预算；不得在此离线命令中悄悄启用API。
