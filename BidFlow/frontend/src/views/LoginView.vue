<template>
  <div class="login-page">
    <div class="brand-area">
      <div class="brand-content">
        <div class="brand-logo">
          <div class="logo-icon">
            <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">tips_and_updates</span>
          </div>
          <h1>BidFlow AI</h1>
        </div>
        <div class="brand-text">
          <h2>智能编制与合规核查平台</h2>
          <p>加速招投标流程，保障文件合规性。利用深度学习与大语言模型，为您的采购与投标提供全方位的技术支撑。</p>
        </div>
        <div class="brand-stats">
          <div class="stat-card">
            <span class="material-symbols-outlined">speed</span>
            <div>
              <strong>效率提升 70%</strong>
              <span>自动化文档生成</span>
            </div>
          </div>
          <div class="stat-card">
            <span class="material-symbols-outlined">verified</span>
            <div>
              <strong>100% 合规</strong>
              <span>法规智能实时核查</span>
            </div>
          </div>
        </div>
      </div>
      <div class="decoration-blob"></div>
    </div>

    <div class="form-area">
      <div class="form-container fade-in">
        <div class="form-header">
          <h3 v-if="isLogin">欢迎回来</h3>
          <h3 v-else>创建新账号</h3>
          <p>{{ isLogin ? '请登录您的账户以开始工作' : '加入 BidFlow AI，开启高效智能编纂之旅。' }}</p>
        </div>

        <div v-if="isLogin" class="login-form">
          <div class="form-group">
            <label>用户名</label>
            <div class="input-wrapper">
              <span class="material-symbols-outlined input-icon">person</span>
              <input
                v-model="loginForm.username"
                type="text"
                placeholder="请输入用户名"
                class="form-input"
                :class="{ 'input-error': loginErrors.username }"
                @input="clearError('username')"
              />
            </div>
            <p class="error-text" :class="{ hidden: !loginErrors.username }">{{ loginErrors.username }}</p>
          </div>

          <div class="form-group">
            <div class="form-label-row">
              <label>密码</label>
              <a class="forgot-link" href="#">忘记密码？</a>
            </div>
            <div class="input-wrapper">
              <span class="material-symbols-outlined input-icon">lock</span>
              <input
                v-model="loginForm.password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="请输入密码"
                class="form-input"
                :class="{ 'input-error': loginErrors.password }"
                @input="clearError('password')"
              />
              <button type="button" class="toggle-password" @click="showPassword = !showPassword">
                <span class="material-symbols-outlined">{{ showPassword ? 'visibility_off' : 'visibility' }}</span>
              </button>
            </div>
            <p class="error-text" :class="{ hidden: !loginErrors.password }">{{ loginErrors.password }}</p>
          </div>

          <button
            class="submit-btn"
            :class="{ loading: loginLoading }"
            @click="handleLogin"
            :disabled="loginLoading"
          >
            <span v-if="!loginLoading">登录</span>
            <span v-else>处理中...</span>
          </button>
        </div>

        <div v-else class="register-form">
          <div class="form-group">
            <label>用户名</label>
            <div class="input-wrapper">
              <span class="material-symbols-outlined input-icon">person</span>
              <input
                v-model="registerForm.username"
                type="text"
                placeholder="请输入用户名 (至少3位)"
                class="form-input"
                :class="{ 'input-error': registerErrors.username }"
                @input="clearError('register_username')"
              />
            </div>
            <p class="error-text" :class="{ hidden: !registerErrors.username }">用户名长度至少为3位</p>
          </div>

          <div class="form-group">
            <label>密码</label>
            <div class="input-wrapper">
              <span class="material-symbols-outlined input-icon">lock</span>
              <input
                v-model="registerForm.password"
                :type="showRegPassword ? 'text' : 'password'"
                placeholder="请输入密码 (至少6位)"
                class="form-input"
                :class="{ 'input-error': registerErrors.password }"
                @input="clearError('register_password')"
              />
              <button type="button" class="toggle-password" @click="showRegPassword = !showRegPassword">
                <span class="material-symbols-outlined">{{ showRegPassword ? 'visibility_off' : 'visibility' }}</span>
              </button>
            </div>
            <p class="error-text" :class="{ hidden: !registerErrors.password }">密码长度至少为6位</p>
          </div>

          <div class="form-group">
            <label>确认密码</label>
            <div class="input-wrapper">
              <span class="material-symbols-outlined input-icon">verified_user</span>
              <input
                v-model="registerForm.confirmPassword"
                :type="showRegConfirmPassword ? 'text' : 'password'"
                placeholder="请再次输入密码"
                class="form-input"
                :class="{ 'input-error': registerErrors.confirm }"
                @input="clearError('register_confirm')"
              />
              <button type="button" class="toggle-password" @click="showRegConfirmPassword = !showRegConfirmPassword">
                <span class="material-symbols-outlined">{{ showRegConfirmPassword ? 'visibility_off' : 'visibility' }}</span>
              </button>
            </div>
            <p class="error-text" :class="{ hidden: !registerErrors.confirm }">两次输入的密码不一致</p>
          </div>

          <div class="agreement">
            <input type="checkbox" id="agreement" v-model="registerForm.agreed" />
            <label for="agreement">
              我已阅读并同意 <a class="text-primary hover:underline" href="#">服务协议</a> 和 <a class="text-primary hover:underline" href="#">隐私政策</a>
            </label>
          </div>

          <button
            class="submit-btn"
            :class="{ loading: registerLoading }"
            @click="handleRegister"
            :disabled="registerLoading"
          >
            <span v-if="!registerLoading">注册账号</span>
            <span v-else>正在创建账号...</span>
          </button>
        </div>

        <div class="form-footer">
          <p v-if="isLogin">
            还没有账号？
            <a class="link-primary" @click="isLogin = false">立即注册</a>
          </p>
          <p v-else>
            已有账号？
            <a class="link-primary" @click="isLogin = true">去登录</a>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const isLogin = ref(true)

