<template>
  <div class="page-wrap">
    <div class="toolbar">
      <span class="page-title">操作留痕</span>
      <span class="page-sub" style="margin: 0">
        管理者动员工数据的每一次都在这里，含改动前后的数值
      </span>
      <div class="spacer"></div>
      <el-select v-model="fAction" placeholder="全部动作" clearable size="small" style="width: 150px" @change="load">
        <el-option v-for="a in actions" :key="a" :label="a" :value="a" />
      </el-select>
      <el-date-picker
        v-model="range"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始"
        end-placeholder="结束"
        size="small"
        @change="load"
      />
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading" stripe empty-text="没有符合条件的记录">
        <el-table-column label="时间" width="165">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="actor_name" label="操作人" width="110" />
        <el-table-column label="动作" width="120">
          <template #default="{ row }">
            <el-tag :type="actionTag(row.action)" size="small" effect="dark">{{ row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="对象" width="120">
          <template #default="{ row }">
            <span class="dim">{{ targetName(row.target_type) }}{{ row.target_id ? ` #${row.target_id}` : '' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="说明" min-width="220" show-overflow-tooltip />
        <el-table-column label="改动" min-width="240">
          <template #default="{ row }">
            <div v-if="hasDiff(row)" class="diff">
              <div class="diff-line">
                <span class="diff-k">改前</span>
                <span>{{ diffText(row.detail.before) }}</span>
              </div>
              <div class="diff-line">
                <span class="diff-k">改后</span>
                <span class="after">{{ diffText(row.detail.after) }}</span>
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
      <div class="count" v-if="rows.length">共 {{ rows.length }} 条（最多显示 200 条，可用时间范围缩小）</div>
    </el-card>

    <el-dialog v-model="detailVisible" title="操作详情" width="520px">
      <pre class="json">{{ prettyDetail }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import request from '../api/request'

const rows = ref([])
const loading = ref(false)
const range = ref(null)
const fAction = ref(null)
const detailVisible = ref(false)
const cur = ref({})

const actions = [
  '代填工作数据', '修改工作数据', '删除工作数据',
  '审批通过', '驳回注册', '修改账号', '删除账号',
  '新建项目', '修改项目', '删除项目', '重置密码'
]

const targetMap = { work_record: '工作记录', user: '账号', project: '项目' }
const targetName = (t) => targetMap[t] || t || '—'

const actionTag = (a) => {
  if (a.startsWith('删除')) return 'danger'
  if (a.startsWith('修改') || a.startsWith('代填')) return 'warning'
  if (a.startsWith('审批通过')) return 'success'
  return 'info'
}

const fmt = (s) => (s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : '—')

// 只有 work_record 的改动带 before/after 快照，其余动作 detail 里是别的字段
function hasDiff(row) {
  return !!(row.detail?.before && row.detail?.after)
}
function hasDetail(row) {
  return !!row.detail && Object.keys(row.detail).length > 0
}

const FIELD = { amount: '总量', rework_amount: '返工量', remark: '备注', work_date: '日期' }

// 只显示真正变了的字段，没变的略过——否则「改前改后」两行一模一样，看不出改了什么
function diffText(snap) {
  if (!snap) return '—'
  const parts = Object.entries(snap)
    .filter(([k]) => FIELD[k])
    .map(([k, v]) => `${FIELD[k]} ${k === 'remark' && !v ? '（空）' : v}`)
  return parts.join(' · ') || JSON.stringify(snap)
}

const prettyDetail = computed(() => JSON.stringify(cur.value.detail || {}, null, 2))

function openDetail(row) {
  cur.value = row
  detailVisible.value = true
}

async function load() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (fAction.value) params.action = fAction.value
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
</script>

<style scoped>
.dim { color: var(--el-text-color-placeholder); }
.diff {
  font-size: 12.5px;
  line-height: 1.6;
}
.diff-line { display: flex; gap: 8px; }
.diff-k {
  flex: 0 0 30px;
  color: var(--el-text-color-secondary);
}
.after { color: var(--crm-teal); }
.count {
  margin-top: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
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
