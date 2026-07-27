# 负责人：成员 C
#
# 你要做什么：给 D 提供唯一的“从企业资料找证据”入口。
# 实现顺序：1）接收 query、owner_id 或 project_id、top_k；2）检查 query 非空且 top_k 合理；3）调用 vector_store 查询；4）过滤低相关结果；5）转成 content、score、filename、material_type、source_ref 结构；6）结果为空时返回空列表。
# 重要约束：D 不允许直接使用 Chroma；所有检索都必须经过本服务，保证数据隔离和来源字段一致。
# 完成后验证：换一个用户检索不能看到别人的资料；没有匹配资料时返回 []。
