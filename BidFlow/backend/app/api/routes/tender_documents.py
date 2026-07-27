# 负责人：成员 B
#
# 你要做什么：实现“上传招标文件并解析成响应清单”。
# 实现顺序：1）校验登录用户和项目归属；2）检查 TXT/PDF/DOCX；3）调用 file_storage 保存；4）创建 pending 记录；5）调用 document_parser；6）调用 tender_requirement_extractor；7）成功更新 success，失败更新 failed；8）提供状态查询和删除。
# 完成后验证：上传 TXT 后项目出现需求项；上传 JPG 被拒绝；解析失败能在页面看到原因。
