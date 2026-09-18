<template>
  <div class="track-block" v-loading="loading">
    <div class="track-title">
      {{ title }}
      <span v-if="points.length" class="track-sub">{{ summaryText }}</span>
    </div>

    <template v-if="points.length">
      <div class="bars">
        <div v-for="p in points" :key="p[dateKey]" class="bar-col">
          <div
            class="bar-stack"
            :style="{ height: barHeight(p) }"
            :title="tooltip(p)"
          >
            <!-- ★ 段序 = DOM 顺序，而 `.bar-stack` 是 `column-reverse`，
                 所以**第一个是柱底**。segs 的顺序因此是从下往上的。 -->
            <div
              v-for="s in segs"
              :key="s.key"
              :class="s.cls"
              :style="{ height: segHeight(p[s.key]) }"
            ></div>
          </div>
          <div class="bar-label">{{ String(p[dateKey]).slice(5) }}</div>
        </div>
      </div>
      <div class="bars-legend">
        <span v-for="s in segs" :key="s.key">
          <i :style="{ background: s.color }"></i>{{ s.label }}
        </span>
      </div>
    </template>
    <el-empty v-else description="该时间段还没有数据" :image-size="80" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  /** 日期轴上的一天。每项至少含 `dateKey` 与各 `segs[].key` */
  points: { type: Array, default: () => [] },
  dateKey: { type: String, default: 'work_date' },
  /** 柱子的分段：**顺序即从下到上**（见模板里的注释）。
   *  `cls` 指向 theme.css 里的 `.bar-2d / .bar-3d / .bar-pass / .bar-reject`。 */
  segs: { type: Array, default: () => [] },
  /** 标题右侧的小字，如「窗口内合计 1,239,698 框」。
   *  由调用方拿服务端算好的整段拼——本组件不做任何求和，
   *  因为「窗口内合计」的口径（有没有补零、含不含被过滤掉的行）属于服务端。 */
  summaryText: { type: String, default: '' },
})

/** 纵轴峰值：取「每天各段之和」的最大值。
 *  ★ 用**求和后的总量**定峰，不是各段各自定峰——后者会让 2D 和 3D 各自顶到满格，
 *    同一根柱子看起来像两天的量。 */
const peak = computed(() => {
  let m = 0
  for (const p of props.points) {
    let sum = 0
    for (const s of props.segs) sum += Number(p[s.key] || 0)
    if (sum > m) m = sum
  }
  return Math.max(1, m)
})

const MAX_H = 150

function barHeight(p) {
  let sum = 0
  for (const s of props.segs) sum += Number(p[s.key] || 0)
  // 有数据的那天至少给 3px：四舍五入会把「1 条」压成 0px，
  // 表现为「那天明明是有的，图上什么都没有」。
  return `${Math.max(sum > 0 ? 3 : 0, Math.round((sum / peak.value) * MAX_H))}px`
}

function segHeight(v) {
  if (!v) return '0px'
  return `${Math.round((Number(v) / peak.value) * MAX_H)}px`
}

function tooltip(p) {
  return props.segs.map((s) => `${s.label} ${Number(p[s.key] || 0).toLocaleString('zh-CN')}`).join('  ')
}
</script>

<style scoped>
.track-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.track-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 400;
}
</style>
