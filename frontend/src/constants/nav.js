/**
 * 菜单与路由的**唯一真相源**。
 *
 * ★ 为什么用一个数组同时驱动两边，而不是在 router 里写 `managerOnly: true`、
 *   在 AppLayout 里再写一遍 `v-if="auth.isManager"`：
 *
 *   否定式的 flag（`managerOnly`）乘上四类角色，就变成一片补集运算——
 *   加第五类角色时要全仓改，而且**「菜单藏了但 URL 还能直接进」一定会漏**。
 *   那种漏法不会报错：组长手敲 `/users` 就进去了，页面上还都是他能看的数据，
 *   谁也不会发现。单数组驱动把这一类从「要记得两边都改」变成「物理上只有一个地方」。
 *
 * ★ `roles` 是**白名单**（谁能进），不是黑名单（谁不能进）。
 *   新增角色时默认什么都不给，必须显式加进来——失败方向偏向锁死。
 */
import { DataAnalysis, EditPen, Stamp, User, Collection } from '@element-plus/icons-vue'

/** 全部角色。管理者两项用数组展开，免得每行都写一遍。 */
const MANAGERS = ['manager', 'super_admin']

export const NAV = [
  {
    path: '/annotations',
    name: 'annotations',
    title: '标注工作量登记',
    icon: EditPen,
    // 四种角色都能进，但进去看到的东西不同（员工只有自己、组长本组、管理者全公司）。
    roles: ['employee', 'leader', ...MANAGERS],
    component: () => import('../views/AnnotationWork.vue'),
  },
  {
    path: '/qc',
    name: 'qc',
    title: '质检工作量登记',
    icon: Stamp,
    roles: ['employee', 'leader', ...MANAGERS],
    component: () => import('../views/QcWork.vue'),
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    title: '数据看板',
    icon: DataAnalysis,
    roles: ['leader', ...MANAGERS],
    component: () => import('../views/Dashboard.vue'),
  },
  {
    path: '/users',
    name: 'users',
    title: '用户管理',
    icon: User,
    roles: MANAGERS,
    component: () => import('../views/UserManage.vue'),
  },
  {
    path: '/projects',
    name: 'projects',
    title: '项目管理',
    icon: Collection,
    roles: MANAGERS,
    component: () => import('../views/ProjectManage.vue'),
  },
]

// ★ v1 的「全部数据」页（`AllRecords.vue`）**没有**进这张表，文件也已删除。
//   管理者的「看到全公司」现在由两个记录页天然提供（它们的接口对他不加范围）。
//   再留一个「全部数据」入口的话，同一个列表就有两个入口、名字暗示的范围还不一样，
//   而且那第二个入口是 v1 的「数量 + 返工量」口径——留在菜单里等于把旧口径
//   又摆回用户面前。删掉页面而不只是藏起来，是为了让 `import` 直接编译不过。

/** 某角色能看到的菜单项（顺序即菜单顺序）。 */
export function navFor(role) {
  return NAV.filter((item) => item.roles.includes(role))
}

/** 某角色能进的路径集合，供路由守卫判定。 */
export function allowedPaths(role) {
  return new Set(NAV.filter((i) => i.roles.includes(role)).map((i) => i.path))
}

/** 登录后该落到哪一页（该角色菜单的第一项）。 */
export function homePath(role) {
  const first = navFor(role)[0]
  return first ? first.path : '/login'
}
