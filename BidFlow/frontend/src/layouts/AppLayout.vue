<!-- AppLayout.vue - Shared authenticated layout with sidebar, header, and route outlet -->
<template>
  <div class="app-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="sidebar-brand">
          <span class="material-symbols-outlined sidebar-logo-icon">bid_landscape</span>
          <div>
            <h1 class="sidebar-logo">BidFlow</h1>
            <p class="sidebar-subtitle">企业采购管理平台</p>
          </div>
        </div>
      </div>
      <nav class="sidebar-nav">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :class="['nav-item', { active: isNavActive(item) }]"
          :to="item.path"
        >
          <span class="nav-icon material-symbols-outlined">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <button class="btn-new-project" @click="$router.push('/new-project')">
          <span class="material-symbols-outlined">add</span>
          新建投标项目
        </button>
        <router-link v-for="item in footerItems" :key="item.name" :to="item.path" class="nav-item footer-nav">
          <span class="nav-icon material-symbols-outlined">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </div>
    </aside>

    <!-- Main content area -->
    <div class="main-area">
      <!-- Top header -->
      <header class="top-header">
        <div class="header-left">
          <button v-if="showBack" class="header-back" @click="$router.back()">
            <span class="material-symbols-outlined">arrow_back</span>
          </button>
          <h2 class="header-page-title">{{ pageTitle }}</h2>
        </div>
        <div class="header-right">
          <div class="header-search-wrap">
            <el-input
              v-if="showSearch"
              class="header-search"
              placeholder="搜索项目数据..."
              v-model="searchQuery"
            >
              <template #prefix>
                <span class="material-symbols-outlined">search</span>
              </template>
            </el-input>
          </div>
          <div class="header-actions">
            <el-badge :is-dot="true" class="header-badge">
              <span class="material-symbols-outlined">notifications</span>
            </el-badge>
            <el-dropdown trigger="click" @command="handleUserCommand">
              <div class="user-info">
                <div class="user-text">
                  <p class="user-name">{{ authStore.user?.username || '用户' }}</p>
                  <p class="user-role">项目主管</p>
                </div>
                <el-avatar :size="32" class="user-avatar">
                  {{ (authStore.user?.username || 'U').charAt(0).toUpperCase() }}
                </el-avatar>
              </div>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="profile">
                    <span class="material-symbols-outlined">person</span>个人资料
                  </el-dropdown-item>
                  <el-dropdown-item command="settings">
                    <span class="material-symbols-outlined">settings</span>设置
                  </el-dropdown-item>
                  <el-dropdown-item divided command="logout">
                    <span class="material-symbols-outlined">logout</span>退出登录
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </header>

      <!-- Route outlet -->
      <main class="content-area">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const searchQuery = ref('')

const navItems = [
  { name: 'ProjectList', label: '项目管理', icon: 'folder_open', path: '/projects' },
  { name: 'CompanyMaterials', label: '资料库', icon: 'description', path: '/company-materials' },
  { name: 'Compliance', label: '合规核查', icon: 'fact_check', path: '/compliance' },
  { name: 'Analytics', label: '统计报表', icon: 'analytics', path: '/analytics' },
]

const footerItems = [
  { name: 'Settings', label: '设置', icon: 'settings', path: '/' },
  { name: 'Help', label: '帮助支持', icon: 'help', path: '/' },
]

const pageTitle = computed(() => {
  const title = route.meta?.title
  if (title) return title
  const match = route.matched.find(m => m.meta?.title)
  return match?.meta?.title || 'BidFlow'
})

const showBack = computed(() => route.name === 'ProjectDetail')
const showSearch = computed(() => route.name !== 'Login' && route.name !== 'Register')

function isNavActive(item) {
  if (item.name === 'ProjectList') return route.name === 'ProjectList' || route.name === 'ProjectDetail'
  if (item.name === 'CompanyMaterials') return route.name === 'CompanyMaterials'
  if (item.name === 'Compliance') return route.name === 'Compliance'
  if (item.name === 'Analytics') return route.name === 'Analytics'
  return false
}