function syncModeFromRoute() {
  if (route.meta?.mode === 'register') {
    isLogin.value = false
  } else {
    isLogin.value = true
  }
}

watch(() => route.path, syncModeFromRoute)
onMounted(syncModeFromRoute)
const loginLoading = ref(false)
const registerLoading = ref(false)
const showPassword = ref(false)
const showRegPassword = ref(false)
const showRegConfirmPassword = ref(false)

const loginForm = reactive({
  username: '',
  password: '',
})

const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  agreed: false,
})

const loginErrors = reactive({
  username: '',
  password: ''
})

const registerErrors = reactive({
  username: '',
  password: '',
  confirm: ''
})

function clearError(field) {
  if (field.startsWith('register_')) {
    registerErrors[field.replace('register_', '')] = ''
  } else {
    loginErrors[field] = ''
  }
}

async function handleLogin() {
  loginErrors.username = ''
  loginErrors.password = ''

  let valid = true
  if (loginForm.username.length < 3) {
    loginErrors.username = '用户名至少需要 3 位字符'
    valid = false
  }
  if (loginForm.password.length < 6) {
    loginErrors.password = '密码至少需要 6 位字符'
    valid = false
  }
  if (!valid) return

  loginLoading.value = true
  try {
    await authStore.doLogin(loginForm.username, loginForm.password)
    ElMessage.success('登录成功')
    router.push('/projects')
  } catch {
    // Error handled by API interceptor
  } finally {
    loginLoading.value = false
  }
}

async function handleRegister() {
  registerErrors.username = ''
  registerErrors.password = ''
  registerErrors.confirm = ''

  let valid = true
  if (registerForm.username.length < 3) {
    registerErrors.username = '用户名长度至少为3位'
    valid = false
  }
  if (registerForm.password.length < 6) {
    registerErrors.password = '密码长度至少为6位'
    valid = false
  }
  if (registerForm.password !== registerForm.confirmPassword) {
    registerErrors.confirm = '两次输入的密码不一致'
    valid = false
  }
  if (!registerForm.agreed) {
    ElMessage.warning('请阅读并同意服务协议')
    return
  }
  if (!valid) return

  registerLoading.value = true
  try {
    await authStore.doRegister(registerForm.username, registerForm.password)
    ElMessage.success('注册成功！正在前往登录页面')
    isLogin.value = true
  } catch {
    // Error handled by API interceptor
  } finally {
    registerLoading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  min-height: 100vh;
  overflow: hidden;
  background: var(--surface);
}

.brand-area {
  display: none;
  flex: 1;
  background: linear-gradient(135deg, #005bbf 0%, #1a73e8 100%);
  position: relative;
  overflow: hidden;
  padding: 64px;
  color: white;
}

@media (min-width: 1024px) {
  .brand-area {
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
}

.brand-content {
  position: relative;
  z-index: 10;
  max-width: 480px;
}

.brand-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
}

.logo-icon {
  width: 48px;
  height: 48px;
  background: white;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.logo-icon .material-symbols-outlined {
  font-size: 30px;
  color: var(--primary-container);
}

.brand-logo h1 {
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: white;
}

.brand-text h2 {
  font-size: 32px;
  font-weight: 700;
  color: white;
  margin-bottom: 16px;
  line-height: 1.2;
}

.brand-text p {
  font-size: 18px;
  opacity: 0.85;
  line-height: 1.7;
  max-width: 440px;
}

.brand-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 48px;
}

.stat-card {
  padding: 20px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: flex-start;
  gap: 12px;
  transition: background 0.2s;
}

.stat-card:hover {
  background: rgba(255, 255, 255, 0.15);
}

.stat-card .material-symbols-outlined {
  font-size: 28px;
  color: white;
}

.stat-card strong {
  display: block;
  font-size: 14px;
  margin-bottom: 2px;
  color: white;
}

.stat-card span {
  font-size: 12px;
  opacity: 0.7;
  color: white;
}

.decoration-blob {
  position: absolute;
  bottom: -80px;
  right: -80px;
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(255,255,255,0.2) 0%, rgba(255,255,255,0) 70%);
  border-radius: 50%;
  pointer-events: none;
}

.form-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  background: var(--surface);
}

