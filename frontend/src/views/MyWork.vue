<template>
  <div class="page-wrap">
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>填报工作数据</span>
          <span class="hint">每人每个项目每天一条，只能补填最近 {{ BACKFILL_DAYS }} 天</span>
        </div>
      </template>

      <el-form :model="form" label-width="76px" class="fill-form">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12" :md="6">
            <el-form-item label="日期" required>
              <el-date-picker
                v-model="form.work_date"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="选择日期"
                :disabled-date="disabledDate"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="6">
            <el-form-item label="项目" required>
              <el-select v-model="form.project_id" placeholder="选择项目" style="width: 100%">
                <el-option
                  v-for="p in projects"
                  :key="p.id"
                  :label="`${p.name}（${p.unit}）`"
                  :value="p.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="12" :sm="12" :md="5">
            <el-form-item label="数量" required>
              <el-input-number v-model="form.amount" :min="0" :max="10000000" :step="100" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :xs="12" :sm="12" :md="4">
            <el-form-item label="返工量">
              <el-input-number v-model="form.rework_amount" :min="0" :max="10000000" :step="10" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="24" :md="3">
            <el-form-item label-width="0">
              <el-button type="primary" :loading="submitting" style="width: 100%" @click="onSubmit">
                提交
              </el-button>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="24">
            <el-form-item label="备注">
              <el-input v-model="form.remark" maxlength="255" show-word-limit placeholder="可不填（如：半天、含返工说明）" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="calc" v-if="form.amount > 0">
          合格量 = {{ form.amount }} − {{ form.rework_amount || 0 }} =
          <b>{{ Math.max(0, (form.amount || 0) - (form.rework_amount || 0)) }}</b>
        </div>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div class="card-head">
          <span>我的填报记录</span>
          <div class="filters">
            <el-date-picker
              v-model="range"
              type="daterange"
              value-format="YYYY-MM-DD"
              range-separator="至"
              start-placeholder="开始"
              end-placeholder="结束"
              size="small"
            />
            <el-select v-model="filterProject" placeholder="全部项目" clearable size="small" style="width: 150px">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
            <el-button size="small" :icon="Refresh" @click="loadRecords">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="records" v-loading="loading" stripe empty-text="还没有填报记录">
        <el-table-column prop="work_date" label="日期" width="120" sortable />
        <el-table-column prop="project_name" label="项目" min-width="140" />
        <el-table-column prop="amount" label="数量" width="100" align="right" />
        <el-table-column prop="rework_amount" label="返工量" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ warn: row.rework_amount > 0 }">{{ row.rework_amount }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="qualified" label="合格量" width="100" align="right">
          <template #default="{ row }"><b class="teal">{{ row.qualified }}</b></template>
        </el-table-column>
        <el-table-column label="备注" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.remark">{{ row.remark }}</span>
            <span v-else class="dim">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.edited_by_manager" type="warning" size="small" effect="dark">
              管理者改过
            </el-tag>
            <span v-else class="dim">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <template v-if="editable(row)">
              <el-button link type="primary" size="small" @click="openEdit(row)">修改</el-button>
              <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
            </template>
            <el-tooltip v-else content="超过可修改期限，如需更正请联系管理员" placement="top">
              <span class="dim">不可改</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editVisible" title="修改填报" width="440px">
      <el-form :model="editForm" label-width="76px">
        <el-form-item label="日期">
          <el-input :model-value="editForm.work_date" disabled />
        </el-form-item>
        <el-form-item label="项目">
          <el-input :model-value="editForm.project_name" disabled />
        </el-form-item>
        <el-form-item label="数量" required>
          <el-input-number v-model="editForm.amount" :min="0" :max="10000000" :step="100" style="width: 100%" />
        </el-form-item>
        <el-form-item label="返工量">
          <el-input-number v-model="editForm.rework_amount" :min="0" :max="10000000" :step="10" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.remark" maxlength="255" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSaveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import request from '../api/request'

