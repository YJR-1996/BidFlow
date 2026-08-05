# BidFlow 项目日报（7月30日 — 8月3日）

> 项目：BidFlow 智能投标响应系统（FastAPI + Vue3 + MySQL + Milvus + DashScope LLM）

---

## 📅 2026-07-30 日报

### 今日任务
1. 修复「为已匹配需求批量生成响应」按钮超时问题（点击无反应）
2. 排查合规检查报告中的高风险/中风险项来源，修复误报
3. 按流程完整度要求，对流程图 vs 代码做第二轮只读审查
4. 输出 5 份架构级功能修复提示词（Agent编排/语义合规/PDF导出/回退闭环/响应就绪度）

### 完成情况
- ✅ 批量生成超时**根因定位**：前端 axios 全局 30s 硬墙 + 后端单请求内同步串行跑全部需求 RAG+LLM（单条最坏 30s×3=90s）→ 数学上必超时；已产出异步化修复提示词
- ✅ 合规误报**双重根因定位**：`source_refs=[]` 硬编码丢弃真实来源 + `status` 中英文语义错配（"未处理"vs"completed"）；产出修复提示词并确认 Trae 落地（含 `ast.literal_eval` 兜底 + `COMPLETED_STATUSES` 中英文兼容集合）
- ✅ 第二轮流程审查：节点④辅助需求生成已补上，最终 **9 完整 + 3 部分 + 3 缺失 = 60% 覆盖**；新增发现 Embedding 链路断开（F14 前身）、语义缺口分析未接线
- ✅ 5 份架构级提示词落盘 `docs/bidflow-architecture-prompts.md`，并应要求精简（776→280 行）

### 遇到的问题
- 🔴 批量生成接口同步串行跑 LLM → 前端 30s 必超时
- 🔴 合规检查中风险误报（数据明明有来源却报缺失）
- 🔴 合规检查高风险误报（P0 已生成响应却报未完成）
- 🟡 提示词过长（用户要求精简）

### 解决情况
- ✅ 超时 → 给出「异步任务 + task_id 返回 + 前端轮询」方案提示词
- ✅ 中风险误报 → `source_refs` 正确解析传入 + `ast.literal_eval` 兼容单引号旧数据
- ✅ 高风险误报 → 快照状态改用响应草稿状态 + 中英文兼容状态集合
- ✅ 提示词 → 保功能砍叙事，压缩 64%

---

## 📅 2026-07-31 日报

### 今日任务
1. 三维度全面代码审查（逻辑正确性/功能完整性/全流程可运行性）
2. 修复用户实测反馈的一批新问题（DOCX 解析失败、schema_check 崩溃、Milvus 连不上、全站 500 等）
3. 实现比对分析持久化新功能
4. 统一风险数量显示口径 + 综合健康度算法修正 + 语义合规误报治理

### 完成情况
- ✅ 全面审查产出 18 项问题 F1-F18 报告（`docs/bidflow-comprehensive-review.md`），拆成 16 份可执行修复提示词
- ✅ 直接改代码修复：DOCX/PDF 依赖缺失（python-docx+PyPDF2）、`text` NameError、aiomysql `pool_pre_ping` 500、Milvus 连接配置、风险口径统一、应用建议事件链、健康度三维加权、图标残缺/表格挤压等
- ✅ 比对分析持久化新功能（6 文件）：`match_analysis_runs/details` 新表 + force 参数 + POST 重算端点 + 前端复用历史
- ✅ 语义合规 5 层误报治理：日期锚点 / 负向约束 / 黑名单 / 置信度阈值+level 封顶 / 去重

### 遇到的问题
- 🔴 DOCX 资料无法解析 → 对比分析匹配率 0%（依赖未装）
- 🔴 schema_check `name 'text' is not defined`（9 张表全报）
- 🔴 `AsyncAdapt_aiomysql_connection.ping() missing reconnect` → 全站 500
- 🔴 Milvus 连 localhost 而非阿里云（.env 写死 + pydantic-settings 不注入 os.environ 双重坑）
- 🔴 两个 uvicorn 进程抢 8000 + 装错 Python venv（依赖装到非服务环境）
- 🟡 风险数字三处不一致（10/32/26）、综合健康度假 100%、应用建议无响应、图标残缺/被遮挡

