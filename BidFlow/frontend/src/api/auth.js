// Authentication API calls
import api from './client'

export async function register(username, password) {
  const data = await api.post('/auth/register', { username, password })
  return data
}

export async function login(username, password) {
  const data = await api.post('/auth/login', { username, password })
  return data
}

export async function getCurrentUser() {
  const data = await api.get('/auth/me')
  return data
}
