import axios from 'axios'

const client = axios.create({ baseURL: '/api', timeout: 30000 })

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('bidflow_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.detail?.message || error.response?.data?.detail || error.message || '请求失败'
    if (error.response?.status === 401) localStorage.removeItem('bidflow_token')
    return Promise.reject(new Error(message))
  },
)

export default client
