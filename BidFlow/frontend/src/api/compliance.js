// Compliance and draft API calls
import api from './client'

// Run compliance check for project
export async function runComplianceCheck(projectId) {
  const data = await api.post(`/projects/${projectId}/compliance-check`)
  return data
}

// Get compliance report for project
export async function getComplianceReport(projectId) {
  const data = await api.get(`/projects/${projectId}/compliance-report`)
  return data
}

// Download report as Markdown
export async function downloadReportMarkdown(projectId) {
  const data = await api.get(`/projects/${projectId}/compliance-report/markdown`, {
    responseType: 'blob'
  })
  return data
}

// Generate AI draft for requirement
export async function generateDraft(requirementId) {
  const data = await api.post(`/requirements/${requirementId}/response/generate`)
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

// Get requirements list
export async function getRequirements(projectId, params = {}) {
  const data = await api.get(`/projects/${projectId}/requirements`, { params })
  return data
}