const BACKFILL_DAYS = 7

const projects = ref([])
const records = ref([])
const loading = ref(false)
const submitting = ref(false)
const saving = ref(false)
const range = ref(null)
const filterProject = ref(null)

const editVisible = ref(false)
const editForm = reactive({ id: null, work_date: '', project_name: '', amount: 0, rework_amount: 0, remark: '' })

const form = reactive({
  work_date: todayStr(),
  project_id: null,
  amount: null,
  rework_amount: 0,
  remark: ''
})

const minDate = computed(() => {
  const d = new Date()
  d.setDate(d.getDate() - BACKFILL_DAYS)
  d.setHours(0, 0, 0, 0)
  return d
})

function todayStr() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

// 只能填今天往前 7 天，不能填未来（与服务端 BACKFILL_DAYS 一致）
function disabledDate(d) {
  const t = new Date()
  t.setHours(23, 59, 59, 999)
  return d > t || d < minDate.value
}

// 记录是否还在可改期内（服务端对员工只放行最近 7 天）
function editable(row) {
  return row.work_date >= fmtDate(minDate.value)
}

function fmtDate(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

async function loadProjects() {
  projects.value = await request.get('/projects', { params: { status: 'active' } })
  if (!form.project_id && projects.value.length) form.project_id = projects.value[0].id
}

async function loadRecords() {
  loading.value = true
  try {
    const params = {}
    if (range.value?.length === 2) {
      params.date_from = range.value[0]
      params.date_to = range.value[1]
    }
    if (filterProject.value) params.project_id = filterProject.value
    records.value = await request.get('/work-records', { params })
  } finally {
    loading.value = false
  }
}

async function onSubmit() {
  if (!form.work_date) return ElMessage.warning('请选择日期')
  if (!form.project_id) return ElMessage.warning('请选择项目')
  if (form.amount === null || form.amount === undefined) return ElMessage.warning('请填写数量')
  if ((form.rework_amount || 0) > form.amount) return ElMessage.warning('返工量不能大于数量')

  submitting.value = true
  try {
    await request.post('/work-records', {
      project_id: form.project_id,
      work_date: form.work_date,
      amount: form.amount,
      rework_amount: form.rework_amount || 0,
      remark: form.remark
    })
    ElMessage.success('已提交')
    form.amount = null
    form.rework_amount = 0
    form.remark = ''
    await loadRecords()
  } catch {
    // 409（当天该项目已填过）由拦截器提示，用户去列表里改即可
  } finally {
    submitting.value = false
  }
}

function openEdit(row) {
  Object.assign(editForm, {
    id: row.id,
    work_date: row.work_date,
    project_name: row.project_name,
    amount: row.amount,
    rework_amount: row.rework_amount,
    remark: row.remark
  })
  editVisible.value = true
}

async function onSaveEdit() {
  if ((editForm.rework_amount || 0) > editForm.amount) return ElMessage.warning('返工量不能大于数量')
  saving.value = true
  try {
    await request.patch(`/work-records/${editForm.id}`, {
      amount: editForm.amount,
      rework_amount: editForm.rework_amount || 0,
      remark: editForm.remark
    })
    ElMessage.success('已保存')
    editVisible.value = false
    await loadRecords()
  } catch {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除 ${row.work_date} · ${row.project_name} 这条记录吗？删除后不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await request.delete(`/work-records/${row.id}`)
  ElMessage.success('已删除')
  await loadRecords()
}

onMounted(async () => {
  await loadProjects()
  await loadRecords()
})
</script>

<style scoped>
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}
.card-head .hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.filters {
  display: flex;
  gap: 8px;
  align-items: center;
}
.calc {
  margin-left: 76px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.calc b {
  color: var(--crm-teal);
  font-size: 15px;
}
.teal { color: var(--crm-teal); }
.warn { color: var(--crm-warn); }
.dim { color: var(--el-text-color-placeholder); }
</style>
