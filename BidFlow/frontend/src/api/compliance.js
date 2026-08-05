// Compliance and draft API calls
import api from './client'
import { parseResponse } from '@/utils/api'

// Run compliance check for project
// M9：合规核查同步跑规则引擎+语义 LLM（大项目可达 60s+），单独放宽超时，
// 避免 30s 全局硬墙导致"点了没反应"（后端实际仍在写库）
export async function runComplianceCheck(projectId) {
  const data = await api.post(`/${projectId}/compliance-check`, null, { timeout: 180000 })
  return data
}

// 生成补救计划：按 rule_code 映射未处理风险为可执行动作
// （upload_materials 引导上传资料 / regenerate 触发重新生成 / manual_review 人工处理）
// 路径注意：responses.router 挂载前缀 /requirements，所以是 /requirements/projects/...
export async function remediateProject(projectId) {
  const data = await api.post(`/requirements/projects/${projectId}/remediate`)
  return data
}

// Get compliance report for project
export async function getComplianceReport(projectId) {
  const data = await api.get(`/${projectId}/compliance-report`)
  return data
}

// Download report as Markdown
export async function downloadReportMarkdown(projectId) {
  const data = await api.get(`/${projectId}/compliance-report/markdown`, {
    responseType: 'blob'
  })
  return data
}

// Download full bid document (merged responses) as Markdown or PDF
// format: 'markdown' | 'pdf'
export async function downloadBidDocument(projectId, format = 'markdown') {
  const data = await api.get(`/projects/${projectId}/bid-document/${format}`, {
    responseType: 'blob'
  })
  return data
}

// Download bid package (zip: bid md/pdf + compliance report md/pdf + README)
export async function downloadBidPackage(projectId) {
  const data = await api.get(`/projects/${projectId}/bid-package`, {
    responseType: 'blob'
  })
  return data
}

// Generate AI draft for requirement
// H6 修复：单条生成会调 LLM（最坏 30s×3 重试 = 90s），单独放宽该接口超时，
// 避免 30s 全局硬墙导致「点了没反应」（后端实际仍在写库）。
// force=true：强制重新生成（跳过后端「已存在草稿」拦截，重新调 LLM 覆盖旧稿）
export async function generateDraft(requirementId, force = false) {
  const data = await api.post(`/requirements/${requirementId}/response/generate`, null, {
    timeout: 120000,
    params: force ? { force: true } : undefined
  })
  return data
}

// Get draft for requirement
export async function getDraft(requirementId) {
  const data = await api.get(`/requirements/${requirementId}/response`)
  return data
}

// Update draft/response for requirement
export async function updateDraft(requirementId, payload) {
  const data = await api.patch(`/requirements/${requirementId}/response`, payload)
  return data
}

// Update requirement
export async function updateRequirement(requirementId, updates) {
  const data = await api.patch(`/requirements/${requirementId}`, updates)
  return data
}

// Analyze requirement matches with company materials
export async function analyzeMatches(projectId) {
  const data = await api.get(`/requirements/projects/${projectId}/match-analysis`)
  return data
}

// Force re-run match analysis (user explicit button click) — 异步启动，立即返回 task_id
export async function runMatchAnalysis(projectId) {
  const data = await api.post(`/requirements/projects/${projectId}/match-analysis/run`)
  return data
}

// 查询比对分析后台任务进度（轻量只读内存字典，不会触发 30s 超时）
export async function getMatchAnalysisStatus(projectId, taskId) {
  const data = await api.get(`/requirements/projects/${projectId}/match-analysis/status`, {
    params: { task_id: taskId }
  })
  return data
}

// 通用轮询比对分析任务：每 2s 查 status；completed 时 resolve（含 summary/matches）
// used by ProjectDetailView (autoLoadComparison/runComparison) 和 RequirementTable (onMounted)
// M7：支持 signal（AbortSignal）——组件卸载时 abort，停止轮询并回收定时器
export function pollMatchAnalysisTask(projectId, taskId, { intervalMs = 2000, timeoutMs = 600000, signal = null } = {}) {
  return new Promise((resolve, reject) => {
    let timeoutHandle = null
    const cleanup = () => { clearInterval(timer); if (timeoutHandle) clearTimeout(timeoutHandle) }
    const timer = setInterval(async () => {
      if (signal?.aborted) {
        cleanup()
        reject(new Error('已取消'))
        return
      }
      try {
        const status = parseResponse(await getMatchAnalysisStatus(projectId, taskId), {})
        if (status?.status === 'completed') {
          cleanup()
          resolve(status)
        } else if (status?.status === 'failed') {
          cleanup()
          reject(new Error(status.error || '比对分析失败'))
        }
      } catch (e) {
        cleanup()
        reject(e)
      }
    }, intervalMs)
    timeoutHandle = setTimeout(() => { cleanup(); reject(new Error('比对分析超时')) }, timeoutMs)
  })
}

// Batch generate responses for all requirements
// 启动批量生成任务（异步，立即返回 task_id）
// requirementIds 可选：只处理指定需求（选中批量生成）
export async function batchGenerateResponses(projectId, requirementIds = null) {
  // 手拼 URLSearchParams，强制 ?requirement_ids=271&requirement_ids=272&...
  // （不能直接传数组给 axios params——axios 默认序列化为 requirement_ids[]=271（带 [] 后缀），
  //   FastAPI Query 参数名是 requirement_ids 匹配不上 → 收不到参数 → 静默全项目处理）
  const qs = new URLSearchParams()
  if (requirementIds?.length) {
    requirementIds.forEach(id => qs.append('requirement_ids', id))
  }
  const qsStr = qs.toString()
  const url = qsStr
    ? `/requirements/projects/${projectId}/batch-generate?${qsStr}`
    : `/requirements/projects/${projectId}/batch-generate`
  const data = await api.post(url)
  return data
}

// 查询批量任务进度（前端每 2s 轮询）
// 注：此接口本身很快（只读内存字典），不会触发 30s 超时
export async function getBatchStatus(projectId, taskId) {
  const data = await api.get(`/requirements/projects/${projectId}/batch-status/${taskId}`)
  return data
}


