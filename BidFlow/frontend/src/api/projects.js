import client from './client'

export const listProjects = () => client.get('/projects')
export const createProject = (payload) => client.post('/projects', payload)
export const getProject = (id) => client.get(`/projects/${id}`)
export const updateProject = (id, payload) => client.patch(`/projects/${id}`, payload)
export const listRequirements = (id) => client.get(`/projects/${id}/requirements`)
export const updateRequirement = (id, payload) => client.patch(`/requirements/${id}`, payload)
export const uploadTender = (id, file) => {
  const form = new FormData()
  form.append('file', file)
  return client.post(`/projects/${id}/tender-documents`, form)
}
export const parseTender = (id) => client.post(`/tender-documents/${id}/parse`)
