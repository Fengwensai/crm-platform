<template>
  <div class="page-wrap">
    <!-- 统计卡：★ 只受数据范围约束，**不受下面的筛选条约束**。
         卡片在筛选条上面，而「今日工作量」配上「开始日期 = 上个月」本就自相矛盾。
         范围小字（本人 / 本组全量 / 全公司）由服务端给，前端不自己推。 -->
    <div class="stat-grid">
      <div class="stat-card">
        <div class="k">今日标注人数 <span class="scope">{{ summary.scope_label }}</span></div>
        <div class="v">{{ summary.today_people }}</div>
      </div>
      <div class="stat-card">
        <div class="k">今日工作量（框）</div>
        <div class="v teal">{{ num(summary.today_box) }}</div>
      </div>
      <div class="stat-card">
        <div class="k">总工作量（框）</div>
        <div class="v">{{ num(summary.total_box) }}</div>
      </div>
      <div class="stat-card">
        <div class="k">参与人数</div>
        <div class="v">{{ summary.people }}</div>
      </div>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="tab">
        <!-- ————— 登记 ————— -->
        <el-tab-pane label="标注登记" name="form">
          <el-form ref="formRef" :model="form" :rules="rules" label-width="92px" style="max-width: 560px">
            <el-form-item v-if="auth.seesOthers" label="登记给谁">
              <el-select v-model="form.user_id" placeholder="默认记在自己名下" clearable filterable style="width: 100%">
                <el-option
                  v-for="u in options"
                  :key="u.id"
                  :label="u.id === auth.user?.id ? `${u.name}（我自己）` : u.name"
                  :value="u.id"
                />
              </el-select>
              <div class="tip">
                代组员登记会写入操作留痕，那条记录上会出现「已修改」标记——被代填的人自己点开就能看到。
              </div>
            </el-form-item>
            <el-form-item label="项目" prop="project_id">
              <el-select v-model="form.project_id" placeholder="选择项目" style="width: 100%">
                <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="日期" prop="work_date">
              <el-date-picker v-model="form.work_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
            <el-form-item label="条目号">
              <el-input v-model="form.item_no" maxlength="64" placeholder="如 A-001、007（可留空）" />
            </el-form-item>
            <el-form-item label="2D 框数">
              <el-input-number v-model="form.box2d" :min="0" :max="1000000" :step="10" style="width: 100%" />
            </el-form-item>
            <el-form-item label="3D 框数">
              <el-input-number v-model="form.box3d" :min="0" :max="1000000" :step="10" style="width: 100%" />
            </el-form-item>
            <el-form-item label="合计">
              <b class="teal">{{ num((form.box2d || 0) + (form.box3d || 0)) }}</b> 框
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="form.remark" maxlength="255" show-word-limit placeholder="选填" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="onSubmit">提交登记</el-button>
              <el-button @click="resetForm">清空</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- ————— 记录 ————— -->
        <el-tab-pane label="标注记录" name="list">
          <div class="filters">
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              value-format="YYYY-MM-DD"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              size="small"
              style="width: 250px"
              @change="reload"
            />
            <el-select v-model="projectId" placeholder="全部项目" clearable size="small" style="width: 150px" @change="reload">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
            <!-- 只有能看到别人的人才给这个下拉。员工的服务端范围里只有他自己，
                 给他一个「全部员工」下拉只会永远只有一项，纯噪音。 -->
            <el-select
              v-if="auth.seesOthers"
              v-model="userId"
              placeholder="全部人员"
              clearable
              filterable
              size="small"
              style="width: 160px"
              @change="reload"
            >
              <el-option v-for="u in options" :key="u.id" :label="u.name" :value="u.id" />
            </el-select>
            <el-button size="small" :icon="Refresh" @click="reload">刷新</el-button>
            <div class="spacer"></div>
            <span class="hint">共 {{ total }} 条</span>
            <el-button size="small" :icon="Download" :loading="exporting" @click="onExport">导出 CSV</el-button>
          </div>

          <el-table :data="rows" v-loading="loading" stripe empty-text="没有符合条件的记录">
            <el-table-column prop="work_date" label="日期" width="112" />
            <el-table-column label="标注人" width="120">
              <template #default="{ row }">
                {{ row.user_name }}
                <div v-if="row.user_id === auth.user?.id" class="dim" style="font-size: 12px">我自己</div>
              </template>
            </el-table-column>
            <el-table-column prop="project_name" label="项目" min-width="120" />
            <el-table-column label="条目号" width="110">
              <template #default="{ row }">
                <span v-if="row.item_no">{{ row.item_no }}</span>
                <span v-else class="dim">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="box2d" label="2D" width="80" align="right" />
            <el-table-column prop="box3d" label="3D" width="80" align="right" />
            <el-table-column label="合计" width="90" align="right">
              <template #default="{ row }"><b class="teal">{{ num(row.box_total) }}</b></template>
            </el-table-column>
            <el-table-column label="备注" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.remark">{{ row.remark }}</span>
                <span v-else class="dim">—</span>
              </template>
            </el-table-column>
            <el-table-column label="标记" width="150">
              <template #default="{ row }">
                <span v-if="row.suspected_duplicate" class="mini-tag dup" title="同人、同项目、同天、同条目号还有别的记录">疑似重复</span>
                <button v-if="row.edited_by_manager" class="mini-tag warn link" @click="openHistory(row)">
                  已被修改
                </button>
                <span v-if="!row.suspected_duplicate && !row.edited_by_manager" class="dim">—</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openEdit(row)">修改</el-button>
                <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-if="total > pageSize"
            v-model:current-page="page"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next, total"
            style="margin-top: 12px; justify-content: flex-end"
            @current-change="load"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 修改弹窗。★ 没有项目 / 日期：服务端不接受改这两项
         （它们是「疑似重复」探测键，改了等于搬到另一条记录上，还能绕开日期闸门）。 -->
    <el-dialog v-model="dlgVisible" title="修改标注记录" width="460px">
      <el-form label-width="80px">
        <el-form-item label="条目号">
          <el-input v-model="dlg.item_no" maxlength="64" placeholder="可留空" />
        </el-form-item>
        <el-form-item label="2D 框数">
          <el-input-number v-model="dlg.box2d" :min="0" :max="1000000" :step="10" style="width: 100%" />
        </el-form-item>
        <el-form-item label="3D 框数">
          <el-input-number v-model="dlg.box3d" :min="0" :max="1000000" :step="10" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dlg.remark" maxlength="255" show-word-limit placeholder="建议写明改动原因，便于日后追溯" />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="dlg.edited_by_manager"
        type="warning"
        :closable="false"
        show-icon
        title="这是别人的记录，改动会留痕，对方能看到改前改后"
        style="margin-top: 4px"
      />
      <template #footer>
        <el-button @click="dlgVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <RecordHistory
      v-model="histVisible"
      target-type="annotation"
      :target-id="histRow?.id"
      :title="histRow ? `${histRow.user_name} · ${histRow.work_date} · ${histRow.item_no || '无条目号'}` : ''"
      :labels="{ work_date: '日期', item_no: '条目号', box2d: '2D框数', box3d: '3D框数', remark: '备注' }"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Refresh } from '@element-plus/icons-vue'