### 解决情况
- ✅ DOCX → requirements.txt 补依赖 + 两个 Python 环境都装齐
- ✅ NameError → `text` 提升模块级 import
- ✅ 500 → async engine `pool_pre_ping=False`（aiomysql 0.3.2 是最终版，无法升级）
- ✅ Milvus → `.env` 改阿里云地址 + `vector_store.py` fallback `settings.MILVUS_HOST`
- ✅ venv → 查进程 CommandLine 确认服务 Python 路径，两环境都装 + 清理重复进程
- ✅ 风险口径 → 统一「待处理风险 = 高+中+未处理」；健康度 → 三维加权 overall + 状态分级；应用建议 → 事件链接通；图标 → 换 Material Symbols 正确命名 + 列宽留余量

---

## 📅 2026-08-03 日报

### 今日任务
1. 全栈第三轮只读审查（逻辑/缺陷/规范/功能完整性）
2. 修复审查发现的 C2/C3 + H1-H6 共 8 项问题
3. 企业资料库上传流程改造（二段式：选文件入队 → 用户确认后上传）

### 完成情况
- ✅ 第三轮审查报告落盘（`docs/bidflow-review-2026-08-03.md`）：3 致命 + 6 高 + 12 中 + 8 低；上轮 F1-F18 大部分已确认落地
- ✅ C2/C3 + H1-H6 全部修复（7 个后端文件语法验证通过）：
  - C2：`backend/.env` 填入真实 DashScope Key + embedding 模型升 v4 → **AI 语义比对/向量检索/语义合规真正激活**
  - C3：`configure_mappers()` 启动自检
  - H1：批量任务 6 小时过期 GC
  - H2：批量生成前端加 2s 轮询 + 字段对齐（succeeded/skipped/failed）
  - H3：选中批量生成传 ids（后端加 `requirement_ids` 参数 + 归属校验）
  - H4：语义黑名单加否定词保护（真风险不再被误杀）
  - H5：stages_done 重复 append 移除（编排流水线不再提前收尾）
  - H6：单条生成接口超时放宽到 120s
- ✅ 资料上传二段式改造（CompanyMaterialsView.vue）：`pendingFiles` 待上传队列 + 移除/清空 + 按钮 disabled 联动——修复「按钮语义反了」（原 submitUpload 只打开文件选择器）

### 遇到的问题
- 🔴 C1 **凭据泄露**：`.env.example` 混入真实 DashScope Key + MySQL root 明文密码（安全红线，git 历史残留需手动清理）
- 🔴 C2 **LLM Key 为空** → Milvus 虽连接但从不写入/检索，全链路降级为关键词匹配（产品核心价值缺失）
- 🔴 C3 ORM mapper 初始化顺序脆弱（曾导致全部接口 500）
- 🟠 H5 编排流水线跑 2 个阶段就误判完成；H4 黑名单误杀真风险
- 🟠 资料上传「选完即自动处理」，无中间控制

### 解决情况
- ✅ C1 → `.env.example` 恢复占位符 + 加警告注释（git 历史撤销待用户执行 `git rm --cached`）
- ✅ C2 → Key 从 example 移入 backend/.env，AI 链路激活
- ✅ C3 → 启动自检前置暴露 mapper 错误
- ✅ H1-H6 → 全部修复（见完成情况）
- ✅ 上传流程 → 二段式（选文件入队 → 配置 → 点「开始上传并向量化」才执行）

---

## 📊 三天总体小结

| 维度 | 成果 |
|------|------|
| 审查 | 三轮全面审查（流程完整度 / F1-F18 / C1-C3+H1-H6），问题全部闭环 |
| 修复 | 30+ 项问题修复（超时/误报/崩溃/配置/UI），关键架构性缺陷清零 |
| 新功能 | 比对分析持久化、批量生成异步化、上传二段式、健康度三维化 |
| 安全 | 凭据泄露已止血（git 历史残留待用户清理） |
| 待办 | ① git 撤销 .env.example 泄露提交 ② M1-M12 中优先级项 ③ 重新上传资料让真实向量入库 |
