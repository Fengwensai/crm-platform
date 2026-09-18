import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import { NAV, allowedPaths, homePath } from '../constants/nav'

// 路由表由 `constants/nav.js` 的 NAV 数组生成——**菜单和路由是同一份数据**。
// 详见 nav.js 顶部的说明：分开写两份的结果必然是「菜单藏了但 URL 还能进」。
//
// ★ 这里仍然只是**体验层**的收口。真正的隔断在服务端：组长手敲别人的记录 ID
//   会拿到 404，员工打 /api/users 会拿到 403。前端这套的作用是不让人点进
//   一个只会报错的页面，不是安全边界。
const routes = [
  { path: '/login', name: 'login', component: Login },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/Register.vue')
  },
  {
    path: '/',
    component: () => import('../layout/AppLayout.vue'),
    // 落到「该角色菜单的第一项」。★ 不再写 `mgr ? '/dashboard' : '/my-work'`——
    // 那种写法每加一个角色就要再加一个分支，而且默认落在哪个页面与菜单顺序
    // 是两处独立的事实，迟早对不上（菜单第一项是标注页，却默认打开看板）。
    redirect: () => {
      const u = JSON.parse(localStorage.getItem('user') || 'null')
      return homePath(u?.role)
    },
    children: NAV.map((item) => ({
      path: item.path.slice(1), // '/annotations' → 'annotations'
      name: item.name,
      component: item.component,
      meta: { title: item.title, roles: item.roles }
    }))
  },
  // 未匹配到的路径回首页。★ 少了这条，手敲一个不存在的地址会得到
  // 一片空白（vue-router 不会自己回退），看起来像页面崩了。
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  const user = JSON.parse(localStorage.getItem('user') || 'null')
  const role = user?.role

  const isAuthPage = to.path === '/login' || to.path === '/register'
  if (!isAuthPage && !token) return '/login'
  if (isAuthPage && token) return '/'
  // 白名单判定（见 nav.js）：roles 里没有这个角色就不让进，
  // 而不是「有 managerOnly 就不让进」那种否定式写法。
  if (role && !isAuthPage && to.meta?.roles && !allowedPaths(role).has(to.path)) {
    return '/'
  }
})

export default router
