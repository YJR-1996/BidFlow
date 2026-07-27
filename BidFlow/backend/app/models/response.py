# 负责人：成员 D
#
# 你要做什么：保存每条招标需求的 AI 草稿、人工修改结果和资料依据。
# 实现步骤：1）关联 requirement_id；2）保存 AI 原始草稿；3）保存用户最终编辑内容；4）以 JSON 保存 source_refs；5）保存 draft、pending_review、completed、needs_manual 状态；6）记录更新时间。
# 完成后验证：任意 AI 草稿均能展开看到来源；无来源草稿不能直接成为 completed。
