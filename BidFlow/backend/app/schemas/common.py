# 负责人：组长／成员 A
#
# 你要做什么：统一所有接口给前端的数据形状，减少前端逐接口判断。
#
# 实现步骤：
# 1. 定义成功响应：code、message、data。
# 2. 定义列表响应：items、total、page、page_size。
# 3. 定义错误响应：code、message、detail。
# 4. 与前端确认 code=0 表示成功，非 0 表示业务失败。
#
# 完成后手动验证：打开 Swagger，项目列表和登录接口的返回结构都应包含统一字段。
