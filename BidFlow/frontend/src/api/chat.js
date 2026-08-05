// AI 助手对话 API
import api from './client'

// 与项目 AI 助手对话（多轮，后端按 项目+用户 内存保存会话）
export async function chatProject(projectId, message) {
  const data = await api.post(`/projects/${projectId}/chat`, { message }, { timeout: 90000 })
  return data
}
