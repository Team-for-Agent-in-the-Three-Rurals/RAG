# Milvus 部署：路线 B（独立服务器）与路线 C（Notebook 内直跑）

适用对象：Notebook `2609151541024683`（华东一区【昆山】，异构加速卡 AI ×1 卡）
现状：Notebook 内无 Milvus 进程、无 Docker/K8s，`127.0.0.1:19530` Connection refused；L20 实例（012组）弃用。
排除项：Milvus Lite（路线 A）不采用。

---

## 路线 B：同 VPC 独立 Milvus 服务器（正式方案）

### 原理
在一台真正的 Linux 云服务器上用 Docker Compose 起 Milvus Standalone（etcd + MinIO + milvus-standalone 三个容器），Notebook 通过同 VPC 私网 IP 连接 19530。数据库与 Notebook 解耦，Notebook 关机、释放都不影响数据。

### 需要向平台/负责人申请的资源

| 项 | 要求 |
|---|---|
| 位置 | 华东一区【昆山】，与 Notebook 同 VPC |
| 规格 | Ubuntu 22.04，4 vCPU / 16 GiB（32 GiB 更稳）/ **200 GiB 以上 SSD**（全国库按 500 GiB 规划） |
| 网络 | 入方向仅允许 Notebook 私网 IP 访问 TCP `19530`；`9091` 只做本机健康检查，不对公网开放 |
| 软件 | Docker Compose V2 |
| 认证 | MinIO 随机用户名 + ≥16 位密码（写入 `.env`，chmod 600） |

### 服务器端部署步骤

```bash
mkdir -p /opt/rag-milvus && cd /opt/rag-milvus
# 上传项目中的 docker-compose.yml 和 .env.example 到当前目录
cp .env.example .env            # 编辑：替换随机 MinIO 用户名和至少16位密码
chmod 600 .env
docker compose config --quiet   # 语法检查
docker compose up -d
docker compose ps               # 三个服务均需 healthy
curl --fail http://127.0.0.1:9091/healthz
```

版本固定在 Milvus `v2.5.27`，与项目 `pymilvus>=2.5,<3` 同主版本，符合 `BEIJING_FULL_INGEST_GPU_PLAN.md` 的约定；升级前必须备份并重新验收。

### Notebook 侧接入

```bash
unset RAG_MILVUS_URI
export MILVUS_HOST="<独立 Milvus 私网 IP>"
export MILVUS_PORT="19530"
python verify_milvus.py
```

注意：`RAG_MILVUS_URI` 不清掉的话会继续指向本地文件库，务必 unset。

### 验收节奏（两阶段）

1. 冒烟：`policy_chunks_bge_m3_beijing_smoke100`（100 篇），`verify_milvus.py` + 20 问评测达标。
2. 全量：`policy_chunks_bge_m3_beijing_v1`（6,238 篇 / 约 18.7 万 chunk），完成后再把应用的 `RAG_COLLECTION_NAME` 切过去。

### 优缺点

- 优点：正式口径；HNSW 索引；容量可扩到全国 1,177 万 chunk；数据不随 Notebook 释放而消失；成员 1 / 成员 5 也能直接连库联调。
- 成本：依赖平台审批和服务器费用；多一台机器要运维（备份、安全组、`.env` 保管）。
- 风险：审批慢、同 VPC 网络策略不通时需要平台侧配合。

---

## 路线 C：Notebook 内直接运行 Milvus 二进制（临时自给方案）

### 原理
Milvus 从 v2.6 起提供官方 deb/rpm 安装包，内含 embedded etcd，**不需要 Docker**。容器里通常没有 systemd，因此不注册服务，直接以进程方式运行 `milvus run standalone`，监听 127.0.0.1:19530，本机连接。

### 第 0 步：前置检查（必做）

```bash
whoami && uname -m && head -2 /etc/os-release   # 期望 root、x86_64、Ubuntu/Debian
free -g                                          # 内存需 ≥ 8GiB 空余
df -h / /var/lib/milvus                          # 系统盘若只有 50GiB，只够北京库
```

同时确认 GPU 可用于 embedding：

```bash
nvidia-smi
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
export RAG_EMBEDDING_DEVICE=cuda
```

⚠️ 「异构加速卡 AI」不一定是 NVIDIA 卡。若 `nvidia-smi` 不存在或 `torch.cuda.is_available()` 为 False，说明这张卡不是标准 CUDA 卡，BGE-M3 推理要另行解决，先停下来报给负责人。

