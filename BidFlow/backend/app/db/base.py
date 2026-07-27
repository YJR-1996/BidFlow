# 负责人：组长／成员 A
#
# 你要做什么：让数据库初始化时能看到全组创建的所有数据表。
#
# 实现步骤：
# 1. 从 session.py 导入 ORM 的 Base。
# 2. 显式导入 user、bid_project、tender_document、requirement、company_document、response、compliance_issue。
# 3. 不在此处创建数据或执行查询；本文件只负责模型注册。
# 4. 新增模型时提醒对应成员在这里补充导入。
#
# 完成后手动验证：删除本地测试数据库后重启服务，检查全部七张表是否被重新创建。
