import client from './client'

export const generateDraft = (payload) => client.post('/responses/generate', payload)
export const getDraft = (id) => client.get(`/responses/${id}`)
export const updateDraft = (id, payload) => client.patch(`/responses/${id}`, payload)
export const runCompliance = (id) => client.post(`/compliance/projects/${id}/run`)
export const getReport = (id) => client.get(`/compliance/projects/${id}/report`)
export const reportUrl = (id) => `/api/compliance/projects/${id}/report.md`
