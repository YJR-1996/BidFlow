import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi, register as registerApi, getCurrentUser as getCurrentUserApi } from '@/api/auth'
import { ElMessage } from 'element-plus'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(null)
  const isAuthenticated = computed(() => !!token.value)
  const isLoggedIn = computed(() => !!token.value && !!user.value)

  function setToken(t) {
    token.value = t
    localStorage.setItem('token', t)
  }

  function clearAuth() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
  }

  function logout() {
    clearAuth()
  }

  async function doLogin(username, password) {
    try {
      const res = await loginApi(username, password)
      if (res.data && res.data.access_token) {
        setToken(res.data.access_token)
        await fetchCurrentUser()
        return res
      }
      throw new Error('登录失败')
    } catch (error) {
      clearAuth()
      throw error
    }
  }

  async function doRegister(username, password) {
    try {
      const res = await registerApi(username, password)
      ElMessage.success('注册成功，请登录')
      return res
    } catch (error) {
      throw error
    }
  }

  async function fetchCurrentUser() {
    try {
      const res = await getCurrentUserApi()
      user.value = res.data
    } catch {
      clearAuth()
    }
  }

  return {
    token,
    user,
    isAuthenticated,
    isLoggedIn,
    setToken,
    clearAuth,
    logout,
    doLogin,
    doRegister,
    fetchCurrentUser
  }
})
