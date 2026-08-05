# 修复合规检查误报（source_refs 未传入 + P0 / needs_manual 状态语义错乱）

> 本提示词用于修复一次合规检查（POST `/{project_id}/compliance-check`）产生的两类**误报风险项**：
> 1. 中风险「响应内容缺少企业资料来源」—— 实际已有资料来源却被误报
> 2. 高风险「P0 响应项尚未完成」—— 实际已生成响应却被误报
>
> 同时顺带修正「资料不足，需要人工补充」中风险规则因状态语义错误而永远不触发的问题。
>
> 两个修复点都在同一个快照构建循环（`compliance.py`）和同一个规则引擎（`compliance_checker.py`）内，**必须作为一个整体一次性提交**，不要拆成两次修改，否则会改同一段代码产生冲突。

---

## 一、背景与根因（完整、无需外部推断）

### 1.1 合规检查的数据流（当前实现）

用户点击「合规检查」→ 调用 `backend/app/api/routes/compliance.py` 的 `run_compliance_check`：

- 清除 `compliance_issues` 表旧记录（第 33–36 行）
- 查出项目下全部 `Requirement`（第 39–41 行）
- **对每个 Requirement 构建 `RequirementSnapshot`**（第 47–71 行），这是问题源头
- 把快照交给 `ComplianceChecker.check()`（`backend/app/services/compliance_checker.py` 第 29 行）判定
- 把产出的 `ComplianceIssue` 写入 `compliance_issues` 表（第 78–90 行）

### 1.2 误报根因 A：source_refs 被硬编码为空列表（导致中风险「缺少企业资料来源」误报）

现状代码（`backend/app/api/routes/compliance.py` 第 47–71 行）：

```python
snapshots: list[RequirementSnapshot] = []
for req in requirements:
    resp_content = ""
    if hasattr(req, 'responses') and req.responses:
        for r in req.responses:
            if r.edited_content:
                resp_content = r.edited_content
                break
            if r.ai_content:
                resp_content = r.ai_content
                break
        try:
            src = r.source_refs or ""      # ← 在 for 循环内部，只取了最后一个 r；且是字符串
        except Exception:
            src = ""
    snapshots.append(RequirementSnapshot(
        requirement_id=req.id,
        content=req.content or "",
        priority=req.priority or "P2",
        response_content=resp_content,
        source_refs=[],                    # ← BUG：硬编码空列表，src 变量被完全丢弃
        status=req.status or "pending",     # ← 见根因 B
    ))
```

关键事实：
- `Response.source_refs` 字段定义在 `backend/app/models/response.py` 第 16 行：`source_refs = Column(Text)`（文本列）
- 该字段由 `responses.py` 以 `str(source_dicts)` 写入，形如：
  `'[{"filename": "公司资质证书.pdf", "score": 12.3, "content": "我方具备..."}, ...]'`
  即 **JSON 字符串**（不是 Python 列表）
- 规则引擎 `backend/app/services/compliance_checker.py` 第 38–39 行：
  ```python
  elif not item.source_refs:
      issues.append(... "RESPONSE_SOURCE_MISSING", "medium", "响应内容缺少企业资料来源", ...)
  ```
  因为快照里 `source_refs=[]`，`not item.source_refs` 永远为 `True` → **只要有响应内容，就必然产生一条中风险误报**，即使后端真实存了资料来源。

### 1.3 误报根因 B：状态值语言不一致 + 从不回写（导致高风险「P0 响应项尚未完成」误报）

现状代码（`backend/app/api/routes/compliance.py` 第 70 行）：
```python
status=req.status or "pending",   # 用的是 Requirement.status（需求级状态）
```

- `Requirement.status` 定义在 `backend/app/models/requirement.py` 第 21 行：`status = Column(String(20), default="未处理")`（**中文**默认值）
- 数据库实际存的值是中文 `"未处理"`
- 但规则引擎 `backend/app/services/compliance_checker.py` 第 33 行：
  ```python
  p0_incomplete = item.priority == "P0" and item.status != "completed"
  ```
  拿 `item.status`（中文 `"未处理"`）和英文 `"completed"` 比较 → **永远不相等** → 所有 P0 优先级需求**必然**报「P0 响应项尚未完成」高风险
- 批量生成路径（`backend/app/services/batch_task_service.py` 的 `_process_one`，第 135–236 行）只写入 `BidResponse` 记录（其 `Response.status` 为英文 `pending_review` / `needs_manual` / `draft`），**从不回写 `Requirement.status`**。因此即使用户已经成功批量生成了 P0 需求的应答稿，`Requirement.status` 仍是 `"未处理"`，合规检查照报高风险。

