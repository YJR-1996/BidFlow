// Company materials API calls
import api from './client'

/**
 * 上传企业资料文档
 * @param {FormData} formData - 包含 file, category, tags 等字段的表单数据
 * @param {Object} options - 可选参数
 * @param {string} [options.scope='company'] - 资料作用域: 'company'(公司级共享) | 'project'(项目级专属)
 * @param {number} [options.projectId] - 归属项目 ID（scope='project' 时必填）
 * @returns {Promise<Object>} 上传结果
 */
export async function uploadMaterial(formData, options = {}) {
  const { scope = 'company', projectId } = options

  // 添加 scope 和 project_id 到 formData
  formData.append('scope', scope)
  if (scope === 'project' && projectId) {
    formData.append('project_id', String(projectId))
  }

  const data = await api.post('/company-documents', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return data
}

// Get materials list (with optional project_id filter)
export async function getMaterials(params = {}) {
  const data = await api.get('/company-documents', { params })
  return data
}

// Delete material
export async function deleteMaterial(id) {
  const data = await api.delete(`/company-documents/${id}`)
  return data
}

// Update material scope (company ⇄ project + target project)
export async function updateMaterialScope(id, { scope = 'company', projectId = null }) {
  const formData = new FormData()
  formData.append('scope', scope)
  if (scope === 'project' && projectId) {
    formData.append('project_id', String(projectId))
  }
  const data = await api.patch(`/company-documents/${id}/scope`, formData)
  return data
}

// Search knowledge base
export async function searchKnowledge(query, projectId, topK = 5) {
  const data = await api.post('/retrieval/search', {
    query,
    project_id: projectId,
    top_k: topK
  })
  return data
}

// Get document detail with content preview
export async function getDocumentDetail(docId) {
  const data = await api.get(`/company-documents/${docId}/detail`)
  return data
}
