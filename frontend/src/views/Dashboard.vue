<template>
  <div class="page-wrap">
    <div class="toolbar">
      <span class="page-title">数据看板</span>
      <div class="spacer"></div>
      <el-radio-group v-model="quick" size="small" @change="onQuick">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">近 90 天</el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-model="range"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="开始"
        end-placeholder="结束"
        size="small"
        @change="onRange"
      />
      <el-button size="small" :icon="Refresh" @click="loadAll">刷新</el-button>
    </div>

    <div class="stat-grid" v-loading="loading">
      <div class="stat-card">
        <div class="k">总标注量</div>
        <div class="v">{{ ov.total_amount }}</div>
        <div class="sub">{{ ov.record_count }} 条填报记录</div>
      </div>
      <div class="stat-card">
        <div class="k">合格量</div>
        <div class="v teal">{{ ov.total_qualified }}</div>
        <div class="sub">返工 {{ ov.total_rework }}</div>
      </div>
      <div class="stat-card">
        <div class="k">合格率</div>
        <div class="v teal">{{ (ov.pass_rate * 100).toFixed(1) }}%</div>
        <div class="sub">合格量 ÷ 总量</div>
      </div>
      <div class="stat-card">
        <div class="k">参与员工</div>
        <div class="v">{{ activeCount }}</div>
        <div class="sub">在岗 {{ ov.active_employee_count }} / 共 {{ ov.employee_count }}</div>
      </div>
      <div class="stat-card">
        <div class="k">进行中项目</div>
        <div class="v">{{ ov.project_count }}</div>
        <div class="sub">共 {{ projects.length }} 个</div>
      </div>
      <div class="stat-card" v-if="ov.pending_count > 0">
        <div class="k">待审批账号</div>
        <div class="v warn">{{ ov.pending_count }}</div>
        <div class="sub">
          <router-link to="/review" style="color: #66b1ff">去审批 →</router-link>
        </div>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>每日产出趋势</span>
          <span class="hint">窗口内合计 {{ trend.total_amount }}，返工 {{ trend.total_rework }}</span>
        </div>
      </template>
      <div v-if="trend.points?.length" class="bars">
        <div v-for="p in trend.points" :key="p.work_date" class="bar-col">
          <div
            class="bar-stack"
            :style="{ height: barHeight(p) }"
            :title="`${p.work_date}  合格 ${p.qualified} / 返工 ${p.rework}`"
          >
            <div class="bar-rework" :style="{ height: segHeight(p.rework) }"></div>
            <div class="bar-qualified" :style="{ height: segHeight(p.qualified) }"></div>
          </div>
          <div class="bar-label">{{ p.work_date.slice(5) }}</div>
        </div>
      </div>
      <el-empty v-else description="该时间段还没有数据" :image-size="80" />
      <div class="bars-legend" v-if="trend.points?.length">
        <span><i style="background: linear-gradient(180deg, #4fc3f7, #2b7fd4)"></i>合格量</span>
        <span><i style="background: rgba(230,162,60,.75)"></i>返工量</span>
      </div>
    </el-card>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="24" :lg="12">
        <el-card shadow="never">
          <template #header><span style="font-weight: 600">员工产出排行</span></template>
          <el-table :data="byUser" stripe max-height="420" empty-text="暂无数据">
            <el-table-column type="index" label="#" width="52" />
            <el-table-column prop="name" label="姓名" min-width="90">
              <template #default="{ row }">
                {{ row.name }}
                <span class="dim" style="font-size: 12px">（{{ row.username }}）</span>
              </template>
            </el-table-column>
            <el-table-column prop="amount" label="总量" width="100" align="right" sortable />
            <el-table-column prop="qualified" label="合格量" width="100" align="right" sortable />
            <el-table-column prop="rework" label="返工" width="80" align="right" />
            <el-table-column label="合格率" width="90" align="right">
              <template #default="{ row }">
                <span :class="row.pass_rate >= 0.98 ? 'teal' : row.pass_rate < 0.95 ? 'danger' : ''">
                  {{ (row.pass_rate * 100).toFixed(1) }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="days" label="天数" width="70" align="right" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="12">
        <el-card shadow="never">
          <template #header><span style="font-weight: 600">项目产出</span></template>
          <el-table :data="byProject" stripe max-height="420" empty-text="暂无数据">
            <el-table-column prop="name" label="项目" min-width="130" />
            <el-table-column prop="unit" label="单位" width="70" />
            <el-table-column prop="amount" label="总量" width="100" align="right" sortable />
            <el-table-column prop="qualified" label="合格量" width="100" align="right" sortable />
            <el-table-column label="合格率" width="90" align="right">
              <template #default="{ row }">{{ (row.pass_rate * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column prop="people" label="人数" width="70" align="right" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import request from '../api/request'

const loading = ref(false)
const quick = ref(30)
const range = ref(null)
const projects = ref([])

const ov = ref({
  total_amount: 0, total_rework: 0, total_qualified: 0, pass_rate: 0,
  record_count: 0, employee_count: 0, active_employee_count: 0,
  project_count: 0, pending_count: 0
})
const trend = ref({ points: [], total_amount: 0, total_rework: 0 })
const byUser = ref([])
const byProject = ref([])

const activeCount = computed(() => byUser.value.length)
const peak = computed(() => Math.max(1, ...(trend.value.points || []).map((p) => p.amount)))

function barHeight(p) {
  const h = Math.round(((p.amount || 0) / peak.value) * 150)
  return `${Math.max(p.amount > 0 ? 3 : 0, h)}px`
}
function segHeight(v) {
  if (!v) return '0px'
  return `${Math.round((v / peak.value) * 150)}px`
}

function isoOffset(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function onQuick(n) {
  range.value = [isoOffset(n - 1), isoOffset(0)]
  loadAll()
}
function onRange() {
  if (!range.value?.length) return
  // 手选区间后把快捷按钮的高亮取消，避免"选了 90 天但显示近 7 天"
  quick.value = null
  loadAll()
}

async function loadAll() {
  loading.value = true
  const params = {}
  if (range.value?.length === 2) {
    params.date_from = range.value[0]
    params.date_to = range.value[1]
  }
  try {
    const days = range.value?.length === 2 ? daysBetween(range.value) : 30
    const [o, t, u, p] = await Promise.all([
      request.get('/stats/overview', { params }),
      request.get('/stats/trend', { params: { days: Math.min(Math.max(days, 1), 365) } }),
      request.get('/stats/by-user', { params }),
      request.get('/stats/by-project', { params })
    ])
    ov.value = o
    trend.value = t
    byUser.value = u
    byProject.value = p
  } finally {
    loading.value = false
  }
}

function daysBetween([a, b]) {
  return Math.round((new Date(b) - new Date(a)) / 86400000) + 1
}

onMounted(async () => {
  try {
    projects.value = await request.get('/projects')
  } catch {
    /* 看板不因项目列表失败而空白 */
  }
  onQuick(30)
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
.teal { color: var(--crm-teal); }
.warn { color: var(--crm-warn); }
.danger { color: var(--crm-danger); }
.dim { color: var(--el-text-color-placeholder); }
</style>