### 1.4 顺带问题：needs_manual 中风险规则永不触发

规则引擎第 40 行：
```python
if item.status == "needs_manual":
    issues.append(... "MANUAL_MATERIAL_REQUIRED", "medium", "资料不足，需要人工补充", ...)
```
该规则期望 `item.status` 是响应草稿状态 `needs_manual`（英文），但 `compliance.py` 传的是 `Requirement.status`（中文 `"未处理"`），所以这条中风险**永远不触发**，逻辑同样是错的。

### 1.5 结论

| 风险项 | 当前行为 | 真实情况 | 性质 |
|--------|---------|---------|------|
| 响应内容缺少企业资料来源（中） | 必报 | 实际可能已有来源 | **误报（代码 Bug）** |
| P0 响应项尚未完成（高） | P0 必报 | 可能已生成响应 | **误报（状态语义错）** |
| 资料不足，需要人工补充（中） | 永不报 | 无资料需求应报 | **漏报（状态语义错）** |

---

## 二、修复目标

1. 合规检查快照要正确携带**响应草稿里的资料来源**（`source_refs`），使「缺少企业资料来源」只在真正缺失时触发。
2. 合规检查判定「完成」应基于**响应草稿的真实状态**（已生成 / 待评审 / 已完成），而非从未被更新的需求级状态；且状态比对要兼容中英文枚举，避免再因语言不一致漏判。
3. 「需要人工补充」中风险要能正确触发（针对 `needs_manual` 响应）。
4. 不改变合规检查对「真正未处理 / 真正缺失资料」需求的原有报警能力——规则只是从「误报」纠正为「准确报」。

---

## 三、约束条件

1. **只改两个文件**：`backend/app/api/routes/compliance.py`（快照构建循环）、`backend/app/services/compliance_checker.py`（规则判定）。
2. **不动**：`Requirement` / `Response` 模型定义、`batch_task_service.py`、数据库表结构（无 migration）、前端代码、任何 API 路径与签名。
3. **不引入新第三方依赖**；`json` 为标准库，若 `compliance.py` 顶部未 `import json` 则补上。
4. `RequirementSnapshot` dataclass（`compliance_checker.py` 第 7–14 行）的字段签名**保持不变**（仍用 `status` 字段，但语义改为「响应草稿状态，兜底需求状态」），不要新增/删除字段，避免影响 `ReportService.build()` 等其他调用方。
5. 向后兼容：修复后 `item.status` 仍可能是中文（无响应时兜底 `req.status`），因此规则判定必须使用「中英文兼容的状态集合」，不能只比单一英文值。
6. 保持幂等：合规检查每次都会先 `delete()` 旧 `compliance_issues` 再重写，修改后的逻辑不影响该幂等性。

---

## 四、具体改动（可直接落地）

### 4.1 改动一：修复 `compliance.py` 的快照构建（第 47–71 行整段替换）

在 `backend/app/api/routes/compliance.py` **文件顶部**确认有 `import json`（若无则在其他 import 旁添加 `import json`）。

把第 47–71 行的快照构建循环替换为：

```python
def _parse_source_refs(raw) -> list:
    """把 Response.source_refs（Text 列，存 JSON 字符串）安全解析为列表。

    responses.py 以 str(source_dicts) 写入，形如：
      '[{"filename": "资质.pdf", "score": 12.3, "content": "..."}]'
    解析失败或为空时返回 []，绝不抛异常。
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


# 构建快照
snapshots: list[RequirementSnapshot] = []
for req in requirements:
    resp_content = ""
    source_refs: list = []
    resp_status = None

    responses = getattr(req, "responses", None) or []
    for r in responses:
        # 取响应内容（优先 edited_content，其次 ai_content）
        if not resp_content:
            resp_content = r.edited_content or r.ai_content or ""
        # 取首个非空 source_refs 并解析为列表
        if not source_refs and getattr(r, "source_refs", None):
            source_refs = _parse_source_refs(r.source_refs)
        # 取首个「有内容」响应的状态作为合规判定依据
        if resp_status is None and (r.edited_content or r.ai_content):
            resp_status = r.status

    # 合规检查针对「响应草稿」，因此 status 以响应草稿状态为准，兜底需求状态
    snapshot_status = resp_status or req.status or "未处理"

    snapshots.append(RequirementSnapshot(
        requirement_id=req.id,
        content=req.content or "",
        priority=req.priority or "P2",
        response_content=resp_content,
        source_refs=source_refs,
        status=snapshot_status,
    ))
```