import request from '../api/request'
import { useAuthStore } from '../stores/auth'
import { usePersistedFilters } from '../composables/usePersistedFilters'
import { downloadFile } from '../utils/download'
import RecordHistory from '../components/RecordHistory.vue'

const auth = useAuthStore()

const tab = ref('form')
const rows = ref([])
const total = ref(0)
const projects = ref([])
const options = ref([])
const loading = ref(false)
const saving = ref(false)
const exporting = ref(false)
const summary = ref({ today_people: 0, today_box: 0, total_box: 0, people: 0, scope_label: '' })

// ★ 必须**解构成顶层 ref**（下面这几个 const），不能写成
//   `const f = usePersistedFilters(...)` 然后用 `f.dateRange`——
//   放进对象再取的话模板不会自动解包，`v-model` 会绑到 ref 对象本身，
//   表现为「选了日期但筛选没生效」，而且不报错。
// 日期区间存成**一个数组**，不拆成两个 key：拆开要写 computed getter/setter，
// 而收益只是 localStorage 里多一个字段，不值。
const { dateRange, projectId, userId } = usePersistedFilters('anno-filters-v1', {
  dateRange: null,
  projectId: null,
  userId: null,
})
// ★ `page` 刻意**不持久化**：刷新回到第 1 页。
//   记住页码的话，用户改了数据再刷新会落在一个可能已经不存在的页上，
//   看到一张空表却没有任何提示。
const page = ref(1)
const pageSize = 50

const formRef = ref()
const form = reactive({
  user_id: null, project_id: null, work_date: today(), item_no: '', box2d: 0, box3d: 0, remark: '',
})
const rules = {
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  work_date: [{ required: true, message: '请选择日期', trigger: 'change' }],
}

const dlgVisible = ref(false)
const dlg = reactive({ id: null, item_no: '', box2d: 0, box3d: 0, remark: '', edited_by_manager: false })

const histVisible = ref(false)
const histRow = ref(null)

