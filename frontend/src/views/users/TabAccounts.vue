<template>
  <div>
    <div class="filters">
      <el-input
        v-model="kw"
        placeholder="搜工号 / 姓名"
        clearable
        size="small"
        style="width: 180px"
        :prefix-icon="Search"
      />
      <el-select v-model="fStatus" placeholder="全部状态" clearable size="small" style="width: 130px">
        <el-option label="已启用" value="active" />
        <el-option label="待审批" value="pending" />
        <el-option label="已驳回" value="rejected" />
        <el-option label="已停用" value="disabled" />
      </el-select>
      <el-select v-model="fRole" placeholder="全部角色" clearable size="small" style="width: 140px">
        <el-option label="员工" value="employee" />
        <el-option label="组长" value="leader" />
        <el-option label="管理者" value="manager" />
        <el-option label="超级管理员" value="super_admin" />
      </el-select>
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
      <div class="spacer"></div>
      <span class="hint">共 {{ shown.length }} 个账号</span>
    </div>

    <el-table :data="shown" v-loading="loading" stripe empty-text="没有符合条件的账号">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="工号" width="130" />
      <el-table-column prop="name" label="姓名" width="120" />
      <el-table-column label="角色" width="120">
        <template #default="{ row }">
          <el-tag :type="roleTag(row.role)" size="small" effect="plain">{{ roleName(row.role) }}</el-tag>
          <!-- 组长没挂团队 = 他登录后什么都看不见。这里显式提示，
               否则这个配置疏漏只能等他自己来问「为什么我进去是空的」。 -->
          <div v-if="row.role === 'leader' && !row.team_id" class="warnline">未分配团队</div>
        </template>
      </el-table-column>
      <el-table-column label="团队" width="130">
        <template #default="{ row }">
          <span v-if="row.team_name">{{ row.team_name }}</span>
          <span v-else class="dim">未分配</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="96">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status)" size="small" effect="dark">{{ statusName(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="注册时间" min-width="165">
        <template #default="{ row }">{{ fmt(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="审批备注" min-width="130" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.review_note">{{ row.review_note }}</span>
          <span v-else class="dim">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button
            v-if="row.status === 'active'"
            link
            type="warning"
            size="small"
            :disabled="row.id === me.id"
            @click="setStatus(row, 'disabled')"
          >停用</el-button>
          <el-button
            v-else-if="row.status === 'disabled'"
            link
            type="success"
            size="small"
            @click="setStatus(row, 'active')"
          >启用</el-button>
          <el-button
            link
            type="danger"
            size="small"
            :disabled="row.id === me.id || row.role === 'super_admin'"
            @click="onDelete(row)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="tip">
      停用会<b>立刻生效</b>——对方手上已登录的会话下一次请求就会被踢出，不用等重新登录。<br />
      有标注 / 质检记录的账号<b>删不掉</b>（会提示改用停用）。这是防止历史数据变成孤儿：
      删掉之后那些记录还在，但已经不指向任何人，任何列表都查不到它们，且不报错。<br />
      设「组长」必须同时给他选一个团队，且一个团队只能有一个组长。
    </div>

    <el-dialog v-model="visible" title="编辑账号" width="460px">
      <el-form :model="form" label-width="96px">
        <el-form-item label="工号">
          <el-input :model-value="form.username" disabled />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.name" maxlength="64" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" :disabled="!auth.isSuper" style="width: 100%">
            <el-option label="员工" value="employee" />
            <el-option label="组长" value="leader" />
            <el-option label="管理者" value="manager" />
            <el-option label="超级管理员" value="super_admin" />
          </el-select>
          <div v-if="!auth.isSuper" class="hint">仅超级管理员可调整角色</div>
        </el-form-item>
        <el-form-item label="团队">
          <el-select v-model="form.team_id" clearable placeholder="未分配" style="width: 100%">
            <el-option v-for="t in teams" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <div v-if="form.role === 'leader' && !form.team_id" class="warnline">
            组长必须属于一个团队——没有团队的组长登录后看不到任何数据。
          </div>
        </el-form-item>
        <el-form-item label="重置密码">
          <el-input v-model="form.password" placeholder="留空则不修改，至少 6 位" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import request from '../../api/request'
import { useAuthStore } from '../../stores/auth'
import { usePersistedFilters } from '../../composables/usePersistedFilters'