.form-container {
  width: 100%;
  max-width: 440px;
  background: white;
  padding: 40px 32px;
  border-radius: 16px;
  border: 1px solid var(--border-subtle);
  box-shadow: 0 12px 40px rgba(0, 91, 191, 0.08);
}

.fade-in {
  animation: fadeInSlideUp 0.6s ease-out;
}

@keyframes fadeInSlideUp {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.form-header {
  text-align: center;
  margin-bottom: 32px;
}

@media (min-width: 1024px) {
  .form-header {
    text-align: left;
  }
}

.form-header h3 {
  font-size: 24px;
  font-weight: 600;
  color: var(--on-surface);
  margin-bottom: 8px;
}

.form-header p {
  font-size: 14px;
  color: var(--on-surface-variant);
  margin: 0;
}

.form-group {
  margin-bottom: 20px;
}

.form-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.form-label-row label,
.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--on-surface-variant);
  margin-bottom: 8px;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 14px;
  font-size: 20px;
  color: var(--outline);
  pointer-events: none;
  transition: color 0.2s;
}

.form-input {
  width: 100%;
  padding: 12px 48px 12px 44px;
  border: 1px solid var(--outline-variant);
  border-radius: 8px;
  font-size: 14px;
  color: var(--on-surface);
  background: white;
  transition: all 0.2s;
  outline: none;
}

.form-input::placeholder {
  color: var(--outline);
}

.form-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(26, 115, 232, 0.1);
}

.form-input:focus ~ .input-icon,
.input-wrapper:focus-within .input-icon {
  color: var(--primary);
}

.form-input.input-error {
  border-color: var(--error);
}

.toggle-password {
  position: absolute;
  right: 10px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--outline);
}

.toggle-password:hover {
  color: var(--on-surface);
}

.error-text {
  font-size: 12px;
  color: var(--error);
  margin-top: 4px;
  display: none;
}

.error-text:not(.hidden) {
  display: block;
}

.forgot-link {
  font-size: 12px;
  color: var(--primary);
  text-decoration: none;
}

.forgot-link:hover {
  text-decoration: underline;
}

.submit-btn {
  width: 100%;
  padding: 12px 16px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
}

.submit-btn:hover {
  background: var(--primary-container);
}

.submit-btn:active {
  transform: scale(0.98);
}

.submit-btn.loading {
  opacity: 0.8;
  cursor: not-allowed;
}

.agreement {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 20px;
}

.agreement input[type="checkbox"] {
  width: 16px;
  height: 16px;
  margin-top: 2px;
  accent-color: var(--primary);
  cursor: pointer;
  flex-shrink: 0;
}

.agreement label {
  font-size: 13px;
  color: var(--on-surface-variant);
  line-height: 1.5;
}

.agreement .text-primary {
  color: var(--primary);
  cursor: pointer;
}

.agreement .text-primary:hover {
  text-decoration: underline;
}

.form-footer {
  text-align: center;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--outline-variant);
}

.form-footer p {
  font-size: 14px;
  color: var(--on-surface-variant);
  margin: 0;
}

.link-primary {
  color: var(--primary);
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
}

.link-primary:hover {
  text-decoration: underline;
}

.text-primary {
  color: var(--primary);
}

.hover\:underline:hover {
  text-decoration: underline;
}

.hidden {
  display: none !important;
}

@media (max-width: 900px) {
  .form-container {
    padding: 32px 24px;
  }
}
</style>
