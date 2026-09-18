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
    isLeader: (s) => s.user?.role === 'leader',
    // 「这个人能看到不止自己」——组长和管理者都是。凡是界面上要问
    // 「要不要给他看别人的名字」的地方一律用它，别写 `!isEmployee`：
    // 那种写法在角色扩到第五种时会静默变成「看不到」或「看得到」，取决于写法。
    seesOthers: (s) =>
      ['leader', 'manager', 'super_admin'].includes(s.user?.role),
    roleLabel: (s) =>
      ({
        super_admin: '超级管理员',
        manager: '管理者',
        leader: '组长',
        employee: '员工'
      }[s.user?.role] || '—'),
    // 没有团队时不要自称「组长」——后端给了他空集，
    // 标签说「组长」会让他在界面上找一整天原因。说清楚配置没配好。
    roleLabelFull: (s) => {
      if (s.user?.role === 'leader' && !s.user?.team_id) return '组长（未分配团队）'
      return ({
        super_admin: '超级管理员',
        manager: '管理者',
        leader: '组长',
        employee: '员工'
      }[s.user?.role] || '—')
    }
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
