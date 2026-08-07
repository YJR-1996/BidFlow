// BidFlow API client - Axios wrapper with token injection and error handling
import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

// Request interceptor: inject token + auto multipart for FormData
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // 自动检测 FormData：设 multipart 让 axios 加 boundary（之前因默认 application/json
  // 导致 FormData 被 JSON 序列化，后端 Form() 拿不到字段，使用默认值）
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    delete config.headers['Content-Type']  // 让 axios + XHR 自动加 boundary
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
        localStorage.removeItem('token')
        // 路由使用 createWebHashHistory，跳转需带 hash 前缀，否则会落到空白页
        window.location.href = '/#/login'
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
      ElMessage.error(message)
      return Promise.reject(new Error(message))
    }
    // Network error
    ElMessage.error('网络连接失败，请检查网络')
    return Promise.reject(error)
  }
)

export default api
