<template>
  <div class="page-wrap">
    <div class="toolbar">
      <span class="page-title">全部数据</span>
      <span class="page-sub" style="margin: 0">
        管理者的每一次代填 / 修改 / 删除都会记入「操作留痕」
      </span>
      <div class="spacer"></div>
      <el-button type="primary" size="small" :icon="Plus" @click="openCreate">代员工补录</el-button>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="filters">
          <el-date-picker
            v-model="range"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            size="small"
            @change="load"
          />
          <el-select v-model="filterUser" placeholder="全部员工" clearable filterable size="small" style="width: 170px" @change="load">
            <el-option v-for="u in employees" :key="u.id" :label="`${u.name}（${u.username}）`" :value="u.id" />
          </el-select>
          <el-select v-model="filterProject" placeholder="全部项目" clearable size="small" style="width: 160px" @change="load">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
          <div class="spacer"></div>
          <span class="hint">共 {{ records.length }} 条</span>
        </div>
      </template>

      <el-table :data="records" v-loading="loading" stripe empty-text="没有符合条件的数据">
        <el-table-column prop="work_date" label="日期" width="115" sortable />
        <el-table-column label="员工" width="140">
          <template #default="{ row }">
            {{ row.user_name }}
            <div class="dim" style="font-size: 12px">{{ usernameOf(row.user_id) }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="project_name" label="项目" min-width="130" />
        <el-table-column prop="amount" label="总量" width="100" align="right" sortable />
        <el-table-column prop="rework_amount" label="返工" width="85" align="right">
          <template #default="{ row }">
            <span :class="{ warn: row.rework_amount > 0 }">{{ row.rework_amount }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="qualified" label="合格量" width="100" align="right">
          <template #default="{ row }"><b class="teal">{{ row.qualified }}</b></template>
        </el-table-column>
        <el-table-column label="备注" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.remark">{{ row.remark }}</span>
            <span v-else class="dim">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.edited_by_manager" type="warning" size="small" effect="dark">已修改</el-tag>
            <span v-else class="dim">原始</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">修改</el-button>
            <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 代填 / 修改 共用一个弹窗 -->
    <el-dialog v-model="dlgVisible" :title="dlgMode === 'create' ? '代员工补录' : '修改数据'" width="460px">
      <el-form :model="dlg" label-width="76px">
        <el-form-item label="员工" required>
          <el-select
            v-model="dlg.user_id"
            placeholder="选择员工"
            filterable
            :disabled="dlgMode === 'edit'"
            style="width: 100%"
          >
            <el-option v-for="u in employees" :key="u.id" :label="`${u.name}（${u.username}）`" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="项目" required>
          <el-select v-model="dlg.project_id" placeholder="选择项目" :disabled="dlgMode === 'edit'" style="width: 100%">
            <el-option v-for="p in projects" :key="p.id" :label="`${p.name}（${p.unit}）`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期" required>
          <el-date-picker
            v-model="dlg.work_date"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled="dlgMode === 'edit'"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="数量" required>
          <el-input-number v-model="dlg.amount" :min="0" :max="10000000" :step="100" style="width: 100%" />
        </el-form-item>
        <el-form-item label="返工量">
          <el-input-number v-model="dlg.rework_amount" :min="0" :max="10000000" :step="10" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dlg.remark" maxlength="255" show-word-limit placeholder="建议写明改动原因，便于日后追溯" />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="dlgMode === 'edit'"
        type="warning"
        :closable="false"
        show-icon
        title="将记录改动前后的数值，员工端会看到「管理者改过」标记"
        style="margin-top: 4px"
      />
      <template #footer>
        <el-button @click="dlgVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import request from '../api/request'

const records = ref([])
const employees = ref([])
const projects = ref([])
const loading = ref(false)
const saving = ref(false)

const range = ref(null)
const filterUser = ref(null)
const filterProject = ref(null)

const dlgVisible = ref(false)
const dlgMode = ref('create')
const dlg = reactive({
  id: null, user_id: null, project_id: null, work_date: null,
  amount: null, rework_amount: 0, remark: ''
})

function usernameOf(id) {
  return employees.value.find((u) => u.id === id)?.username || ''
}

async function loadMeta() {
  const [u, p] = await Promise.all([
    request.get('/users', { params: { status: 'active' } }),
    request.get('/projects')
  ])
  // 在岗账号都能填报（管理者自己也下项目），所以这里不按角色过滤
  employees.value = u
  projects.value = p
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (range.value?.length === 2) {
      params.date_from = range.value[0]
      params.date_to = range.value[1]
    }
    if (filterUser.value) params.user_id = filterUser.value
    if (filterProject.value) params.project_id = filterProject.value
    records.value = await request.get('/work-records', { params })
  } finally {
    loading.value = false
  }
}

function openCreate() {
  dlgMode.value = 'create'
  Object.assign(dlg, {
    id: null, user_id: filterUser.value || null, project_id: filterProject.value || null,
    work_date: new Date().toISOString().slice(0, 10), amount: null, rework_amount: 0, remark: ''
  })
  dlgVisible.value = true
}

function openEdit(row) {
  dlgMode.value = 'edit'
  Object.assign(dlg, {
    id: row.id, user_id: row.user_id, project_id: row.project_id, work_date: row.work_date,
    amount: row.amount, rework_amount: row.rework_amount, remark: row.remark
  })
  dlgVisible.value = true
}

async function onSave() {
  if (!dlg.user_id) return ElMessage.warning('请选择员工')
  if (!dlg.project_id) return ElMessage.warning('请选择项目')
  if (!dlg.work_date) return ElMessage.warning('请选择日期')
  if (dlg.amount === null || dlg.amount === undefined) return ElMessage.warning('请填写数量')
  if ((dlg.rework_amount || 0) > dlg.amount) return ElMessage.warning('返工量不能大于数量')

  saving.value = true
  try {
    if (dlgMode.value === 'create') {
      await request.post('/work-records', {
        user_id: dlg.user_id,
        project_id: dlg.project_id,
        work_date: dlg.work_date,
        amount: dlg.amount,
        rework_amount: dlg.rework_amount || 0,
        remark: dlg.remark
      })
      ElMessage.success('已代填')
    } else {
      await request.patch(`/work-records/${dlg.id}`, {
        amount: dlg.amount,
        rework_amount: dlg.rework_amount || 0,
        remark: dlg.remark
      })
      ElMessage.success('已修改，改动已留痕')
    }
    dlgVisible.value = false
    await load()
  } catch {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.user_name}」在 ${row.work_date} · ${row.project_name} 的记录吗？\n删除会被记入操作留痕，但数据本身不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await request.delete(`/work-records/${row.id}`)
  ElMessage.success('已删除并留痕')
  await load()
}

onMounted(async () => {
  await loadMeta()
  await load()
})
</script>

<style scoped>
.filters {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.hint { font-size: 12px; color: var(--el-text-color-secondary); }
.teal { color: var(--crm-teal); }
.warn { color: var(--crm-warn); }
.dim { color: var(--el-text-color-placeholder); }
</style>
