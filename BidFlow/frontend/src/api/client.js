// BidFlow API client - Axios wrapper with token injection and error handling
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

// Request interceptor: inject token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor: extract data and handle 401
api.interceptors.response.use(
  response => {
    // Return the data property directly
    return response.data
  },
  error => {
    if (error.response) {
      const { status, data } = error.response
      if (status === 401) {
        localStorage.removeItem('access_token')
        window.location.href = '/login'
      }
      // Show error message from backend
      let message = '请求失败'
      if (status === 409) {
        message = '用户名已存在，请重新输入'
      } else if (data?.detail) {
        message = typeof data.detail === 'string' ? data.detail : data.detail.message || JSON.stringify(data.detail)
      } else if (data?.message) {
        message = data.message
      }
      if (typeof window !== 'undefined' && window.ElementPlus) {
        window.ElementPlus.ElMessage.error(message)
      }
      return Promise.reject(new Error(message))
    }
    // Network error
    if (typeof window !== 'undefined' && window.ElementPlus) {
      window.ElementPlus.ElMessage.error('网络连接失败，请检查网络')
    }
    return Promise.reject(error)
  }
)

export default api
