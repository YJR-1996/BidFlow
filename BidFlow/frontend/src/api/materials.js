import client from './client'

export const listMaterials = () => client.get('/company-documents')
export const uploadMaterial = (file) => {
  const form = new FormData()
  form.append('file', file)
  return client.post('/company-documents', form)
}
export const deleteMaterial = (id) => client.delete(`/company-documents/${id}`)
export const searchMaterials = (query, top_k = 5) => client.post('/company-documents/search', { query, top_k })
