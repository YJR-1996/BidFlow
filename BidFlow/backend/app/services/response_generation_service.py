# 负责人：成员 D
#
# 你要做什么：根据一条招标需求和企业资料生成可追溯的投标响应草稿。
#
# 开始前确认：B 的 requirement 含内容和来源；C 的 retrieval_service 返回资料片段与来源；llm_client 可调用。
#
# 实现顺序：
# 1）读取 requirement，确认当前用户能访问其项目。
# 2）把 requirement.content 传给 retrieval_service。
# 3）检索结果为空时，不调用模型，直接返回 needs_manual 和“待人工补充”。
# 4）有资料时，把需求和资料片段填入 prompt_templates 的草稿模板。
# 5）调用 llm_client，保存 AI 草稿和所有 source_refs。
# 6）默认状态设为 pending_review，等待人工确认。
#
# 完成后验证：有案例资料时草稿显示案例来源；无资料时不生成虚构内容。
