<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <span class="logo-mark"><el-icon :size="18" color="#fff"><DataLine /></el-icon></span>
        <span class="logo-text">工作量统计</span>
      </div>
      <div class="logo-line"></div>
      <el-menu :default-active="activeMenu" router class="menu">
        <el-menu-item v-for="item in menu" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
          <el-badge
            v-if="item.path === '/users' && pendingCount > 0"
            :value="pendingCount"
            class="menu-badge"
          />
        </el-menu-item>
      </el-menu>
      <!-- 组长没挂团队时后端给他空集，他登录后什么都看不见。
           不说清楚的话他只会认为系统坏了，所以在菜单底下明写一行。 -->
      <div v-if="auth.role === 'leader' && !auth.user?.team_id" class="team-warn">
        尚未分配团队，暂时看不到下属数据
      </div>
    </el-aside>

    <el-container>
      <el-header class="header">
        <span class="page-title">{{ $route.meta.title }}</span>
        <el-dropdown @command="onCommand">
          <span class="user">
            <span class="user-avatar"><el-icon :size="14"><UserFilled /></el-icon></span>
            <span class="user-name">{{ auth.user?.name || auth.user?.username }}</span>
            <span class="user-role">{{ auth.roleLabelFull }}</span>
            <el-icon class="user-caret"><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <!-- 只读演示账号的常驻提示。放在这里而不是做成一次性弹窗：
           演示往往由别人操作，中途刷新后 toast 就没了，而他并不知道
           自己为什么点不动任何按钮。 -->
      <div v-if="auth.isReadonly" class="readonly-bar">
        <el-icon :size="15"><View /></el-icon>
        <span>当前为只读演示账号，可以浏览全部数据，但不能新增、修改或删除</span>
      </div>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { navFor } from '../constants/nav'
import request from '../api/request'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const pendingCount = ref(0)
const activeMenu = computed(() => route.meta.activeMenu || route.path)

// ★ 菜单来自 NAV，与路由表同一份数据（见 constants/nav.js 的说明）。
//   这里不再有任何 `v-if="auth.isManager"` —— 那种写成否定式的门禁，
//   加一类角色就要全仓改一遍，且「菜单藏了但 URL 还能直接进」一定会漏。
const menu = computed(() => navFor(auth.role))

async function refreshPending() {
  if (!auth.isManager) return
  try {
    const rows = await request.get('/users/pending')
    pendingCount.value = rows.length
  } catch {
    // 顶栏红点拿不到不该打断页面，静默即可
  }
}

onMounted(async () => {
  // 本地缓存的 user 可能是旧的（比如角色被改过），进后台先以服务端为准。
  // 顺带这一步也验证了 token 还有效——失效会被 401 拦截器踢回登录页。
  try {
    await auth.fetchMe()
  } catch {
    return
  }
  // ★ fetchMe 之后角色才确定。若本地缓存里没有 user（比如换了浏览器、
  //   或被清过 localStorage 但 token 还在），beforeEach 会因为没有 role
  //   而放行任意页面。拿到真角色后在这里补一次判定，把人送回他的首页。
  if (!navFor(auth.role).some((i) => i.path === route.path)) {
    router.replace('/')
  }
  refreshPending()
})

// 离开用户管理页后刷新红点
watch(() => route.path, refreshPending)

function onCommand(cmd) {
  if (cmd === 'logout') {
    auth.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
  background: var(--el-bg-color-page);
}

/* —— 侧栏：白底 + 浅边框 ——
   原来是深色渐变 + 右下角一团青色光晕（`::after` 的 radial-gradient）。
   那团光晕在浅色底上就是一块脏斑，随深色一起删掉了。
   品牌识别由 .logo-mark / .logo-line / 菜单选中态那根竖条承担。 */
.aside {
  display: flex;
  flex-direction: column;
  background: #fff;
  border-right: 1px solid var(--el-border-color-light);
  overflow-x: hidden;
  overflow-y: auto;
}

.logo {
  position: relative;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex: 0 0 auto;
}
/* 保留：蓝青渐变方块是本平台的品牌锚点，浅色底上比深色底更清晰 */
.logo-mark {
  width: 30px; height: 30px;
  border-radius: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #409eff, #00c9b0);
  box-shadow: 0 4px 14px rgba(64, 158, 255, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.35);
}
/* ★ 原样式是白→浅蓝的 `background-clip: text` 渐变字。白字在**白底**上
   完全看不见（不是「对比度差」，是纯隐形）。改纯色。 */
.logo-text {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--el-text-color-primary);
}
/* 保留：分隔线是品牌锚点之一 */
.logo-line {
  height: 1px;
  margin: 0 18px 8px;
  background: linear-gradient(90deg, transparent, rgba(64, 158, 255, 0.5), rgba(0, 201, 176, 0.5), transparent);
  flex: 0 0 auto;
}

