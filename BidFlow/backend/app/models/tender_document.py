# 负责人：成员 B
#
# 你要做什么：记录每份招标文件从上传到解析完成的全过程。
# 实现步骤：1）关联 project_id；2）保存原始文件名、真实存储路径、类型和上传时间；3）保存 pending、processing、success、failed 状态；4）失败时保存 error_message；5）关联由此文件提取的需求项。
# 完成后验证：上传后能看到 pending；解析成功变 success；故意上传损坏文件时能显示 failed 和原因。