const auth = useAuthStore()
const me = computed(() => auth.user || {})

const rows = ref([])
const teams = ref([])
const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const kw = ref('')

// ★ 只持久化**状态与角色**两个下拉，`kw` 刻意只留在内存里。
//   把搜索词也存下来的话，用户下次进来看到的是一张被自己上次的搜索词过滤过的表，
//   而搜索框里那几个字很容易被忽略——表现就是「我的员工怎么少了几个」。
//   （这是后台完善 9 那套「筛选本地记忆」唯一不该照抄的一处。）
const { fStatus, fRole } = usePersistedFilters('user-filters-v1', {
  fStatus: null,
  fRole: null,
})

const form = reactive({ id: null, username: '', name: '', role: '', team_id: null, password: '' })

const shown = computed(() => {
  const k = kw.value.trim().toLowerCase()
  if (!k) return rows.value
  return rows.value.filter(
    (r) => r.username.toLowerCase().includes(k) || (r.name || '').toLowerCase().includes(k)
  )
})

const roleName = (r) =>
  ({ super_admin: '超级管理员', manager: '管理者', leader: '组长', employee: '员工' }[r] || r)
const roleTag = (r) =>
  ({ super_admin: 'danger', manager: 'warning', leader: 'success', employee: 'info' }[r] || 'info')
const statusName = (s) =>
  ({ active: '已启用', pending: '待审批', rejected: '已驳回', disabled: '已停用' }[s] || s)
const statusTag = (s) =>
  ({ active: 'success', pending: 'warning', rejected: 'danger', disabled: 'info' }[s] || 'info')
const fmt = (s) => (s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : '—')

async function load() {
  loading.value = true
  try {
    // ★ 状态/角色在**服务端**过滤（能少传一批行），搜索词在本地过滤——
    //   搜索要随着打字即时反应，每敲一个字发一次请求既慢又浪费。
    const params = {}
    if (fStatus.value) params.status = fStatus.value
    if (fRole.value) params.role = fRole.value
    rows.value = await request.get('/users', { params })
  } finally {
    loading.value = false
  }
}

async function loadTeams() {
  try {
    teams.value = await request.get('/teams')
  } catch {
    /* 团队列表拿不到不该让整页空掉 */
  }
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id, username: row.username, name: row.name, role: row.role,
    team_id: row.team_id, password: '',
  })
  visible.value = true
}

async function onSave() {
  if (!form.name.trim()) return ElMessage.warning('姓名不能为空')
  if (form.password && form.password.length < 6) return ElMessage.warning('密码至少 6 位')
  if (form.role === 'leader' && !form.team_id) {
    return ElMessage.warning('组长必须属于一个团队，请先选择团队')
  }
  saving.value = true
  try {
    const payload = { name: form.name.trim(), team_id: form.team_id ?? null }
    if (auth.isSuper) payload.role = form.role
    if (form.password) payload.password = form.password
    await request.patch(`/users/${form.id}`, payload)
    ElMessage.success('已保存')
    visible.value = false
    await load()
  } catch {
    /* 拦截器已提示（如「该团队已有组长」422） */
  } finally {
    saving.value = false
  }
}

async function setStatus(row, status) {
  const verb = status === 'disabled' ? '停用' : '启用'
  try {
    await ElMessageBox.confirm(
      status === 'disabled'
        ? `停用「${row.name}」后，他将无法登录；已登录的会话也会立刻失效。确定吗？`
        : `确定重新启用「${row.name}」吗？`,
      `${verb}确认`,
      { type: 'warning', confirmButtonText: verb, cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await request.patch(`/users/${row.id}`, { status })
  ElMessage.success(`已${verb}`)
  await load()
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除账号「${row.name}（${row.username}）」吗？删除后不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await request.delete(`/users/${row.id}`)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* 有记录时 422，拦截器已提示「改用停用」 */
  }
}

onMounted(async () => {
  await Promise.all([load(), loadTeams()])
})
defineExpose({ load })
</script>

<style scoped>
.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.spacer { flex: 1; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); }
.tip {
  margin-top: 14px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.8;
}
.warnline {
  font-size: 12px;
  color: var(--crm-warn);
  line-height: 1.5;
  margin-top: 4px;
}
.dim { color: var(--el-text-color-placeholder); }
</style>
