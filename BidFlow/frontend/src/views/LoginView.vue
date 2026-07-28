<!-- LoginView.vue - Login and register page -->
<template>
  <div class="login-page">
    <!-- Left Side: Brand Visual Area -->
    <div class="brand-area">
      <div class="brand-content">
        <div class="brand-logo">
          <div class="logo-icon">
            <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">auto_awesome</span>
          </div>
          <h1>BidFlow AI</h1>
        </div>
        <h2>智能编制与合规核查平台</h2>
        <p>加速招投标流程，保障文件合规性。利用深度学习与大语言模型，为您的采购与投标提供全方位的技术支撑。</p>
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
    </div>

    <!-- Right Side: Form Area -->
    <div class="form-area">
      <div class="form-container" :class="{ 'fade-in': true }">
        <!-- Header -->
        <div class="form-header">
          <h3 v-if="isLogin">欢迎回来</h3>
          <h3 v-else>创建新账号</h3>
          <p>{{ isLogin ? '请登录您的账户以开始工作' : '加入 BidFlow AI，开启高效智能编纂之旅。' }}</p>
        </div>

        <!-- Login Form -->
        <div v-if="isLogin" class="login-form">
          <!-- Username -->
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

          <!-- Password -->
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
                <span class="material-symbols-outlined input-icon">{{ showPassword ? 'visibility_off' : 'visibility' }}</span>
              </button>
            </div>
            <p class="error-text" :class="{ hidden: !loginErrors.password }">{{ loginErrors.password }}</p>
          </div>

          <!-- Remember me & Forgot -->
          <div class="form-options">
            <label class="checkbox-label">
              <input type="checkbox" v-model="loginForm.remember" />
              <span>记住我</span>
            </label>
            <a class="forgot-link" href="#">忘记密码？</a>
          </div>

          <!-- Submit Button -->
          <button
            class="submit-btn"
            :class="{ loading: loginLoading }"
            @click="handleLogin"
            :disabled="loginLoading"
          >
            <span v-if="!loginLoading">{{ isLogin ? '登录' : '注册' }}</span>
            <span v-else>处理中...</span>
          </button>

          <!-- Divider -->
          <div class="divider">
            <div class="divider-line"></div>
            <span class="divider-text">其他登录方式</span>
            <div class="divider-line"></div>
          </div>

          <!-- Social Login -->
          <div class="social-buttons">
            <button class="social-btn" type="button">
              <span class="material-symbols-outlined">fingerprint</span>
              <span>指纹</span>
            </button>
            <button class="social-btn" type="button">
              <span class="material-symbols-outlined">qr_code</span>
              <span>扫码</span>
            </button>
          </div>
        </div>

        <!-- Register Form -->
        <div v-else class="register-form">
          <!-- Username -->
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

          <!-- Password -->
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
                <span class="material-symbols-outlined input-icon">{{ showRegPassword ? 'visibility_off' : 'visibility' }}</span>
              </button>
            </div>
            <p class="error-text" :class="{ hidden: !registerErrors.password }">密码长度至少为6位</p>
          </div>

          <!-- Confirm Password -->
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
                <span class="material-symbols-outlined input-icon">{{ showRegConfirmPassword ? 'visibility_off' : 'visibility' }}</span>
              </button>
            </div>
            <p class="error-text" :class="{ hidden: !registerErrors.confirm }">两次输入的密码不一致</p>
          </div>

          <!-- Agreement -->
          <div class="agreement">
            <input type="checkbox" id="agreement" v-model="registerForm.agreed" />
            <label for="agreement">
              我已阅读并同意 <a class="text-primary hover:underline" href="#">服务协议</a> 和 <a class="text-primary hover:underline" href="#">隐私政策</a>
            </label>
          </div>

          <!-- Submit Button -->
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

        <!-- Footer Toggle -->
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
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()

const isLogin = ref(true)
const loginLoading = ref(false)
const registerLoading = ref(false)
const showPassword = ref(false)
const showRegPassword = ref(false)
const showRegConfirmPassword = ref(false)

const loginForm = reactive({
  username: '',
  password: '',
  remember: false
})

const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  agreed: false
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
    router.push('/')
  } catch (error) {
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
  } catch (error) {
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
}

/* Brand area (left side) */
.brand-area {
  display: none;
  flex: 1;
  background: #1a73e8;
  align-items: center;
  justify-content: center;
  padding: 64px;
  position: relative;
  overflow: hidden;
}