function today() {
  // 本地日期。这里用浏览器时区是**对的**：用户看到的「今天」就是他表上的今天。
  // 服务端的 `today_cn()` 是另一回事（它管的是入库与统计口径）。
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
function num(n) {
  return (n ?? 0).toLocaleString('zh-CN')
}

function queryParams() {
  const p = {}
  if (dateRange.value?.length === 2) {
    p.date_from = dateRange.value[0]
    p.date_to = dateRange.value[1]
  }
  if (projectId.value) p.project_id = projectId.value
  if (userId.value) p.user_id = userId.value
  return p
}

async function loadSummary() {
  try {
    summary.value = await request.get('/stats/annotation-summary')
  } catch {
    /* 拦截器已提示 */
  }
}

async function load() {
  loading.value = true
  try {
    const data = await request.get('/annotations', {
      params: { ...queryParams(), limit: pageSize, offset: (page.value - 1) * pageSize },
    })
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

/** 筛选条件一变就回第 1 页。不回的话「共 3 条」配上「第 5 页」会是一张空表。 */
function reload() {
  page.value = 1
  load()
}

async function loadMeta() {
  const [p, o] = await Promise.all([
    request.get('/projects'),
    // ★ 走 /users/options 而不是 /users：后者是管理者专属，
    //   组长拿不到（403），而组长恰恰最需要这个下拉来代填。
    request.get('/users/options'),
  ])
  projects.value = p
  options.value = o
}

async function onSubmit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  if (!form.box2d && !form.box3d) {
    ElMessage.warning('2D 和 3D 框数不能都是 0')
    return
  }
  saving.value = true
  try {
    const payload = {
      project_id: form.project_id,
      work_date: form.work_date,
      item_no: form.item_no,
      box2d: form.box2d || 0,
      box3d: form.box3d || 0,
      remark: form.remark,
    }
    // 只在真的代填时才带 user_id。带一个等于自己的 id 虽然服务端也认，
    // 但会让「这条是代填还是自填」在请求层面失去区分。
    if (form.user_id && form.user_id !== auth.user?.id) payload.user_id = form.user_id
    const saved = await request.post('/annotations', payload)
    // ★ 重复**不是错误**，服务端返回的是 201。这里只是提示一句，绝不阻止提交。
    if (saved.suspected_duplicate) {
      ElMessage.warning('已登记。提示：同一天同一项目下这个条目号已经有记录，请确认是否重复')
    } else {
      ElMessage.success('已登记')
    }
    resetForm()
    await Promise.all([load(), loadSummary()])
  } catch {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    // 代填对象保持住——组长连着补录好几个人的时候，不用每次重选
    user_id: form.user_id,
    project_id: form.project_id,
    work_date: form.work_date,
    item_no: '', box2d: 0, box3d: 0, remark: '',
  })
}

function openEdit(row) {
  Object.assign(dlg, {
    id: row.id, item_no: row.item_no, box2d: row.box2d, box3d: row.box3d,
    remark: row.remark, edited_by_manager: row.user_id !== auth.user?.id,
  })
  dlgVisible.value = true
}

async function onSave() {
  saving.value = true
  try {
    await request.patch(`/annotations/${dlg.id}`, {
      item_no: dlg.item_no, box2d: dlg.box2d, box3d: dlg.box3d, remark: dlg.remark,
    })
    ElMessage.success(dlg.edited_by_manager ? '已修改，改动已留痕' : '已修改')
    dlgVisible.value = false
    await Promise.all([load(), loadSummary()])
  } catch {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.user_name}」在 ${row.work_date} · ${row.project_name} 的记录吗？\n删除后不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await request.delete(`/annotations/${row.id}`)
  ElMessage.success('已删除')
  await Promise.all([load(), loadSummary()])
}

function openHistory(row) {
  histRow.value = row
  histVisible.value = true
}

async function onExport() {
  // ★ 必须自己带 `/api` 前缀：downloadFile 走原生 fetch，不吃 axios 的 baseURL。
  const params = new URLSearchParams(queryParams()).toString()
  await downloadFile(
    `/api/annotations/export${params ? `?${params}` : ''}`,
    `标注记录_${today()}.csv`,
    exporting
  )
}

onMounted(async () => {
  await loadMeta()
  await Promise.all([load(), loadSummary()])
})
</script>

<style scoped>
.filters {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.spacer { flex: 1; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); }
.teal { color: var(--crm-teal); }
.dim { color: var(--el-text-color-placeholder); }
.scope {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  border-radius: 4px;
  padding: 0 5px;
  margin-left: 2px;
}
.tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-top: 4px;
}
/* 「已被修改」是个按钮（点开看历史），所以要把 button 的默认样式压掉 */
.mini-tag.link {
  cursor: pointer;
  font-family: inherit;
}
.mini-tag.link:hover { text-decoration: underline; }
.mini-tag + .mini-tag { margin-left: 4px; }
</style>
