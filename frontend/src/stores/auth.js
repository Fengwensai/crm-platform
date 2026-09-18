import { defineStore } from 'pinia'
import request from '../api/request'

// 后端 /auth/login 只回 token（不回用户对象），所以登录后必须再拉一次 /auth/me
// 才知道自己是谁、什么角色。角色决定整个左侧菜单——不能只靠前端猜。
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: JSON.parse(localStorage.getItem('user') || 'null')
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
    role: (s) => s.user?.role || '',
    isManager: (s) => s.user?.role === 'manager' || s.user?.role === 'super_admin',
    isSuper: (s) => s.user?.role === 'super_admin',
    roleLabel: (s) =>
      ({ super_admin: '超级管理员', manager: '管理者', employee: '员工' }[s.user?.role] || '—')
  },
  actions: {
    async login(username, password) {
      const data = await request.post('/auth/login', { username, password })
      this.token = data.access_token
      localStorage.setItem('token', this.token)
      await this.fetchMe()
    },
    async fetchMe() {
      const me = await request.get('/auth/me')
      this.user = me
      localStorage.setItem('user', JSON.stringify(me))
      return me
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    }
  }
})
