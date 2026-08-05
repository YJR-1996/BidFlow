// Route definitions with login guards
import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false, title: 'BidFlow - 登录' }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false, title: 'BidFlow - 注册', mode: 'register' }
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { requiresAuth: true },
    redirect: '/projects',
    children: [
      {
        path: 'projects',
        name: 'ProjectList',
        component: () => import('@/views/ProjectListView.vue'),
        meta: { title: '项目管理' }
      },
      {
        path: 'project/:id',
        name: 'ProjectDetail',
        component: () => import('@/views/ProjectDetailView.vue'),
        props: true,
        meta: { title: '项目详情' }
      },
      {
        path: 'company-materials',
        name: 'CompanyMaterials',
        component: () => import('@/views/CompanyMaterialsView.vue'),
        meta: { title: '企业资料库' }
      },
      {
        path: 'new-project',
        name: 'NewProject',
        component: () => import('@/views/NewProjectView.vue'),
        meta: { title: '新建项目' }
      },
      {
        path: 'compliance',
        name: 'Compliance',
        component: () => import('@/views/ComplianceReportView.vue'),
        meta: { title: '合规核查' }
      },
      {
        path: 'analytics',
        name: 'Analytics',
        component: () => import('@/views/AnalyticsView.vue'),
        meta: { title: '统计报表' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  const auth = useAuthStore()
  
  // If we have a token but no user, try to restore user state from backend (e.g., after page refresh)
  if (auth.token && !auth.user) {
    try {
      await auth.fetchCurrentUser()
    } catch {
      // Token is invalid or expired, clear it
      auth.clearAuth()
    }
  }
  
  if (to.meta.requiresAuth !== false && !auth.isLoggedIn) {
    next('/login')
  } else if ((to.name === 'Login' || to.name === 'Register') && auth.isLoggedIn) {
    next('/')
  } else {
    next()
  }
})

export default router