> 说明：此改动同时解决根因 A（`source_refs` 正确传入）和根因 B 的「传入正确的响应状态」。原来的 `src = r.source_refs` 在 `for` 循环内部只取最后一个响应、`snapshots.append` 又写死 `[]` 的两处错误一并消除。

### 4.2 改动二：修复 `compliance_checker.py` 的规则判定（第 29–42 行 `check` 方法替换）

把 `backend/app/services/compliance_checker.py` 中 `ComplianceChecker.check` 方法（第 29–42 行）整体替换为：

```python
    # 视为「已完成 / 已具备可审核响应」的状态集合（中英文兼容，避免再次因语言不一致漏判）
    COMPLETED_STATUSES = {
        "completed", "已完成",
        "pending_review", "待评审",
        "approved", "已通过", "reviewed",
    }

    def check(self, requirements: list[RequirementSnapshot]) -> list[ComplianceIssue]:
        issues: list[ComplianceIssue] = []
        for item in requirements:
            content = item.response_content.strip()
            # P0 且响应未完成（无有效响应草稿）→ 高风险
            p0_incomplete = item.priority == "P0" and item.status not in self.COMPLETED_STATUSES
            if p0_incomplete:
                issues.append(self._issue(item, "P0_RESPONSE_MISSING", "high", "P0 响应项尚未完成", "补充响应内容并完成审核。"))
            if not content and not p0_incomplete:
                issues.append(self._issue(item, "RESPONSE_CONTENT_EMPTY", "high", "响应内容为空", "补充可审核的响应内容。"))
            elif not item.source_refs:
                issues.append(self._issue(item, "RESPONSE_SOURCE_MISSING", "medium", "响应内容缺少企业资料来源", "补充可追溯的企业资料引用。"))
            if item.status in ("needs_manual", "需要人工补充"):
                issues.append(self._issue(item, "MANUAL_MATERIAL_REQUIRED", "medium", "资料不足，需要人工补充", "上传相关资质、案例或技术资料。"))
        return self._deduplicate(issues)
```

> 说明：
> - P0 规则从 `item.status != "completed"`（只比单一英文值，因中文永远不等而必报）改为 `item.status not in COMPLETED_STATUSES`（中英文兼容集合）。批量生成后响应状态为 `pending_review`，命中集合 → 不再误报；真正未生成 / `needs_manual` 的 P0 需求仍会正确报高风险。
> - needs_manual 规则从 `item.status == "needs_manual"`（永远不命中，因原传入中文）改为 `item.status in ("needs_manual", "需要人工补充")`（现在传入的是响应草稿状态，能正确命中）。

---

## 五、预期结果（修改后行为）

以一个项目为例，假设有：
- 需求 #186（P0，已批量生成响应，来源来自企业资料）→ 修改后**不再**报「P0 响应项尚未完成」，**不再**报「缺少企业资料来源」
- 需求 #188（P0，尚未生成响应）→ 仍报「P0 响应项尚未完成」高风险（正确）
- 需求 #187（已生成响应，但检索无资料 → 响应状态 `needs_manual`）→ 报「资料不足，需要人工补充」中风险（原来漏报，现在修正）
- 需求 #192（P0，`needs_manual`）→ 同时报「P0 响应项尚未完成」+「资料不足，需要人工补充」（正确）

即：误报消失、漏报补上、真实风险保留。

---

## 六、验证步骤

1. 启动后端服务。
2. 选一个**已对某 P0 需求成功批量生成响应**的项目，调用 `POST /{project_id}/compliance-check`。
3. 查询 `compliance_issues` 表（或前端合规检查页），确认：
   - 之前必报的「P0 响应项尚未完成」「响应内容缺少企业资料来源」对**已生成且有来源**的需求已消失；
   - 对**未生成 / 无资料**的需求仍正常报警。
4. 选一个检索无资料、响应状态为 `needs_manual` 的需求，确认现在能正确出现「资料不足，需要人工补充」中风险。
5. 跑一遍现有合规检查相关测试（如有）确保 `RequirementSnapshot` 字段签名未变、`ReportService.build()` 调用正常。

---

## 七、交付自检清单

- [ ] `compliance.py` 顶部已 `import json`（如原本缺失）
- [ ] `compliance.py` 快照循环已替换为 4.1 版本，`source_refs` 正确解析传入
- [ ] `compliance.py` 快照 `status` 改为使用响应草稿状态（兜底需求状态）
- [ ] `compliance_checker.py` 的 `check` 方法已替换为 4.2 版本（含 `COMPLETED_STATUSES` 集合）
- [ ] 未改动任何模型 / 数据库 schema / 前端 / API 路径
- [ ] 验证步骤通过，误报消除、漏报补上、真实风险保留
