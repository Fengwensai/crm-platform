<template>
  <div class="page-wrap">
    <div class="toolbar">
      <span class="page-title">账号管理</span>
      <div class="spacer"></div>
      <el-input v-model="kw" placeholder="搜工号 / 姓名" clearable size="small" style="width: 180px" :prefix-icon="Search" />
      <el-select v-model="fStatus" placeholder="全部状态" clearable size="small" style="width: 130px" @change="load">
        <el-option label="已启用" value="active" />
        <el-option label="待审批" value="pending" />
        <el-option label="已驳回" value="rejected" />
        <el-option label="已停用" value="disabled" />
      </el-select>
      <el-select v-model="fRole" placeholder="全部角色" clearable size="small" style="width: 130px" @change="load">
        <el-option label="员工" value="employee" />
        <el-option label="管理者" value="manager" />
        <el-option label="超级管理员" value="super_admin" />
      </el-select>
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="shown" v-loading="loading" stripe empty-text="没有符合条件的账号">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="工号" width="140" />
        <el-table-column prop="name" label="姓名" width="130" />
        <el-table-column label="角色" width="130">
          <template #default="{ row }">
            <el-tag :type="roleTag(row.role)" size="small" effect="plain">{{ roleName(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
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
        <el-table-column label="操作" width="230" fixed="right">
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
            <el-button link type="danger" size="small" :disabled="row.id === me.id || row.role === 'super_admin'" @click="onDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="tip">
      新增管理者：让对方先走
      <router-link to="/register">员工自助注册</router-link>
      ，审批通过后在这里把角色改成「管理者」。<br />
      停用会立刻生效——对方手上已登录的会话下一次请求就会被踢出，不用等重新登录。<br />
      有填报数据的账号删不掉（会提示改用停用），这是防止历史数据变成孤儿。
    </div>

    <el-dialog v-model="visible" title="编辑账号" width="440px">
      <el-form :model="form" label-width="86px">
        <el-form-item label="工号">
          <el-input :model-value="form.username" disabled />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.name" maxlength="64" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" :disabled="!auth.isSuper" style="width: 100%">
            <el-option label="员工" value="employee" />
            <el-option label="管理者" value="manager" />
            <el-option label="超级管理员" value="super_admin" />
          </el-select>
          <div v-if="!auth.isSuper" class="hint">仅超级管理员可调整角色</div>
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
import request from '../api/request'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const me = computed(() => auth.user || {})

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const kw = ref('')
const fStatus = ref(null)
const fRole = ref(null)

const form = reactive({ id: null, username: '', name: '', role: '', password: '' })

const shown = computed(() => {
  const k = kw.value.trim().toLowerCase()
  if (!k) return rows.value
  return rows.value.filter(
    (r) => r.username.toLowerCase().includes(k) || (r.name || '').toLowerCase().includes(k)
  )
})

const roleName = (r) => ({ super_admin: '超级管理员', manager: '管理者', employee: '员工' }[r] || r)
const roleTag = (r) => ({ super_admin: 'danger', manager: 'warning', employee: 'info' }[r] || 'info')
const statusName = (s) => ({ active: '已启用', pending: '待审批', rejected: '已驳回', disabled: '已停用' }[s] || s)
const statusTag = (s) => ({ active: 'success', pending: 'warning', rejected: 'danger', disabled: 'info' }[s] || 'info')
const fmt = (s) => (s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : '—')

async function load() {
  loading.value = true
  try {
    const params = {}
    if (fStatus.value) params.status = fStatus.value
    if (fRole.value) params.role = fRole.value
    rows.value = await request.get('/users', { params })
  } finally {
    loading.value = false
  }
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id, username: row.username, name: row.name, role: row.role, password: ''
  })
  visible.value = true
}

async function onSave() {
  if (!form.name.trim()) return ElMessage.warning('姓名不能为空')
  if (form.password && form.password.length < 6) return ElMessage.warning('密码至少 6 位')
  saving.value = true
  try {
    const payload = { name: form.name.trim() }
    if (auth.isSuper) payload.role = form.role
    if (form.password) payload.password = form.password
    await request.patch(`/users/${form.id}`, payload)
    ElMessage.success('已保存')
    visible.value = false
    await load()
  } catch {
    /* 拦截器已提示 */
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
    /* 有填报数据时后端返回 422，拦截器已提示「改用停用」 */
  }
}

onMounted(load)
</script>

<style scoped>
.tip {
  margin-top: 14px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.8;
}
.tip a { color: #66b1ff; text-decoration: none; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 4px; }
.dim { color: var(--el-text-color-placeholder); }
</style>
