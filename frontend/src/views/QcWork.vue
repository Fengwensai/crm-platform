<template>
  <div class="wk">
    <div class="wk-tabs">
      <button class="wk-tab" :class="{ on: tab === 'form' }" @click="tab = 'form'">
        <el-icon><CircleCheck /></el-icon>登记质检
      </button>
      <button class="wk-tab" :class="{ on: tab === 'list' }" @click="tab = 'list'">
        <el-icon><List /></el-icon>质检记录
      </button>
    </div>

    <!-- ————— 登记 ————— -->
    <div v-if="tab === 'form'" class="wk-panel">
      <div class="wk-hd-t" style="margin-bottom: 14px">质检工作量填报</div>
      <div class="wk-form-box">
        <div class="wk-form-title"><el-icon><CircleCheckFilled /></el-icon>填报质检工作量</div>

        <el-form ref="formRef" class="wk-form-fields" :model="form" :rules="rules" label-position="top">
          <el-form-item prop="target_user_id">
            <template #label><el-icon><User /></el-icon>被质检人员</template>
            <!-- ★ 这里用的是**全公司**名单（`?all=true`）。员工之间互相质检是常态，
                 跨组也会有。若按登录者的数据范围收窄，员工的下拉里只剩他自己，
                 而「不能质检自己」又会拦掉那一条——整个页面填不出东西。 -->
            <el-select v-model="form.target_user_id" placeholder="请选择被质检人员" filterable>
              <el-option v-for="u in targets" :key="u.id" :label="optionLabel(u)" :value="u.id" />
            </el-select>
          </el-form-item>

          <el-form-item prop="project_id">
            <template #label><el-icon><OfficeBuilding /></el-icon>质检项目</template>
            <el-select v-model="form.project_id" placeholder="请选择项目">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>

          <el-form-item prop="qc_date">
            <template #label><el-icon><Calendar /></el-icon>质检日期</template>
            <el-date-picker v-model="form.qc_date" type="date" value-format="YYYY-MM-DD" format="YYYY年MM月DD日" placeholder="选择日期" />
          </el-form-item>

          <!-- 条目号和结论各占半行（设计稿就是「上三下二」，
               这两项是这条记录真正的正文，给它们更宽的位置） -->
          <el-form-item prop="item_no">
            <template #label><el-icon><CircleCheck /></el-icon>条目号</template>
            <el-input
              v-model="form.item_no"
              maxlength="64"
              placeholder="请输入条目号"
              @input="scheduleRate"
              @blur="loadRate"
            />
          </el-form-item>

          <el-form-item prop="result">
            <template #label><el-icon><CircleCheck /></el-icon>质检结果</template>
            <el-select v-model="form.result" placeholder="请选择质检结果">
              <el-option label="通过" value="pass" />
              <el-option label="打回" value="reject" />
            </el-select>
          </el-form-item>

          <!-- ★ 「0 条 → 0.0%」是**服务端**算的（空表单也会返回 200 而不是 422），
               前端不做 `total ? x : 0`。那种写法每个调用点都要记得写一次，
               漏一个就是 NaN%。 -->
          <div class="wk-calc">
            <span>
              通过率（自动计算）
              <span v-if="rate.total" class="note">
                该条目历史 {{ rate.total }} 条：通过 {{ rate.passed }} / 打回 {{ rate.rejected }}
              </span>
              <span v-else class="note">该项目下这个条目号还没有历史记录</span>
            </span>
            <b :class="rateState.cls">{{ rateState.text }}</b>
          </div>

          <el-form-item class="full">
            <template #label>备注（可选）</template>
            <el-input v-model="form.remark" maxlength="255" placeholder="添加备注信息..." />
          </el-form-item>

          <p class="wk-foot-tip">质检人恒为你自己，不提供代填——质检记录的内容就是「我看了这份活」。</p>

          <el-button class="wk-save" type="primary" :loading="saving" @click="onSubmit">
            <el-icon><Check /></el-icon>保存质检记录
          </el-button>
        </el-form>
      </div>
    </div>

    <!-- ————— 记录 ————— -->
    <template v-else>
      <div class="wk-cards">
        <div class="wk-card c-blue">
          <div class="k">总记录数 <em>{{ summary.scope_label }}</em></div>
          <div class="v">{{ num(summary.total) }}</div>
        </div>
        <div class="wk-card c-green">
          <div class="k">通过记录</div>
          <div class="v">{{ num(summary.passed) }}</div>
        </div>
        <div class="wk-card c-red">
          <div class="k">打回记录</div>
          <div class="v">{{ num(summary.rejected) }}</div>
        </div>
      </div>

      <div class="wk-panel">
        <div class="wk-panel-hd">
          <span class="wk-hd-t"><el-icon><Filter /></el-icon>筛选条件</span>
          <button class="wk-export" :disabled="exporting" @click="onExport">
            <el-icon><Download /></el-icon>{{ exporting ? '导出中…' : '导出' }}
          </button>
        </div>

        <div class="wk-fields">
          <label class="wk-field">
            <span class="wk-lb"><el-icon><User /></el-icon>被质检人员</span>
            <el-select v-model="fTarget" placeholder="全部人员" clearable filterable @change="reload">
              <el-option v-for="u in people" :key="u.id" :label="u.name" :value="u.id" />
            </el-select>
          </label>

          <label class="wk-field">
            <span class="wk-lb"><el-icon><OfficeBuilding /></el-icon>质检项目</span>
            <el-select v-model="fProject" placeholder="全部项目" clearable @change="reload">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </label>

          <label class="wk-field">
            <span class="wk-lb"><el-icon><Calendar /></el-icon>开始日期</span>
            <el-date-picker v-model="fFrom" type="date" value-format="YYYY-MM-DD" format="YYYY年MM月DD日" placeholder="选择开始日期" @change="reload" />
          </label>
          <label class="wk-field">
            <span class="wk-lb"><el-icon><Calendar /></el-icon>结束日期</span>
            <el-date-picker v-model="fTo" type="date" value-format="YYYY-MM-DD" format="YYYY年MM月DD日" placeholder="选择结束日期" @change="reload" />
          </label>

          <!-- 上面一排与设计稿一致。下面几个是这张表**非做不可**的筛选项：
               质检表上有两个人，「谁检的」和「检了谁」是两件事，
               合成一个笼统的「人员」下拉，迟早被解释成另一端——
               两种解释查出来的行完全不同，而且都不会报错。 -->
          <label v-if="auth.seesOthers" class="wk-field">
            <span class="wk-lb"><el-icon><User /></el-icon>质检人</span>
            <el-select v-model="fInspector" placeholder="全部质检人" clearable filterable @change="reload">
              <el-option v-for="u in people" :key="u.id" :label="u.name" :value="u.id" />
            </el-select>
          </label>

          <!-- 「来源」只给看不到别人的人：他的列表是「我检的 ∪ 我被他检的」并集，
               没有这一项就分不开这两半。管理者有上面两个下拉，自己就是其中一项，
               再给一个「来源」纯属重复。 -->
          <label v-if="!auth.seesOthers" class="wk-field">
            <span class="wk-lb">来源</span>
            <el-select v-model="fSource" placeholder="全部来源" clearable @change="reload">
              <el-option label="我检的" value="mine" />
              <el-option label="我被检的" value="theirs" />
            </el-select>
          </label>

          <label class="wk-field">
            <span class="wk-lb">质检结果</span>
            <el-select v-model="fResult" placeholder="全部结果" clearable @change="reload">
              <el-option label="通过" value="pass" />
              <el-option label="打回" value="reject" />
            </el-select>
          </label>
        </div>
      </div>

      <div class="wk-panel">
        <div class="wk-panel-hd">
          <span class="wk-hd-t">质检记录列表</span>
        </div>

        <el-table class="wk-table" :data="rows" v-loading="loading" empty-text="没有符合条件的记录">
          <el-table-column prop="qc_date" label="日期" width="128" />
          <!-- 设计稿没有这一列，但本列表是并集、管理者还能看全公司，
               不写质检人的话没人知道这条是谁做的。 -->
          <!-- 「我检的」做成同行小尾巴，不做第二行：做成块级元素的话，
               我自己做的那些行会比别人高一倍，行高参差看起来像渲染坏了。 -->
          <el-table-column label="质检人" width="132">
            <template #default="{ row }">
              {{ row.inspector_name }}<span v-if="row.mine" class="wk-dim" style="font-size: 12px"> · 我检的</span>
            </template>
          </el-table-column>
          <el-table-column prop="target_name" label="被质检人员" width="128" />
          <!-- 项目固定宽、备注吃剩余。理由同 AnnotationWork：
               两个都给 min-width 会让短项目名占掉比备注还宽的地方 -->
          <el-table-column prop="project_name" label="项目" width="190" />
          <el-table-column label="条目号" width="110" align="center">
            <template #default="{ row }">
              <span v-if="row.item_no" class="wk-amber">{{ row.item_no }}</span>
              <span v-else class="wk-dim">—</span>
            </template>
          </el-table-column>
          <el-table-column label="质检结果" width="112">
            <template #default="{ row }">
              <span class="wk-pill" :class="row.result === 'pass' ? 'pass' : 'reject'">
                <el-icon><CircleCheck v-if="row.result === 'pass'" /><CircleClose v-else /></el-icon>
                {{ row.result === 'pass' ? '通过' : '打回' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.remark">{{ row.remark }}</span>
              <span v-else class="wk-dim">—</span>
            </template>
          </el-table-column>
          <el-table-column label="标记" width="96">
            <template #default="{ row }">
              <button v-if="row.edited_by_manager" class="wk-mark warn" @click="openHistory(row)">已被修改</button>
              <span v-else class="wk-dim">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="92">
            <template #default="{ row }">
              <el-button link type="primary" :icon="Edit" @click="openEdit(row)" />
              <el-button link type="danger" :icon="Delete" @click="onDelete(row)" />
            </template>
          </el-table-column>
        </el-table>

        <div v-if="total > pageSize" class="wk-pager">
          <el-pagination
            v-model:current-page="page"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next, total"
            @current-change="load"
          />
        </div>
      </div>
    </template>

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
import {
  Calendar, Check, CircleCheck, CircleCheckFilled, CircleClose, Delete, Download,
  Edit, Filter, List, OfficeBuilding, User,
} from '@element-plus/icons-vue'
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

// ★ 必须**解构成顶层 ref**，不能 `const f = usePersistedFilters(...)` 再用 `f.fProject`：
//   放进对象再取的话模板不会自动解包，`v-model` 会绑到 ref 对象本身——
//   表现为「选了但筛选没生效」，而且全程不报错。
//
// ★ 日期**不持久化**：记住一个过去的区间，下次进来就是一张空表，
//   而页面上没有任何地方提示「你上次筛过日期」。与操作留痕页同一个理由。
const { fTarget, fProject, fInspector, fSource, fResult, fFrom, fTo } = usePersistedFilters(
  'qc-filters-v2',
  { fTarget: null, fProject: null, fInspector: null, fSource: null, fResult: null, fFrom: null, fTo: null }
)
// ★ `page` 刻意**不持久化**——刷新回第 1 页。记住页码的话，用户改完数据再刷新
//   会落在一个可能已不存在的页上，看到一张空表却没有任何解释。
const page = ref(1)
const pageSize = 50

const formRef = ref()
// ★ `result` 和 `item_no` **故意不给默认值**（设计稿上这两个都是空下拉 / 空输入）。
//   `result` 给个默认 'pass' 会让「打回」多一次点击，看着像体贴；但质检员连点
//   几十条时漏改一次，就静默记成了一条「通过」——数据里看不出来，因为它长得
//   和正常的通过一模一样。空着 + 必填校验，漏选会当场报错，不会变成错数据。
//   服务端仍允许 `item_no` 为空字符串（标注侧条目号本就可留空），这里只是前端
//   收紧：`(project_id, "")` 会把所有没填条目号的质检聚成同一个通过率桶。
const form = reactive({
  target_user_id: null, project_id: null, qc_date: today(), item_no: '', result: null, remark: '',
})
const rules = {
  target_user_id: [{ required: true, message: '请选择被质检人员', trigger: 'change' }],
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  qc_date: [{ required: true, message: '请选择日期', trigger: 'change' }],
  item_no: [{ required: true, message: '请填写条目号', trigger: 'blur' }],
  result: [{ required: true, message: '请选择结果', trigger: 'change' }],
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
function optionLabel(u) {
  return u.team_name ? `${u.name}（${u.team_name}）` : u.name
}

// 被质检人员下拉里要去掉自己：服务端会 422「不能质检自己」，
// 与其让用户选完再被打回来，不如一开始就不给这一项。
const targets = computed(() => people.value.filter((u) => u.id !== auth.user?.id))

// 百分比取整（设计稿上写的就是「0%」）。一位小数在通过率上是假精度：
// 3 次质检最多也就能分辨到 33%，67% 和 66.7% 给读者的信息量完全一样，
// 却让这个数字看起来比它的样本量更可信。
const rateState = computed(() => {
  const r = rate.value
  // 历史条数太少时把百分比压暗：1/1 = 100% 看起来像「这个条目质量很好」，
  // 实际只是「只检过一次」。数据量不写出来的话，读者会过度解读。
  if (!r.total) return { text: '0%', cls: 'mute' }
  const cls = r.rate >= 0.9 ? 'ok' : r.rate < 0.6 ? 'bad' : ''
  return { text: `${Math.round(r.rate * 100)}%`, cls }
})

function queryParams() {
  const p = {}
  if (fFrom.value) p.date_from = fFrom.value
  if (fTo.value) p.date_to = fTo.value
  if (fProject.value) p.project_id = fProject.value
  if (fResult.value) p.result = fResult.value
  // 「来源」两个选项分别落到服务端的两个独立参数上。
  // 服务端没有笼统的 user_id，这里也就不用为它造一个。
  if (fSource.value === 'mine') p.inspector_id = auth.user?.id
  if (fSource.value === 'theirs') p.target_user_id = auth.user?.id
  // 显式的两个人筛选优先于「来源」快捷项（两者同时给会是 AND，此处按更精确的那个来）
  if (fInspector.value) p.inspector_id = fInspector.value
  if (fTarget.value) p.target_user_id = fTarget.value
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
    item_no: '', result: null, remark: '',
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
