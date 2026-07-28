// Company materials API calls
import api from './client'

// Upload company document
export async function uploadMaterial(formData) {
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

// Search knowledge base
export async function searchKnowledge(query, projectId, topK = 5) {
  const data = await api.post('/retrieval/search', {
    query,
    project_id: projectId,
    top_k: topK
  })
  return data
}