function handleUserCommand(command) {
  if (command === 'logout') {
    authStore.logout()
    router.push('/login')
  } else if (command === 'profile') {
    ElMessage.info('个人资料功能开发中')
  } else if (command === 'settings') {
    ElMessage.info('设置功能开发中')
  }
}
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 260px;
  height: 100vh;
  position: fixed;
  left: 0;
  top: 0;
  background: var(--surface-container-lowest);
  border-right: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  padding: 24px 16px;
  z-index: 50;
}

.sidebar-header {
  margin-bottom: 24px;
  padding: 0 8px;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sidebar-logo-icon {
  color: var(--primary);
  font-size: 28px;
}

.sidebar-logo {
  font-size: 24px;
  font-weight: 700;
  color: var(--primary);
  line-height: 1.1;
  margin: 0;
}

.sidebar-subtitle {
  font-size: 11px;
  color: var(--on-surface-variant);
  margin: 0;
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  text-decoration: none;
  color: var(--on-surface-variant);
  transition: all 0.2s;
  font-size: 14px;
}

.nav-item:hover {
  background: var(--surface-container-high);
  color: var(--on-surface);
}

.nav-item.active {
  color: var(--primary);
  font-weight: 600;
  background: var(--surface-container-low);
  border-left: 4px solid var(--primary);
  padding-left: 8px;
}

.nav-icon {
  margin-right: 12px;
  font-size: 22px;
}

.nav-label {
  font-size: 14px;
}

.sidebar-footer {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px 8px 0;
  border-top: 1px solid var(--border-subtle);
}

.btn-new-project {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 12px 16px;
  background: var(--primary-container);
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s;
  margin-bottom: 16px;
}

.btn-new-project:hover {
  opacity: 0.9;
}

.btn-new-project:active {
  transform: scale(0.95);
}

.footer-nav {
  padding: 8px 12px;
}

.main-area {
  margin-left: 260px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--surface-gray);
}

.top-header {
  height: 64px;
  position: fixed;
  top: 0;
  right: 0;
  left: 260px;
  z-index: 40;
  background: var(--surface-container-lowest);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-back {
  background: none;
  border: none;
  padding: 8px;
  border-radius: 50%;
  cursor: pointer;
  color: var(--on-surface);
  display: flex;
  align-items: center;
}

.header-back:hover {
  background: var(--surface-container-low);
}

.header-page-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--on-surface);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 24px;
}

.header-search-wrap {
  flex: 1;
  max-width: 280px;
}

.header-search {
  max-width: 280px;
}

.header-search :deep(.el-input__wrapper) {
  background: var(--surface-gray);
  border: none;
  border-radius: 8px;
  box-shadow: none !important;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-badge {
  cursor: pointer;
}

.header-badge .material-symbols-outlined {
  font-size: 22px;
  color: var(--on-surface-variant);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-left: 16px;
  border-left: 1px solid var(--border-subtle);
  cursor: pointer;
}

.user-text {
  text-align: right;
}

.user-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--on-surface);
  line-height: 1.2;
  margin: 0;
}

.user-role {
  font-size: 10px;
  color: var(--on-surface-variant);
  margin: 0;
}

.user-avatar {
  background: var(--primary-fixed);
  color: var(--on-primary-fixed);
  font-weight: 600;
}

.content-area {
  padding-top: 96px;
  padding-bottom: 48px;
  padding-left: 32px;
  padding-right: 32px;
  flex: 1;
  max-width: 1440px;
  margin: 0 auto;
  width: 100%;
}

:deep(.el-button--primary) {
  --el-button-bg-color: var(--primary);
  --el-button-border-color: var(--primary);
  --el-button-hover-bg-color: var(--primary-container);
}

:deep(.el-tag--success) {
  --el-tag-bg-color: rgba(52, 168, 83, 0.1);
  --el-tag-text-color: var(--success-green);
}

:deep(.el-tag--warning) {
  --el-tag-bg-color: rgba(251, 188, 4, 0.1);
  --el-tag-text-color: #b06000;
}

:deep(.el-tag--danger) {
  --el-tag-bg-color: rgba(186, 26, 26, 0.1);
  --el-tag-text-color: var(--error);
}

:deep(.el-tag--info) {
  --el-tag-bg-color: rgba(43, 91, 181, 0.1);
  --el-tag-text-color: var(--primary);
}
</style>
