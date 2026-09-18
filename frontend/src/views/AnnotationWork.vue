<template>
  <div class="wk">
    <!-- ————— 两段式 tab —————
         用一个 `tab` 字符串切面板，而不是 el-tabs：设计稿的分段控件是
         「浅灰槽 + 白色选中块」，el-tabs 只有下划线那一套形态。 -->
    <div class="wk-tabs">
      <button class="wk-tab" :class="{ on: tab === 'form' }" @click="tab = 'form'">
        <el-icon><EditPen /></el-icon>登记标注
      </button>
      <button class="wk-tab" :class="{ on: tab === 'list' }" @click="tab = 'list'">
        <el-icon><List /></el-icon>标注记录
      </button>
    </div>

    <!-- ————— 登记 ————— -->
    <div v-if="tab === 'form'" class="wk-panel">
      <div class="wk-hd-t" style="margin-bottom: 14px">标注工作量填报</div>
      <div class="wk-form-box">
        <div class="wk-form-title"><el-icon><CircleCheckFilled /></el-icon>填报标注工作量</div>

        <el-form ref="formRef" class="wk-form-fields" :model="form" :rules="rules" label-position="top">
          <!-- 只有看得到别人的人才给这一项。员工的服务端范围里只有他自己，
               给他一个「登记给谁」只会永远只有一项，纯噪音。 -->
          <el-form-item v-if="auth.seesOthers" prop="user_id">
            <template #label><el-icon><User /></el-icon>登记给谁</template>
            <el-select v-model="form.user_id" placeholder="默认记在自己名下" clearable filterable>
              <el-option
                v-for="u in options"
                :key="u.id"
                :label="u.id === auth.user?.id ? `${u.name}（我自己）` : u.name"
                :value="u.id"
              />
            </el-select>
          </el-form-item>

          <el-form-item prop="project_id">
            <template #label><el-icon><OfficeBuilding /></el-icon>标注项目</template>
            <el-select v-model="form.project_id" placeholder="请选择项目">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>

          <el-form-item prop="work_date">
            <template #label><el-icon><Calendar /></el-icon>标注日期</template>
            <el-date-picker v-model="form.work_date" type="date" value-format="YYYY-MM-DD" format="YYYY年MM月DD日" placeholder="选择日期" />
          </el-form-item>

          <el-form-item prop="item_no">
            <template #label><el-icon><CircleCheck /></el-icon>条目号</template>
            <el-input v-model="form.item_no" maxlength="64" placeholder="请输入条目号（可留空）" />
          </el-form-item>

          <el-form-item>
            <template #label><el-icon><Grid /></el-icon>2D 框数</template>
            <el-input-number v-model="form.box2d" :controls="false" :min="0" :max="1000000" />
          </el-form-item>

          <el-form-item>
            <template #label><el-icon><Box /></el-icon>3D 框数</template>
            <el-input-number v-model="form.box3d" :controls="false" :min="0" :max="1000000" />
          </el-form-item>

          <!-- 「合计框数」顶替了设计稿里质检页那一格「通过率（自动计算）」的位置：
               两页的表单是同一个骨架，右对齐的大数字放在同一处，
               切页时视线不用重新找位置。 -->
          <div class="wk-calc">
            <span>合计框数（自动计算）</span>
            <b :class="totalBox ? 'ok' : 'mute'">{{ num(totalBox) }}</b>
          </div>

          <el-form-item class="full">
            <template #label>备注（可选）</template>
            <el-input v-model="form.remark" maxlength="255" placeholder="添加备注信息..." />
          </el-form-item>

          <p v-if="auth.seesOthers" class="wk-foot-tip">
            代组员登记会写入操作留痕，那条记录上会出现「已被修改」标记——被代填的人自己点开就能看到。
          </p>

          <el-button class="wk-save" type="primary" :loading="saving" @click="onSubmit">
            <el-icon><Check /></el-icon>保存标注记录
          </el-button>
        </el-form>
      </div>
    </div>

    <!-- ————— 记录 ————— -->
    <template v-else>
      <!-- 卡片：★ 只受数据范围约束，**不受下面的筛选条约束**。
           设计稿把卡片放在筛选条上面，而「今日工作量」配上「开始日期 = 上个月」
           本就自相矛盾。范围小字（本人 / 本组 / 全公司）由服务端给，前端不自己推。 -->
      <div class="wk-cards">
        <div class="wk-card c-green">
          <div class="k">今日标注人数 <em>{{ summary.scope_label }}</em></div>
          <div class="v">{{ num(summary.today_people) }}</div>
        </div>
        <div class="wk-card c-blue">
          <div class="k">今日工作量</div>
          <div class="v">{{ num(summary.today_box) }}</div>
        </div>
        <div class="wk-card c-amber">
          <div class="k">总工作量</div>
          <div class="v">{{ num(summary.total_box) }}</div>
        </div>
        <div class="wk-card c-purple">
          <div class="k">参与人数</div>
          <div class="v">{{ num(summary.people) }}</div>
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
            <span class="wk-lb"><el-icon><OfficeBuilding /></el-icon>项目</span>
            <el-select v-model="fProject" placeholder="全部项目" clearable @change="reload">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </label>

          <!-- 只有能看到别人的人才给这个下拉。员工的服务端范围里只有他自己，
               给他一个「全部人员」下拉只会永远只有一项。 -->
          <label v-if="auth.seesOthers" class="wk-field">
            <span class="wk-lb"><el-icon><User /></el-icon>人员</span>
            <el-select v-model="fUser" placeholder="全部人员" clearable filterable @change="reload">
              <el-option v-for="u in options" :key="u.id" :label="u.name" :value="u.id" />
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
        </div>
      </div>

      <div class="wk-panel">
        <div class="wk-panel-hd">
          <span class="wk-hd-t">工作量记录列表</span>
        </div>

        <el-table class="wk-table" :data="rows" v-loading="loading" empty-text="没有符合条件的记录">
          <el-table-column prop="work_date" label="日期" width="132" />
          <!-- 「我自己」做成**同行**的小尾巴，不做成第二行：做成块级元素的话，
               自己那几行会比别人的高一倍，「今天做了几条」一眼扫下来会误判行数。
               宽度 130 是为了容下「王乙（乙组长）」这类带组名的长名字不被折断。 -->
          <el-table-column label="人员" width="130">
            <template #default="{ row }">
              {{ row.user_name }}<span v-if="row.user_id === auth.user?.id" class="wk-dim" style="font-size: 12px"> · 我自己</span>
            </template>
          </el-table-column>
          <!-- 项目给固定宽、备注吃剩余：两者都给 min-width 的话，EP 会把余量
               平摊给它们，于是「2D 拉框」这种短文本占掉 250px，比备注还宽 -->
          <el-table-column prop="project_name" label="项目" width="190" />
          <el-table-column label="条目号" width="120" align="center">
            <template #default="{ row }">
              <span v-if="row.item_no" class="wk-amber">{{ row.item_no }}</span>
              <span v-else class="wk-dim">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="box2d" label="2D框数" width="120" align="right" label-class-name="wk-hd-blue">
            <template #default="{ row }"><span class="wk-blue">{{ num(row.box2d) }}</span></template>
          </el-table-column>
          <el-table-column prop="box3d" label="3D框数" width="120" align="right" label-class-name="wk-hd-green">
            <template #default="{ row }"><span class="wk-green">{{ num(row.box3d) }}</span></template>
          </el-table-column>
          <el-table-column label="备注" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.remark">{{ row.remark }}</span>
              <span v-else class="wk-dim">—</span>
            </template>
          </el-table-column>
          <!-- ★ 设计稿里没有这一列。但「疑似重复」和「已被修改」是两个**不标出来
               就会被读错**的状态：前者的规则是「重复允许、只提示」，后者点开能看
               改动前后。删掉它们等于把功能删掉，所以留一列最窄的。 -->
          <el-table-column label="标记" width="104">
            <template #default="{ row }">
              <span v-if="row.suspected_duplicate" class="wk-mark dup" title="同人、同项目、同天、同条目号还有别的记录">疑似重复</span>
              <button v-if="row.edited_by_manager" class="wk-mark warn" @click="openHistory(row)">已被修改</button>
              <span v-if="!row.suspected_duplicate && !row.edited_by_manager" class="wk-dim">—</span>
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
import {
  Box, Calendar, Check, CircleCheck, CircleCheckFilled, Delete, Download,
  Edit, EditPen, Filter, Grid, List, OfficeBuilding, User,
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
const options = ref([])
const loading = ref(false)
const saving = ref(false)
const exporting = ref(false)
const summary = ref({ today_people: 0, today_box: 0, total_box: 0, people: 0, scope_label: '' })

// ★ 必须**解构成顶层 ref**（下面这几个 const），不能写成
//   `const f = usePersistedFilters(...)` 然后用 `f.fProject`——
//   放进对象再取的话模板不会自动解包，`v-model` 会绑到 ref 对象本身，
//   表现为「选了但筛选没生效」，而且全程不报错。
//
// ★ 日期**不持久化**：记住一个过去的区间，下次进来就是一张空表，
//   而页面上没有任何地方提示「你上次筛过日期」。这条与操作留痕页同一个理由。
const { fProject, fUser, fFrom, fTo } = usePersistedFilters('anno-filters-v2', {
  fProject: null,
  fUser: null,
  fFrom: null,
  fTo: null,
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

const totalBox = computed(() => (form.box2d || 0) + (form.box3d || 0))

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
  if (fFrom.value) p.date_from = fFrom.value
  if (fTo.value) p.date_to = fTo.value
  if (fProject.value) p.project_id = fProject.value
  if (fUser.value) p.user_id = fUser.value
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