.menu {
  border-right: none;
  flex: 1 1 auto;
  --el-menu-bg-color: transparent;
  --el-menu-text-color: var(--el-text-color-regular);
  --el-menu-active-color: var(--el-color-primary);
  --el-menu-hover-bg-color: var(--el-fill-color-light);
}
.menu :deep(.el-menu-item) {
  height: 46px;
  margin: 3px 10px;
  border-radius: 10px;
}
.menu :deep(.el-menu-item:hover) { color: var(--el-color-primary); }
.menu :deep(.el-menu-item.is-active) {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  position: relative;
}
/* 保留：选中态左侧那根 3px 竖条 —— 四处品牌锚点里最显眼的一处 */
.menu :deep(.el-menu-item.is-active)::before {
  content: "";
  position: absolute;
  left: 0; top: 9px; bottom: 9px;
  width: 3px;
  border-radius: 3px;
  background: linear-gradient(180deg, #409eff, #00c9b0);
}
.menu :deep(.el-menu-item .el-icon) { font-size: 17px; }
/* 左侧菜单「用户管理」上的待审数量角标。
   ★ Element Plus 把 `.el-badge__content` 的**绝对定位**写在 `.is-fixed` 底下
     （`position:absolute; top:0; right:…; transform:translateY(-50%) translate(100%)`），
     而 `.is-fixed` 只在「角标挂在一个宿主元素右上角」时才加——这里没给默认插槽，
     所以那个 sup 是 **static inline-flex**，老老实实参与行内布局：
     它继承了 `.el-menu-item` 的 56px 行高，被压到那一行的基线上，
     于是角标掉到菜单项底部、看起来浮在下面那一行上（测量的实际位置是
     item.y+33，而菜单项中线在 item.y+23）。
   不去跟 EP 的定位逻辑缠斗（补一个假的宿主元素或手写绝对定位都更脆），
   直接让外层盒子做 flex 容器并复位行高：角标回到菜单项的垂直中线，
   再由 margin-left:auto 贴到右边缘。 */
.menu-badge {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  line-height: 1;
  /* 复位行高还不够：`.el-badge` 自身是 inline-block，作为 flex 子项会被
     `align-items:center` 摆正，但它内部的 sup 仍按 line-height 排——
     所以上面那条 line-height:1 是必需的，不是可选的。 */
}
.menu-badge :deep(.el-badge__content) {
  border: none;
}

.team-warn {
  margin: 8px 14px 14px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--crm-warn);
  background: #fdf6ec;
  border: 1px solid #f0d7a8;
  flex: 0 0 auto;
}

/* 只读演示账号的横幅。
   ★ 用 --crm-warn 那套暖色，不用红色：这不是故障，是「功能被有意关掉」。
     涂成报错红会让人第一反应是系统坏了，然后去点按钮验证——正好是他不该做的。
   ★ 不设 fixed/absolute，就留在文档流里：`.main` 是自动撑高的，
     脱离文档流会直接盖住页面顶部那几行筛选条件。 */
.readonly-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex: 0 0 auto;
  padding: 9px 24px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--crm-warn);
  background: #fdf6ec;
  border-bottom: 1px solid #f0d7a8;
}

/* —— 顶栏：去掉毛玻璃 ——
   深层底上的 `backdrop-filter: blur()` 是为了「内容从半透明栏下透出来」。
   浅色下它只会让滚动的内容变成一片糊影，而且 Safari 上还会掉帧。 */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-light);
}
.page-title {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--el-text-color-primary);
}
/* 保留：标题前的 4px 竖条，与菜单选中态那根是同一套语言 */
.page-title::before {
  content: "";
  display: inline-block;
  width: 4px; height: 16px;
  margin-right: 10px;
  border-radius: 2px;
  vertical-align: -2px;
  background: linear-gradient(180deg, #409eff, #00c9b0);
}
.user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 10px;
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  transition: background 0.2s, border-color 0.2s;
}
.user:hover {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-7);
}
.user-avatar {
  width: 26px; height: 26px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #409eff, #00c9b0);
  color: #fff;
}
.user-name { font-size: 14px; color: var(--el-text-color-primary); }
.user-role {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 999px;
  color: var(--el-color-primary-dark-2);
  background: var(--el-color-primary-light-9);
}

/* ★ 这里原来有两层 radial-gradient 的极光背景。浅色底上它们只会让
   正文区域泛出一层脏黄/脏青，且不同屏幕上看颜色还不一样。整段删掉。 */
.main {
  padding: 20px;
  background: var(--el-bg-color-page);
}
</style>
