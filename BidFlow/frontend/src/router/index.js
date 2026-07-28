// Route definitions with login guards
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'ProjectList',
        component: () => import('@/views/ProjectListView.vue')
      },
      {
        path: 'project/:id',
        name: 'ProjectDetail',
        component: () => import('@/views/ProjectDetailView.vue'),
        props: true
      },
      {
        path: 'materials',
        name: 'CompanyMaterials',
        component: () => import('@/views/CompanyMaterialsView.vue')
      },
      {
        path: 'compliance/:projectId',
        name: 'ComplianceReport',
        component: () => import('@/views/ComplianceReportView.vue'),
        props: true
      },
      {
        path: 'new-project',
        name: 'NewProject',
        component: () => import('@/views/NewProjectView.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth !== false && !auth.isLoggedIn) {
    next('/login')
  } else if ((to.name === 'Login' || to.name === 'Register') && auth.isLoggedIn) {
    next('/')
  } else {
    next()
  }
})

export default router
