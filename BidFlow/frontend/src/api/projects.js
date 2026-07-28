// Project API calls
import api from './client'

// Get all projects
export async function getProjects(params = {}) {
  const data = await api.get('/projects', { params })
  return data
}

// Get single project detail
export async function getProject(id) {
  const data = await api.get(`/projects/${id}`)
  return data
}

// Create new project
export async function createProject(projectData) {
  const data = await api.post('/projects', projectData)
  return data
}

// Update project
export async function updateProject(id, projectData) {
  const data = await api.patch(`/projects/${id}`, projectData)
  return data
}

// Delete project
export async function deleteProject(id) {
  const data = await api.delete(`/projects/${id}`)
  return data
}

// Upload tender document
export async function uploadTender(projectId, formData) {
  const data = await api.post(`/projects/${projectId}/tender-documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return data
}

// List tender documents for project
export async function listTenderDocuments(projectId) {
  const data = await api.get(`/projects/${projectId}/tender-documents`)
  return data
}

// Get tender document detail
export async function getTenderDocument(documentId) {
  const data = await api.get(`/tender-documents/${documentId}`)
  return data
}

// Delete tender document
export async function deleteTenderDocument(documentId) {
  const data = await api.delete(`/tender-documents/${documentId}`)
  return data
}

// Parse tender document and extract requirements
export async function parseTenderDocument(documentId) {
  const data = await api.post(`/tender-documents/${documentId}/parse`)
  return data
}

// Get requirements for project
export async function getRequirements(projectId, params = {}) {
  const data = await api.get(`/projects/${projectId}/requirements`, { params })
  return data
}

// Get single requirement detail
export async function getRequirement(requirementId) {
  const data = await api.get(`/requirements/${requirementId}`)
  return data
}

// Update requirement
export async function updateRequirement(requirementId, updates) {
  const data = await api.patch(`/requirements/${requirementId}`, updates)
  return data
}
