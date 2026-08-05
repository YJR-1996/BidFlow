// Statistics API
import api from './client'

/**
 * Get statistics dashboard data
 * @param {string} period - Time range: '7d', '30d', '90d'
 * @param {number|null} projectId - Project scope (null = all user's projects)
 */
export async function getStats(period = '30d', projectId = null) {
  const params = { period }
  if (projectId) params.project_id = projectId
  const data = await api.get('/stats', { params })
  return data
}