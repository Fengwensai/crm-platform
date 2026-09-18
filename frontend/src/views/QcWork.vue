<template>
  <div class="page-wrap">
    <div class="stat-grid three">
      <div class="stat-card">
        <div class="k">质检记录数 <span class="scope">{{ summary.scope_label }}</span></div>
        <div class="v">{{ num(summary.total) }}</div>
      </div>
      <div class="stat-card">
        <div class="k">通过</div>
        <div class="v teal">
          {{ num(summary.passed) }}
          <span v-if="summary.total" class="pct">{{ pct(summary.passed, summary.total) }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="k">打回</div>
        <div class="v danger">
          {{ num(summary.rejected) }}
          <span v-if="summary.total" class="pct">{{ pct(summary.rejected, summary.total) }}</span>
        </div>
      </div>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="tab">
        <!-- ————— 登记 ————— -->
        <el-tab-pane label="质检登记" name="form">
          <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" style="max-width: 560px">
            <el-form-item label="被质检人员" prop="target_user_id">
              <!-- ★ 这里用的是**全公司**名单（`?all=true`）。员工之间互相质检是常态，
                   跨组也会有。若按登录者的数据范围收窄，员工的下拉里只剩他自己，
                   而「不能质检自己」又会拦掉那一条——整个页面填不出东西。 -->
              <el-select v-model="form.target_user_id" placeholder="选择被质检的同事" filterable style="width: 100%">
                <el-option v-for="u in targets" :key="u.id" :label="optionLabel(u)" :value="u.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="项目" prop="project_id">
              <el-select v-model="form.project_id" placeholder="选择项目" style="width: 100%">
                <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="日期" prop="qc_date">
              <el-date-picker v-model="form.qc_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
            <el-form-item label="条目号">
              <el-input
                v-model="form.item_no"
                maxlength="64"
                placeholder="如 A-001、007"
                @input="scheduleRate"
                @blur="loadRate"
              />
            </el-form-item>
            <el-form-item label="通过率（自动计算）">
              <!-- ★ 「0 条 → 0.0%」是**服务端**算的（空表单也会返回 200 而不是 422），
                   前端不做 `total ? x : 0`。那种写法每个调用点都要记得写一次，漏一个就是 NaN%。 -->
              <div class="rate-box">
                <b :class="rateState.cls">{{ rateState.text }}</b>
                <span v-if="rate.total" class="dim">
                  （该条目历史 {{ rate.total }} 条：通过 {{ rate.passed }} / 打回 {{ rate.rejected }}）
                </span>
                <span v-else class="dim">（该项目下这个条目号还没有历史记录）</span>
              </div>
            </el-form-item>
            <el-form-item label="结论" prop="result">
              <el-radio-group v-model="form.result">
                <el-radio-button value="pass">通过</el-radio-button>
                <el-radio-button value="reject">打回</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="form.remark" maxlength="255" show-word-limit placeholder="打回时建议写明原因" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="onSubmit">提交登记</el-button>
              <el-button @click="resetForm">清空</el-button>
            </el-form-item>
            <div class="foot-tip">
              质检人恒为你自己，不提供代填——质检记录的内容就是「我看了这份活」。
            </div>
          </el-form>
        </el-tab-pane>

        <!-- ————— 记录 ————— -->
        <el-tab-pane label="质检记录" name="list">
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
            <!-- 来源：列表是**并集**（我检的 ∪ 被检人在我范围内的），
                 不显式分开的话用户会以为「这些全是我做的」。 -->
            <el-select v-model="source" clearable placeholder="全部来源" size="small" style="width: 130px" @change="reload">
              <el-option label="我检的" value="mine" />
              <el-option label="被检的" value="theirs" />
            </el-select>
            <el-select v-model="result" clearable placeholder="全部结论" size="small" style="width: 120px" @change="reload">
              <el-option label="通过" value="pass" />
              <el-option label="打回" value="reject" />
            </el-select>
            <!-- 两个「人」的筛选用**两个独立下拉**，不合并成一个。
                 一张质检表上有两个角色，一个笼统的「人员」下拉迟早被解释成另一端
                 ——两种解释查出来的行完全不同，而且都不会报错。 -->
            <el-select v-if="auth.seesOthers" v-model="inspectorId" clearable filterable placeholder="质检人" size="small" style="width: 140px" @change="reload">
              <el-option v-for="u in people" :key="u.id" :label="u.name" :value="u.id" />
            </el-select>
            <el-select v-if="auth.seesOthers" v-model="targetId" clearable filterable placeholder="被质检人员" size="small" style="width: 150px" @change="reload">
              <el-option v-for="u in people" :key="u.id" :label="u.name" :value="u.id" />
            </el-select>
            <el-button size="small" :icon="Refresh" @click="reload">刷新</el-button>
            <div class="spacer"></div>
            <span class="hint">共 {{ total }} 条</span>
            <el-button size="small" :icon="Download" :loading="exporting" @click="onExport">导出 CSV</el-button>
          </div>

          <el-table :data="rows" v-loading="loading" stripe empty-text="没有符合条件的记录">
            <el-table-column prop="qc_date" label="日期" width="112" />
            <el-table-column label="质检人" width="110">
              <template #default="{ row }">
                {{ row.inspector_name }}
                <div v-if="row.mine" class="dim" style="font-size: 12px">我自己</div>
              </template>
            </el-table-column>
            <el-table-column prop="target_name" label="被质检人员" width="110" />
            <el-table-column prop="project_name" label="项目" min-width="110" />
            <el-table-column label="条目号" width="105">
              <template #default="{ row }">
                <span v-if="row.item_no">{{ row.item_no }}</span>
                <span v-else class="dim">—</span>
              </template>
            </el-table-column>
            <el-table-column label="结论" width="86">
              <template #default="{ row }">
                <el-tag :type="row.result === 'pass' ? 'success' : 'danger'" size="small" effect="light">
                  {{ row.result === 'pass' ? '通过' : '打回' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="来源" width="80">
              <template #default="{ row }">
                <span class="mini-tag" :class="row.mine ? 'mine' : 'other'">{{ row.mine ? '我检的' : '被检的' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.remark">{{ row.remark }}</span>
                <span v-else class="dim">—</span>
              </template>
            </el-table-column>
            <el-table-column label="标记" width="110">
              <template #default="{ row }">
                <button v-if="row.edited_by_manager" class="mini-tag warn link" @click="openHistory(row)">已被修改</button>
                <span v-else class="dim">—</span>
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

    <!-- 修改弹窗：只有条目号 / 结论 / 备注。
         ★ 服务端不接受改被质检人、质检人、项目、日期——前两个是**归属**
         （改了等于把这条工作记到别人头上），后两个是通过率的**聚合键**
         （通过率按 `project_id + item_no` 分组，改它等于改写历史口径）。
         所以这里连输入框都不给，而不是给了再等 422。 -->
    <el-dialog v-model="dlgVisible" title="修改质检记录" width="460px">
      <el-form label-width="100px">
        <el-form-item label="条目号">
          <el-input v-model="dlg.item_no" maxlength="64" placeholder="可留空" />
        </el-form-item>
        <el-form-item label="结论">
          <el-radio-group v-model="dlg.result">
            <el-radio-button value="pass">通过</el-radio-button>
            <el-radio-button value="reject">打回</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dlg.remark" maxlength="255" show-word-limit placeholder="建议写明改动原因，便于日后追溯" />
        </el-form-item>
      </el-form>
      <el-alert
        v-if="!dlg.mine"
        type="warning"
        :closable="false"
        show-icon
        title="这是别人提交的质检记录，改动会留痕，对方能看到改前改后"
        style="margin-top: 4px"
      />
      <template #footer>
        <el-button @click="dlgVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <RecordHistory
      v-model="histVisible"
      target-type="qc_record"
      :target-id="histRow?.id"
      :title="histRow ? `${histRow.inspector_name} → ${histRow.target_name} · ${histRow.qc_date}` : ''"
      :labels="{ qc_date: '日期', item_no: '条目号', result: '结论', remark: '备注' }"
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
const people = ref([])
const loading = ref(false)
const saving = ref(false)
const exporting = ref(false)
const summary = ref({ total: 0, passed: 0, rejected: 0, scope_label: '' })
const rate = ref({ total: 0, passed: 0, rejected: 0, rate: 0 })

// ★ 必须**解构成顶层 ref**，不能 `const f = usePersistedFilters(...)` 再用 `f.dateRange`：
//   放进对象再取的话模板不会自动解包，`v-model` 会绑到 ref 对象本身——
//   表现为「选了日期但筛选没生效」，而且全程不报错。
const { dateRange, projectId, source, result, inspectorId, targetId } = usePersistedFilters('qc-filters-v1', {
  dateRange: null,
  projectId: null,
  source: null,
  result: null,
  inspectorId: null,
  targetId: null,
})
// ★ `page` 刻意**不持久化**——刷新回第 1 页。记住页码的话，用户改完数据再刷新
//   会落在一个可能已不存在的页上，看到一张空表却没有任何解释。
const page = ref(1)
const pageSize = 50

const formRef = ref()
const form = reactive({
  target_user_id: null, project_id: null, qc_date: today(), item_no: '', result: 'pass', remark: '',
})
const rules = {
  target_user_id: [{ required: true, message: '请选择被质检人员', trigger: 'change' }],
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  qc_date: [{ required: true, message: '请选择日期', trigger: 'change' }],
  result: [{ required: true, message: '请选择结论', trigger: 'change' }],
}

const dlgVisible = ref(false)
const dlg = reactive({ id: null, item_no: '', result: 'pass', remark: '', mine: true })

const histVisible = ref(false)
const histRow = ref(null)

let rateTimer = null

function today() {
  // 本地日期（用户看到的「今天」是他表上的今天）；服务端的 today_cn() 管入库与统计口径。
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
function num(n) {
  return (n ?? 0).toLocaleString('zh-CN')
}
function pct(part, whole) {
  if (!whole) return ''
  return `${((part / whole) * 100).toFixed(1)}%`
}
function optionLabel(u) {
  return u.team_name ? `${u.name}（${u.team_name}）` : u.name
}

// 被质检人员下拉里要去掉自己：服务端会 422「不能质检自己」，
// 与其让用户选完再被打回来，不如一开始就不给这一项。
const targets = computed(() => people.value.filter((u) => u.id !== auth.user?.id))

const rateState = computed(() => {
  const r = rate.value
  // 历史条数太少时把百分比压暗并加一句说明：1/1 = 100% 看起来像「这个条目质量很好」，
  // 实际只是「只检过一次」。数据量不写出来的话，读者会过度解读。
  if (!r.total) return { text: '0.0%', cls: 'dim' }
  const cls = r.rate >= 0.9 ? 'teal' : r.rate < 0.6 ? 'danger' : ''
  return { text: `${(r.rate * 100).toFixed(1)}%`, cls }
})

function queryParams() {
  const p = {}
  if (dateRange.value?.length === 2) {
    p.date_from = dateRange.value[0]
    p.date_to = dateRange.value[1]
  }
  if (projectId.value) p.project_id = projectId.value
  if (result.value) p.result = result.value
  // 「来源」两个选项分别落到服务端的两个独立参数上。
  // 服务端没有笼统的 user_id，这里也就不用为它造一个。
  if (source.value === 'mine') p.inspector_id = auth.user?.id
  if (source.value === 'theirs') p.target_user_id = auth.user?.id
  // 显式的两个人筛选优先于「来源」快捷项（两者同时给会是 AND，此处按更精确的那个来）
  if (inspectorId.value) p.inspector_id = inspectorId.value
  if (targetId.value) p.target_user_id = targetId.value
  return p
}

async function loadRate() {
  // ★ 无条件调用：表单没填全时服务端返回 `{total:0, rate:0.0}` 而不是 422，
  //   就是为了让这里不需要写 `if (两个字段都填了)` 这种条件。
  //   条件写在前端的话，「通过率显示的是上一次的结果」这种陈旧数据根本看不出来。
  try {
    rate.value = await request.get('/qc-records/pass-rate', {
      params: { project_id: form.project_id, item_no: form.item_no },
    })
  } catch {
    /* 拦截器已提示 */
  }
}

/** 条目号是打字输入的，逐字发请求会很浪费。合并 300ms 内的连续输入。 */
function scheduleRate() {
  clearTimeout(rateTimer)
  rateTimer = setTimeout(loadRate, 300)
}

async function loadSummary() {
  try {
    summary.value = await request.get('/stats/qc-summary')
  } catch {
    /* 拦截器已提示 */
  }
}

async function load() {
  loading.value = true
  try {
    const data = await request.get('/qc-records', {
      params: { ...queryParams(), limit: pageSize, offset: (page.value - 1) * pageSize },
    })
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

/** 筛选一变就回第 1 页，否则「共 3 条」配上「第 5 页」是一张空表。 */
function reload() {
  page.value = 1
  load()
}

async function loadMeta() {
  const [p, u] = await Promise.all([
    request.get('/projects'),
    // ★ 全量名单（`?all=true`）。一张质检表上「谁检的」「检了谁」都可能是任何人
    //   ——跨组质检是允许的——所以按登录者范围收窄的下拉会恰好藏起
    //   那些他看得见其记录的人。
    request.get('/users/options', { params: { all: true } }),
  ])
  projects.value = p
  people.value = u
}

async function onSubmit() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    await request.post('/qc-records', {
      target_user_id: form.target_user_id,
      project_id: form.project_id,
      qc_date: form.qc_date,
      item_no: form.item_no,
      result: form.result,
      remark: form.remark,
    })
    ElMessage.success('已登记')
    resetForm()
    await Promise.all([load(), loadSummary(), loadRate()])
  } catch {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    // 被质检人和项目保持住：连着检同一个项目的多个条目时，不用每次重选
    target_user_id: form.target_user_id,
    project_id: form.project_id,
    qc_date: form.qc_date,
    item_no: '', result: 'pass', remark: '',
  })
  loadRate()
}

function openEdit(row) {
  Object.assign(dlg, {
    id: row.id, item_no: row.item_no, result: row.result, remark: row.remark,
    // ★ `mine` 取的是「我是这条记录的**作者**吗」。用被质检人判的话，
    //   组长给自己组员录一条质检再编辑，会看到「这是别人的记录」的警告——
    //   而那条记录的作者明明就是他自己。
    mine: row.mine,
  })
  dlgVisible.value = true
}

async function onSave() {
  saving.value = true
  try {
    await request.patch(`/qc-records/${dlg.id}`, {
      item_no: dlg.item_no, result: dlg.result, remark: dlg.remark,
    })
    ElMessage.success(dlg.mine ? '已修改' : '已修改，改动已留痕')
    dlgVisible.value = false
    await Promise.all([load(), loadSummary(), loadRate()])
  } catch {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.inspector_name} → ${row.target_name}」在 ${row.qc_date} 的质检记录吗？\n删除后不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await request.delete(`/qc-records/${row.id}`)
  ElMessage.success('已删除')
  await Promise.all([load(), loadSummary(), loadRate()])
}

function openHistory(row) {
  histRow.value = row
  histVisible.value = true
}

async function onExport() {
  // ★ 必须自己带 `/api` 前缀：downloadFile 走的是**原生 fetch**，不吃 axios 的 baseURL。
  const params = new URLSearchParams(queryParams()).toString()
  await downloadFile(
    `/api/qc-records/export${params ? `?${params}` : ''}`,
    `质检记录_${today()}.csv`,
    exporting
  )
}

onMounted(async () => {
  await loadMeta()
  await Promise.all([load(), loadSummary(), loadRate()])
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
.danger { color: var(--crm-danger); }
.dim { color: var(--el-text-color-placeholder); }
.pct {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  margin-left: 6px;
}
.scope {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  border-radius: 4px;
  padding: 0 5px;
  margin-left: 2px;
}
.rate-box { line-height: 22px; }
.rate-box b { font-size: 17px; }
.foot-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
  margin-left: 110px;
}
/* 「已被修改」是个按钮（点开看历史），要把 button 的默认样式压掉 */
.mini-tag.link {
  cursor: pointer;
  font-family: inherit;
}
.mini-tag.link:hover { text-decoration: underline; }
</style>
