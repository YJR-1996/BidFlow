# D 模块接口契约

所有接口均需 JWT；A 接入 FastAPI 时负责项目归属鉴权。

## 生成响应草稿

`POST /api/requirements/{requirement_id}/response`

成功响应：

```json
{
  "content": "投标响应草稿正文",
  "sources": [{"content": "资料片段", "filename": "案例材料.pdf", "source_ref": "第 2 页", "score": 0.92}],
  "status": "pending_review",
  "message": "草稿已生成，等待人工审核。"
}
```

检索不到企业资料时，返回 `status: "needs_manual"` 和空 `sources`，不调用大模型。

## 查看或更新响应草稿

`GET /api/requirements/{requirement_id}/response`
`PATCH /api/requirements/{requirement_id}/response`

更新请求可包含 `content` 或 `status`。`status: "completed"` 时必须保留至少一条来源。

## 运行合规核查

`POST /api/projects/{project_id}/compliance-check`

返回：响应项总数、已完成数、完成度、高中低风险数量和风险列表。风险列表字段为 `requirement_id`、`rule_code`、`level`、`description`、`suggestion`。

## 导出审查报告

`GET /api/projects/{project_id}/compliance-report.md`

返回 Markdown 文本，包含完成度、风险统计、风险详情和待办建议。
