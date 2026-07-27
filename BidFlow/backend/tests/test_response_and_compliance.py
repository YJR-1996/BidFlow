# 负责人：成员 D
#
# 你要做什么：自动验证大模型链路的关键业务规则，而不调用真实 API。
# 编写顺序：1）Mock C 的检索结果和 llm_client；2）测试有资料时保存来源；3）测试无资料时返回 needs_manual；4）测试空 P0 项为 high；5）测试无来源为 medium；6）测试报告统计。
# 完成后验证：运行 pytest tests/test_response_and_compliance.py -v，全部通过且网络请求数为零。
