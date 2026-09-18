import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'

// meta.managerOnly：仅管理者/超管可见。注意这只是**体验层**的收口——
// 真正的隔断在服务端（员工拿自己的 token 直接打 /api/stats/overview 会被 403）。
// 前端这套是为了不让员工点进一个只会报错的页面。
const routes = [
  { path: '/login', name: 'login', component: Login },
  { path: '/register', name: 'register', component: () => import('../views/Register.vue') },
  {
    path: '/',
    component: () => import('../layout/AppLayout.vue'),
    redirect: () => {
      const u = JSON.parse(localStorage.getItem('user') || 'null')
      const mgr = u?.role === 'manager' || u?.role === 'super_admin'
      return mgr ? '/dashboard' : '/my-work'
    },
    children: [
      { path: 'my-work', name: 'myWork', component: () => import('../views/MyWork.vue'), meta: { title: '我的填报' } },
      { path: 'my-stats', name: 'myStats', component: () => import('../views/MyStats.vue'), meta: { title: '我的统计' } },
      { path: 'dashboard', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '数据看板', managerOnly: true } },
      { path: 'records', name: 'records', component: () => import('../views/AllRecords.vue'), meta: { title: '全部数据', managerOnly: true } },
      { path: 'review', name: 'review', component: () => import('../views/AccountReview.vue'), meta: { title: '账号审批', managerOnly: true } },
      { path: 'users', name: 'users', component: () => import('../views/UserManage.vue'), meta: { title: '账号管理', managerOnly: true } },
      { path: 'projects', name: 'projects', component: () => import('../views/ProjectManage.vue'), meta: { title: '项目管理', managerOnly: true } },
      { path: 'audit-logs', name: 'auditLogs', component: () => import('../views/AuditLog.vue'), meta: { title: '操作留痕', managerOnly: true } }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  const user = JSON.parse(localStorage.getItem('user') || 'null')
  const isManager = user?.role === 'manager' || user?.role === 'super_admin'

  if (to.path !== '/login' && to.path !== '/register' && !token) return '/login'
  if ((to.path === '/login' || to.path === '/register') && token) return '/'
  if (to.meta.managerOnly && !isManager) return '/my-work'
})

export default router
