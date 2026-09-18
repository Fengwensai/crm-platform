<template>
  <div class="page-wrap">
    <div class="toolbar">
      <span class="scope-tag">{{ ov.scope_label || '—' }}</span>
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

    <!-- ★ 双轨并列，**不合并成一个「总产出」**。
         框数和质检条数是不同量纲，相加出来的数字既不是框也不是条，
         而它看起来完全正常——这是这个页面最不该犯的错。 -->
    <div class="stat-grid" v-loading="loading">
      <div class="stat-card">
        <div class="k">标注工作量（框）</div>
        <div class="v">{{ num(ov.total_box) }}</div>
        <div class="sub">2D {{ num(ov.total_box2d) }} ＋ 3D {{ num(ov.total_box3d) }}</div>
      </div>
      <div class="stat-card">
        <div class="k">标注记录数</div>
        <div class="v">{{ num(ov.annotation_count) }}</div>
        <div class="sub">窗口内的登记条数</div>
      </div>
      <div class="stat-card">
        <div class="k">质检记录数</div>
        <div class="v">{{ num(ov.qc_total) }}</div>
        <div class="sub">通过 {{ num(ov.qc_pass) }} / 打回 {{ num(ov.qc_reject) }}</div>
      </div>
      <div class="stat-card">
        <div class="k">质检通过率</div>
        <div class="v teal">{{ (ov.qc_pass_rate * 100).toFixed(1) }}%</div>
        <div class="sub">通过 ÷ 质检总数（无质检时为 0%）</div>
      </div>
      <div class="stat-card">
        <div class="k">员工</div>
        <div class="v">{{ ov.active_employee_count }}</div>
        <div class="sub">在岗 / 范围内共 {{ ov.employee_count }}</div>
      </div>
      <div class="stat-card">
        <div class="k">进行中项目</div>
        <div class="v">{{ ov.project_count }}</div>
      </div>
      <div class="stat-card" v-if="ov.pending_count > 0">
        <div class="k">待审批账号</div>
        <div class="v warn">{{ ov.pending_count }}</div>
        <div class="sub"><router-link to="/users" class="link">去审批 →</router-link></div>
      </div>
    </div>

    <el-card shadow="never">
      <template #header><span class="card-title">每日产出趋势</span></template>
      <!-- 两张图**上下叠放、共用同一根日期轴**（见 components/TrendBars.vue，
           它同时负责「按总量定峰」和「无数据那天也要有柱子」这两件事）。 -->
      <TrendBars
        title="标注（框）"
        :loading="loading"
        :points="trend.points || []"
        :segs="ANNO_SEGS"
        :summary-text="`窗口内合计 ${num(trend.total_box)} 框`"
      />
      <TrendBars
        title="质检（条）"
        :loading="loading"
        :points="trend.points || []"
        :segs="QC_SEGS"
        :summary-text="`窗口内合计 ${num(trend.qc_total)} 条`"
      />
    </el-card>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="24" :xl="14">
        <el-card shadow="never">
          <template #header><span class="card-title">员工产出</span></template>
          <el-table :data="byUser" v-loading="loading" stripe max-height="460" empty-text="暂无数据">
            <el-table-column prop="name" label="姓名" min-width="110" fixed>
              <template #default="{ row }">
                {{ row.name }}
                <span class="dim sm">（{{ row.username }}）</span>
              </template>
            </el-table-column>
            <el-table-column prop="box2d" label="2D" width="88" align="right" sortable />
            <el-table-column prop="box3d" label="3D" width="88" align="right" sortable />
            <el-table-column label="标注合计" width="100" align="right" sortable :sort-by="'box_total'">
              <template #default="{ row }"><b class="teal">{{ num(row.box_total) }}</b></template>
            </el-table-column>
            <el-table-column prop="annotation_count" label="条数" width="76" align="right" sortable />
            <el-table-column prop="days" label="天数" width="70" align="right" />
            <!-- ★ 这两列是**方向相反**的两件事，表头必须写清楚，不能都叫「通过率」：
                   做质检 = 他判别人（高 = 他手松 / 偏低 = 他严格）
                   被质检 = 别人判他（这才是通常说的「他的质量」） -->
            <el-table-column label="他做质检" width="130" align="right">
              <template #default="{ row }">
                <template v-if="row.qc_as_inspector_total">
                  <span :class="rateCls(row.qc_as_inspector_pass_rate)">
                    {{ (row.qc_as_inspector_pass_rate * 100).toFixed(1) }}%
                  </span>
                  <span class="dim sm">/{{ row.qc_as_inspector_total }}</span>
                </template>
                <span v-else class="dim">—</span>
              </template>
            </el-table-column>
            <el-table-column label="他被质检" width="130" align="right">
              <template #default="{ row }">
                <template v-if="row.qc_as_target_total">
                  <span :class="rateCls(row.qc_as_target_pass_rate)">
                    {{ (row.qc_as_target_pass_rate * 100).toFixed(1) }}%
                  </span>
                  <span class="dim sm">/{{ row.qc_as_target_total }}</span>
                </template>
                <span v-else class="dim">—</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :xl="10">
        <el-card shadow="never">
          <template #header><span class="card-title">项目产出</span></template>
          <el-table :data="byProject" v-loading="loading" stripe max-height="460" empty-text="暂无数据">
            <el-table-column prop="name" label="项目" min-width="130" fixed>
              <template #default="{ row }">
                {{ row.name }}
                <div class="dim sm">{{ row.code }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="box2d" label="2D" width="86" align="right" sortable />
            <el-table-column prop="box3d" label="3D" width="86" align="right" sortable />
            <el-table-column label="标注合计" width="100" align="right" sortable :sort-by="'box_total'">
              <template #default="{ row }"><b class="teal">{{ num(row.box_total) }}</b></template>
            </el-table-column>
            <el-table-column prop="people" label="人数" width="72" align="right" />
            <el-table-column label="质检" width="120" align="right">
              <template #default="{ row }">
                <template v-if="row.qc_total">
                  {{ num(row.qc_total) }} 条
                  <span :class="rateCls(row.qc_pass_rate)" class="sm">
                    {{ (row.qc_pass_rate * 100).toFixed(1) }}%
                  </span>
                </template>
                <span v-else class="dim">—</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import request from '../api/request'
import TrendBars from '../components/TrendBars.vue'

// 两轨的分段定义。`cls` 指 theme.css 里的类名；**顺序 = 从下往上**。
const ANNO_SEGS = [
  { key: 'box2d', label: '2D 框数', cls: 'bar-2d', color: 'linear-gradient(180deg, #6fc0ec, #4aa8e0)' },
  { key: 'box3d', label: '3D 框数', cls: 'bar-3d', color: 'linear-gradient(180deg, #4a93d8, #2b7fd4)' },
]
const QC_SEGS = [
  { key: 'qc_pass', label: '通过', cls: 'bar-pass', color: 'linear-gradient(180deg, #4fc0a8, #2fa08a)' },
  { key: 'qc_reject', label: '打回', cls: 'bar-reject', color: 'linear-gradient(180deg, #e08c8c, #cf6b6b)' },
]

const loading = ref(false)
const quick = ref(30)
const range = ref(null)

// 默认值刻意**不写成一个看起来完整的对象**（比如 `{total_box: 0, qc_pass_rate: 0.5}`）：
// 初值只需要「渲染不炸」，任何编出来的数字都可能在下一次加载前被当成真数据看一眼。
const ov = ref({})
const trend = ref({ points: [] })
const byUser = ref([])
const byProject = ref([])

function num(n) {
  return (n ?? 0).toLocaleString('zh-CN')
}
/** 通过率配色：≥90% 正常（青），60~90% 中性，<60% 红。
 *  用固定阈值而不是「跟别人比」——比较出来的颜色在只有一个人的时候没有意义。 */
function rateCls(r) {
  if (r >= 0.9) return 'teal'
  if (r < 0.6) return 'danger'
  return ''
}

function isoOffset(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
function daysBetween([a, b]) {
  return Math.round((new Date(b) - new Date(a)) / 86400000) + 1
}

function onQuick(n) {
  // ★ 顺带把「手选区间」清掉：两个控件同时有值时，用户没法从界面上判断
  //   到底按哪个走（实际是按 range），看起来就是「快捷按钮点了没反应」。
  range.value = [isoOffset(n - 1), isoOffset(0)]
  loadAll()
}
function onRange() {
  if (!range.value?.length) return
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
      request.get('/stats/by-project', { params }),
    ])
    ov.value = o
    trend.value = t
    byUser.value = u
    byProject.value = p
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

onMounted(() => onQuick(30))
</script>

<style scoped>
.scope-tag {
  font-size: 12px;
  color: var(--el-color-primary-dark-2);
  background: var(--el-color-primary-light-9);
  border-radius: 999px;
  padding: 2px 10px;
}
.card-title { font-weight: 600; }
.teal { color: var(--crm-teal); }
.warn { color: var(--crm-warn); }
.danger { color: var(--crm-danger); }
.dim { color: var(--el-text-color-placeholder); }
.sm { font-size: 12px; }
.link { color: var(--el-color-primary); text-decoration: none; }
</style>
