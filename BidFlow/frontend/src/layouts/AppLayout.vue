<!-- AppLayout.vue - Shared authenticated layout with sidebar, header, and route outlet -->
<template>
  <div class="app-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h1 class="sidebar-logo">BidFlow AI</h1>
        <p class="sidebar-subtitle">企业采购平台</p>
      </div>
      <nav class="sidebar-nav">
        <a
          v-for="(item, index) in navItems"
          :key="item.name"
          :class="['nav-item', { active: route.name === item.name }]"
          :to="{ name: item.name }"
          @click="activeNav = item.name"
        >
          <span class="nav-icon material-symbols-outlined">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </a>
      </nav>
      <div class="sidebar-footer">
        <el-button class="new-project-btn" @click="$router.push({ name: 'NewProject' })">
          <template #icon><span class="material-symbols-outlined">add</span></template>
          新建项目
        </el-button>
      </div>
    </aside>

    <!-- Main content area -->
    <div class="main-area">
      <!-- Top header -->
      <header class="top-header">
        <div class="header-left">
          <span class="header-title">BidFlow</span>
          <el-input
            class="header-search"
            placeholder="搜索项目、文档或合规文件..."
            v-model="searchQuery"
            clearable
          >
            <template #prefix>
              <span class="material-symbols-outlined">search</span>
            </template>
          </el-input>
        </div>
        <div class="header-right">
          <el-badge :is-dot="true">
            <span class="header-icon material-symbols-outlined">notifications</span>
          </el-badge>
          <span class="header-icon material-symbols-outlined" @click="$router.push({ name: 'ComplianceReport', params: { projectId: currentProjectId } })">analytics</span>
          <div class="user-info">
            <div class="user-text">
              <p class="user-name">{{ authStore.user?.username || '用户' }}</p>
              <p class="user-role">采购主管</p>
            </div>
            <el-avatar :size="36" class="user-avatar">
              {{ (authStore.user?.username || 'U').charAt(0).toUpperCase() }}
            </el-avatar>
          </div>
          <el-button text @click="handleLogout">
            <span class="material-symbols-outlined">logout</span>
            退出
          </el-button>
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
import { ref, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const activeNav = ref('ProjectList')
const searchQuery = ref('')

// Current project ID for compliance report link
const currentProjectId = computed(() => route.params.id)

const navItems = [
  { name: 'ProjectList', label: '项目管理', icon: 'folder_managed' },
  { name: 'CompanyMaterials', label: '企业文档', icon: 'archive' },
  { name: 'NewProject', label: '新建项目', icon: 'add_circle' }
]

// Sync active nav with route changes
watch(() => route.name, (newName) => {
  if (newName) activeNav.value = newName
})

function handleLogout() {
  authStore.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
}

/* Sidebar */
.sidebar {
  width: 260px;
  height: 100vh;
  position: fixed;
  left: 0;
  top: 0;
  background: var(--surface-container-lowest);
  border-right: 1px solid var(--outline-variant);
  display: flex;
  flex-direction: column;
  padding: 24px 16px;
  z-index: 60;
}

.sidebar-header {
  margin-bottom: 40px;
  padding: 0 8px;
}

.sidebar-logo {
  font-size: 24px;
  font-weight: 700;
  color: var(--primary);
  line-height: 1.2;
}

.sidebar-subtitle {
  font-size: 12px;
  color: var(--on-surface-variant);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-radius: 8px;
  text-decoration: none;
  color: var(--on-surface-variant);
  transition: all 0.2s;
}

.nav-item:hover {
  background: var(--surface-container-high);
}

.nav-item.active {
  color: var(--primary);
  font-weight: 700;
  background: rgba(26, 115, 232, 0.1);
}

.nav-icon {
  margin-right: 12px;
  font-size: 22px;
}

.nav-label {
  font-size: 14px;
}

.sidebar-footer {
  padding: 0 8px;
  margin-top: 16px;
}

.new-project-btn {
  width: 100%;
  border-radius: 12px;
  height: 44px;
  font-weight: 600;
  background-color: var(--primary-container);
  border-color: var(--primary-container);
  color: var(--on-primary-container);
}

/* Main area */
.main-area {
  margin-left: 260px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* Top header */
.top-header {
  height: 64px;
  position: fixed;
  top: 0;
  right: 0;
  left: 260px;
  z-index: 50;
  background: var(--surface);
  border-bottom: 1px solid var(--outline-variant);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
}

.header-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--on-surface);
}

.header-search {
  max-width: 400px;
}

.header-search :deep(.el-input__wrapper) {
  border-radius: 9999px;
  background: var(--surface-container);
  box-shadow: none !important;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 24px;
}

.header-icon {
  cursor: pointer;
  font-size: 24px;
  color: var(--on-surface-variant);
  transition: color 0.2s;
}

.header-icon:hover {
  color: var(--primary);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-left: 16px;
  border-left: 1px solid var(--outline-variant);
}

.user-text {
  text-align: right;
}

.user-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--on-surface);
  line-height: 1.2;
}

.user-role {
  font-size: 11px;
  color: var(--outline);
}

.user-avatar {
  background: var(--primary-fixed);
  color: var(--on-primary-fixed);
  font-weight: 600;
}

/* Content area */
.content-area {
  padding-top: 96px;
  padding-bottom: 48px;
  padding-left: 32px;
  padding-right: 32px;
  flex: 1;
}

/* Element Plus overrides */
:deep(.el-button--primary) {
  --el-button-bg-color: var(--primary);
  --el-button-border-color: var(--primary);
  --el-button-hover-bg-color: var(--primary-container);
}

:deep(.el-tag--success) {
  --el-tag-bg-color: rgba(40, 108, 0, 0.1);
  --el-tag-text-color: var(--tertiary);
}

:deep(.el-tag--warning) {
  --el-tag-bg-color: rgba(251, 188, 4, 0.1);
  --el-tag-text-color: var(--warning-amber, #fbbc04);
}

:deep(.el-tag--danger) {
  --el-tag-bg-color: rgba(186, 26, 26, 0.1);
  --el-tag-text-color: var(--error);
}

:deep(.el-tag--info) {
  --el-tag-bg-color: rgba(94, 94, 96, 0.1);
  --el-tag-text-color: var(--secondary);
}
</style>