### 第 1 步：下载安装包

```bash
wget https://github.com/milvus-io/milvus/releases/download/v2.6.22/milvus_2.6.22-1_amd64.deb
```

若 Notebook 直连 GitHub 慢或被限流：在本地 Mac 下载后，用「计算服务」客户端的**文件上传**传到 `/public/home/.../RAG/`，再在 Notebook 里取。

### 第 2 步：安装并手动启动

```bash
apt install -y ./milvus_2.6.22-1_amd64.deb       # 或 dpkg -x 解包到自定义目录
export LD_LIBRARY_PATH=/usr/lib/milvus:$LD_LIBRARY_PATH
nohup /usr/bin/milvus run standalone > ~/milvus_standalone.log 2>&1 &
```

（用 dpkg -x 解包时，改为 `<解包目录>/bin/milvus run standalone`，并把 `LD_LIBRARY_PATH` 指向解包目录的 lib。）

### 第 3 步：验证

```bash
curl -s http://127.0.0.1:9091/healthz
ss -lntp | grep 19530
python verify_milvus.py
```

### 第 4 步：数据目录指向持久化空间

编辑 `/etc/milvus/configs/milvus.yaml`，把 `localStorage.path`（默认 `/var/lib/milvus/data`）改到持久化挂载目录，避免 Notebook 系统盘被占满或释放时丢数据。

### 开机恢复脚本（关机/重启后必须重跑）

Milvus 进程不会跨关机存活，数据在盘上但服务要手动拉起：

```bash
cat > ~/start_milvus.sh <<'EOF'
export LD_LIBRARY_PATH=/usr/lib/milvus:$LD_LIBRARY_PATH
pgrep -f "milvus run standalone" >/dev/null || nohup /usr/bin/milvus run standalone > ~/milvus_standalone.log 2>&1 &
sleep 20 && curl -s http://127.0.0.1:9091/healthz
EOF
chmod +x ~/start_milvus.sh
```

### 版本兼容提醒（重要）

- 路线 C 的服务端是 **2.6.x**，与你们既定的 2.5.27 不同主版本。`pymilvus 2.5` 客户端连 2.6 服务端一般可用，但**必须先在独立测试 collection 上完整跑一遍入库 + 20 问评测 + 过滤验证**，全部通过后才能当正式库。
- 2.5 没有 deb 包，若 2.6 兼容性验证失败，路线 C 走不通，只能回路线 B。
- 2.6 起消息队列由 RocksMQ 换为 Woodpecker（embedded etcd 保留），不影响客户端代码。

### 优缺点

- 优点：不等平台审批，今天就能跑通全链路；Milvus 与 embedding 同机，无网络开销。
- 缺点：与 embedding 进程抢 CPU/内存；受系统盘容量限制（北京库可以，全国库不行）；每次关机要手动重启进程；Notebook 一旦释放，库和数据一起消失；其他人（成员 1/5）连不进来。

---

## 两条路线对比

| 维度 | B 独立服务器 | C Notebook 直跑 |
|---|---|---|
| 依赖平台审批 | 是 | 否，立即可做 |
| Milvus 版本 | 2.5.27（与计划一致） | 2.6.x（需回归验证） |
| 容量 | 200 GiB+，可扩到全国 | 受系统盘限制，仅够北京 |
| 全国 1,177 万 chunk | 可以 | 不行 |
| Notebook 关机/释放 | 数据不受影响 | 进程要重启；释放即丢 |
| 他人接入 | 成员 1/5 可连 | 仅本机 |
| 资源争抢 | 无 | 与 BGE-M3 推理抢内存 |

## 建议节奏

1. **今天**：在 Notebook 上先跑第 0 步前置检查（尤其是 GPU/CUDA 验证），并把路线 B 的资源需求发给负责人。
2. **审批期间**：走路线 C 把北京全量 6,238 篇先入库冒烟，用测试 collection，不覆盖任何正式库。
3. **服务器到位后**：路线 B 部署 → 冒烟 100 篇 → 全量重建 → `RAG_COLLECTION_NAME` 切换；把路线 C 的数据仅作对比参考，不做迁移依赖。
4. 全国全量只允许在路线 B（200 GiB+）上执行。