@media (min-width: 1024px) {
  .brand-area {
    display: flex;
  }
}

.brand-content {
  max-width: 480px;
  color: white;
  position: relative;
  z-index: 1;
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
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.logo-icon .material-symbols-outlined {
  font-size: 30px;
  color: #1a73e8;
}

.brand-logo h1 {
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.brand-content > h2 {
  font-size: 32px;
  font-weight: 700;
  margin-bottom: 16px;
  line-height: 1.2;
}

.brand-content > p {
  font-size: 18px;
  opacity: 0.85;
  margin-bottom: 48px;
  line-height: 1.7;
}

.brand-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
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
}

.stat-card .material-symbols-outlined {
  font-size: 28px;
  color: white;
}

.stat-card strong {
  display: block;
  font-size: 14px;
  margin-bottom: 2px;
}

.stat-card span:last-child {
  font-size: 12px;
  opacity: 0.6;
}

/* Form area (right side) */
.form-area {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  background: #f7f9fc;
}

.form-container {
  width: 100%;
  max-width: 440px;
}

.fade-in {
  animation: fadeInSlideUp 0.7s ease-out;
}

@keyframes fadeInSlideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Form header */
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
  color: #191c1e;
  margin-bottom: 8px;
}

.form-header p {
  font-size: 14px;
  color: #414754;
}

/* Form groups */
.form-group {
  margin-bottom: 24px;
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
  font-size: 14px;
  font-weight: 600;
  color: #414754;
  margin-bottom: 8px;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 12px;
  font-size: 20px;
  color: #727785;
  pointer-events: none;
  transition: color 0.2s;
}

.form-input {
  width: 100%;
  padding: 12px 48px 12px 44px;
  border: 1px solid #c1c6d6;
  border-radius: 8px;
  font-size: 14px;
  color: #191c1e;
  background: white;
  transition: all 0.2s;
  outline: none;
}

.form-input:focus {
  border-color: #005bbf;
  box-shadow: 0 0 0 2px rgba(0, 91, 191, 0.1);
}

.form-input.input-error {
  border-color: #ba1a1a;
}

.form-input:focus ~ .input-icon,
.form-input:focus + .input-icon {
  color: #005bbf;
}

.toggle-password {
  position: absolute;
  right: 12px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.toggle-password:hover {
  color: #191c1e;
}

.error-text {
  font-size: 12px;
  color: #ba1a1a;
  margin-top: 4px;
  display: none;
}

.error-text:not(.hidden) {
  display: block;
}

/* Form options */
.form-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #414754;
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #005bbf;
  cursor: pointer;
}

.forgot-link {
  font-size: 12px;
  color: #005bbf;
  text-decoration: none;
}

.forgot-link:hover {
  text-decoration: underline;
}

/* Submit button */
.submit-btn {
  width: 100%;
  padding: 12px 16px;
  background: #005bbf;
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
}

.submit-btn:hover {
  background: rgba(0, 91, 191, 0.9);
}

.submit-btn:active {
  transform: scale(0.98);
}

.submit-btn.loading {
  opacity: 0.8;
  cursor: not-allowed;
}

/* Divider */
.divider {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 16px 0;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: #c1c6d6;
}

.divider-text {
  font-size: 12px;
  color: #727785;
}

/* Social buttons */
.social-buttons {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 16px;
}

.social-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid #c1c6d6;
  border-radius: 8px;
  background: white;
  cursor: pointer;
  transition: background 0.2s;
  font-size: 14px;
  color: #414754;
}

.social-btn:hover {
  background: #f2f4f7;
}

.social-btn .material-symbols-outlined {
  font-size: 20px;
}

/* Agreement */
.agreement {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 24px;
}

.agreement input[type="checkbox"] {
  width: 16px;
  height: 16px;
  margin-top: 2px;
  accent-color: #005bbf;
  cursor: pointer;
  flex-shrink: 0;
}

.agreement label {
  font-size: 14px;
  color: #414754;
  line-height: 1.5;
}

/* Footer */
.form-footer {
  text-align: center;
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid #c1c6d6;
}

.form-footer p {
  font-size: 14px;
  color: #414754;
}

.link-primary {
  color: #005bbf;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
}

.link-primary:hover {
  text-decoration: underline;
}

/* Responsive */
@media (max-width: 900px) {
  .brand-area {
    display: none !important;
  }
  .form-area {
    width: 100%;
    padding: 24px;
  }
}
</style>
