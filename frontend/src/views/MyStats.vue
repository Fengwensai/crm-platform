<template>
  <div class="page-wrap">
    <div class="toolbar">
      <span class="page-title">我的统计</span>
      <span class="page-sub" style="margin: 0">只统计本人的填报数据</span>
      <div class="spacer"></div>
      <el-radio-group v-model="days" size="small" @change="load">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">近 90 天</el-radio-button>
      </el-radio-group>
    </div>

    <div class="stat-grid" v-loading="loading">
      <div class="stat-card">
        <div class="k">总标注量</div>
        <div class="v">{{ data.total_amount }}</div>
        <div class="sub">共 {{ data.days }} 天有填报</div>
      </div>
      <div class="stat-card">
        <div class="k">合格量</div>
        <div class="v teal">{{ data.total_qualified }}</div>
        <div class="sub">总量 − 返工量</div>
      </div>
      <div class="stat-card">
        <div class="k">返工量</div>
        <div class="v" :class="{ warn: data.total_rework > 0 }">{{ data.total_rework }}</div>
        <div class="sub">越少越好</div>
      </div>
      <div class="stat-card">
        <div class="k">合格率</div>
        <div class="v teal">{{ (data.pass_rate * 100).toFixed(1) }}%</div>
        <div class="sub">合格量 ÷ 总量</div>
      </div>
    </div>

    <el-card shadow="never">
      <template #header><span style="font-weight: 600">每日趋势</span></template>
      <div v-if="data.trend?.length" class="bars">
        <div v-for="p in data.trend" :key="p.work_date" class="bar-col">
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
      <el-empty v-else description="该时间段还没有填报" :image-size="80" />
      <div class="bars-legend" v-if="data.trend?.length">
        <span><i style="background: linear-gradient(180deg, #4fc3f7, #2b7fd4)"></i>合格量</span>
        <span><i style="background: rgba(230,162,60,.75)"></i>返工量</span>
      </div>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header><span style="font-weight: 600">按项目</span></template>
      <el-table :data="data.by_project" stripe empty-text="暂无数据">
        <el-table-column prop="name" label="项目" min-width="160" />
        <el-table-column prop="amount" label="总量" width="120" align="right" sortable />
        <el-table-column prop="rework" label="返工量" width="110" align="right" />
        <el-table-column prop="qualified" label="合格量" width="120" align="right">
          <template #default="{ row }"><b class="teal">{{ row.qualified }}</b></template>
        </el-table-column>
        <el-table-column label="合格率" width="140">
          <template #default="{ row }">
            <el-progress
              :percentage="Number((row.pass_rate * 100).toFixed(1))"
              :stroke-width="10"
              color="#00c9b0"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import request from '../api/request'

const days = ref(30)
const loading = ref(false)
const data = ref({ total_amount: 0, total_rework: 0, total_qualified: 0, pass_rate: 0, days: 0, trend: [], by_project: [] })

// 柱子按窗口内最大值等比缩放
const peak = computed(() => {
  const m = Math.max(1, ...(data.value.trend || []).map((p) => p.amount))
  return m
})

function barHeight(p) {
  const h = Math.round(((p.amount || 0) / peak.value) * 150)
  return `${Math.max(p.amount > 0 ? 3 : 0, h)}px`
}

// 单段高度：按该段占整条的比例切分，保证两段加起来等于总高
function segHeight(v) {
  if (!v) return '0px'
  const total = peak.value
  return `${Math.round((v / total) * 150)}px`
}

async function load() {
  loading.value = true
  try {
    data.value = await request.get('/stats/me', { params: { days: days.value } })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
