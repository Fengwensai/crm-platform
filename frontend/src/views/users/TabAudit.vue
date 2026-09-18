<template>
  <div>
    <div class="filters">
      <el-select v-model="fAction" placeholder="全部动作" clearable size="small" style="width: 165px" @change="reload">
        <el-option v-for="a in actions" :key="a" :label="a" :value="a" />
      </el-select>
      <el-select v-model="fTarget" placeholder="全部对象" clearable size="small" style="width: 140px" @change="reload">
        <el-option v-for="t in targets" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-date-picker
        v-model="range"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始"
        end-placeholder="结束"
        size="small"
        @change="reload"
      />
      <el-button size="small" :icon="Refresh" @click="reload">刷新</el-button>
      <div class="spacer"></div>
      <span class="hint">共 {{ rows.length }} 条</span>
    </div>

    <el-table :data="rows" v-loading="loading" stripe empty-text="没有符合条件的记录">
      <el-table-column label="时间" width="165">
        <template #default="{ row }">{{ fmt(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="actor_name" label="操作人" width="110" />
      <el-table-column label="动作" width="130">
        <template #default="{ row }">
          <el-tag :type="actionTag(row.action)" size="small" effect="dark">{{ row.action }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="对象" width="130">
        <template #default="{ row }">
          <span class="dim">{{ targetName(row.target_type) }}{{ row.target_id ? ` #${row.target_id}` : '' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="summary" label="说明" min-width="200" show-overflow-tooltip />
      <el-table-column label="改动" min-width="280">
        <template #default="{ row }">
          <div v-if="diffRows(row).length" class="diff">
            <div v-for="d in diffRows(row)" :key="d.k" class="diff-line">
              <span class="diff-k">{{ d.label }}</span>
              <span class="old">{{ d.before }}</span>
              <span class="arrow">→</span>
              <span class="after">{{ d.after }}</span>
            </div>
          </div>
          <el-button v-else-if="hasDetail(row)" link type="primary" size="small" @click="openDetail(row)">
            查看详情
          </el-button>
          <span v-else class="dim">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="来源 IP" width="130" />
    </el-table>

    <div class="tip">
      管理者与组长动员工数据的每一次都在这里，含改动前后的数值。<br />
      员工不需要来这里翻——他自己那几条记录上会直接出现「已修改」标记，点开就能看到改前改后。
      能从记录里看到的，就不该要求人去日志里找。
    </div>

    <el-dialog v-model="detailVisible" title="操作详情" width="520px">
      <pre class="json">{{ prettyDetail }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import request from '../../api/request'
import { usePersistedFilters } from '../../composables/usePersistedFilters'

const rows = ref([])
const loading = ref(false)
const detailVisible = ref(false)
const cur = ref({})

// 动作与对象都持久化：审计页最常见的用法就是「盯住某一类动作反复来看」。
// 日期区间不持久化——记住一个过去的区间，下次进来会看到一张空表。
const { fAction, fTarget, range } = usePersistedFilters('audit-filters-v1', {
  fAction: null,
  fTarget: null,
  range: null,
})

// ★ 这里列的是**服务端真实会写入的**动作串。v1 的这份清单里写着「驳回注册」，
//   而代码写的是「审批驳回」——那个筛选项永远是 0 条，且看起来像「没人被驳回过」。
//   清单要与 `grep 'action="' app/routers/*.py` 对齐。
const actions = [
  '代填标注数据', '修改标注数据', '删除标注数据',
  '修改质检数据', '删除质检数据',
  '审批通过', '审批驳回', '修改账号', '删除账号',
  '新建团队', '修改团队', '删除团队',
  '新建项目', '修改项目', '删除项目',
  '代填工作数据', '修改工作数据', '删除工作数据',
]

const targets = [
  { value: 'annotation', label: '标注记录' },
  { value: 'qc_record', label: '质检记录' },
  { value: 'user', label: '账号' },
  { value: 'team', label: '团队' },
  { value: 'project', label: '项目' },
  { value: 'work_record', label: '工作记录（旧）' },
]
const targetMap = Object.fromEntries(targets.map((t) => [t.value, t.label]))
const targetName = (t) => targetMap[t] || t || '—'

const actionTag = (a) => {
  if (a.startsWith('删除')) return 'danger'
  if (a.startsWith('修改') || a.startsWith('代填')) return 'warning'
  if (a.startsWith('审批通过')) return 'success'
  return 'info'
}

const fmt = (s) => (s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : '—')

// 双轨 + v1 的字段名。与 `_snapshot()` 里的键对齐（annotations.py / qc.py / work_records.py）。
const FIELD = {
  work_date: '日期', qc_date: '日期',
  item_no: '条目号',
  box2d: '2D 框数', box3d: '3D 框数',
  result: '结论',
  remark: '备注',
  amount: '总量', rework_amount: '返工量',
  name: '名称', status: '状态',
}
const VALUE = { pass: '通过', reject: '打回' }

const prettyDetail = computed(() => JSON.stringify(cur.value.detail || {}, null, 2))

function hasDetail(row) {
  return !!row.detail && Object.keys(row.detail).length > 0
}

function show(v) {
  if (v === null || v === undefined || v === '') return '（空）'
  return VALUE[v] ?? String(v)
}

/** 只列出**真正变了**的字段。
 *  ★ 服务端的 before/after 是整份快照（含没改的字段），全列出来的话，
 *    「改前改后」两栏会一片相同，真正的那一处改动淹在里面。 */
function diffRows(row) {
  const before = row.detail?.before
  const after = row.detail?.after
  if (!before || !after) return []
  return Object.keys(after)
    .filter((k) => before[k] !== after[k])
    .map((k) => ({
      k,
      label: FIELD[k] || k,
      before: show(before[k]),
      after: show(after[k]),
    }))
}

function openDetail(row) {
  cur.value = row
  detailVisible.value = true
}

function reload() {
  load()
}

async function load() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (fAction.value) params.action = fAction.value
    if (fTarget.value) params.target_type = fTarget.value
    if (range.value?.length === 2) {
      params.date_from = range.value[0]
      params.date_to = range.value[1]
    }
    rows.value = await request.get('/audit-logs', { params })
  } finally {
    loading.value = false
  }
}

onMounted(load)
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
.dim { color: var(--el-text-color-placeholder); }
.diff { font-size: 12.5px; line-height: 1.7; }
.diff-line { display: flex; gap: 8px; align-items: baseline; }
.diff-k {
  flex: 0 0 62px;
  color: var(--el-text-color-secondary);
}
.old { color: var(--el-text-color-placeholder); text-decoration: line-through; }
.arrow { color: var(--el-text-color-placeholder); }
.after { color: var(--crm-teal); font-weight: 600; }
.json {
  margin: 0;
  max-height: 420px;
  overflow: auto;
  font-size: 12.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
