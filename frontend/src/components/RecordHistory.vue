<template>
  <el-dialog
    :model-value="modelValue"
    :title="`「${title}」的改动记录`"
    width="620px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-loading="loading" style="min-height: 80px">
      <el-empty v-if="!loading && !logs.length" description="这条记录没有被别人改过" :image-size="70" />

      <div v-for="log in logs" :key="log.id" class="hist">
        <div class="hist-head">
          <span class="hist-who">{{ log.actor_name || '—' }}</span>
          <span class="hist-act">{{ log.action }}</span>
          <div class="spacer"></div>
          <span class="hist-time">{{ fmtTime(log.created_at) }}</span>
        </div>
        <table v-if="diffRows(log).length" class="hist-diff">
          <thead>
            <tr><th>字段</th><th>改前</th><th>改后</th></tr>
          </thead>
          <tbody>
            <tr v-for="d in diffRows(log)" :key="d.k">
              <td class="k">{{ d.label }}</td>
              <td class="old">{{ d.before }}</td>
              <td class="new">{{ d.after }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="hist-plain">{{ log.summary || log.action }}</div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import request from '../api/request'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** 记录类型：'annotation' | 'qc_record'，直接对应后端审计的 target_type */
  targetType: { type: String, required: true },
  targetId: { type: [Number, String], default: null },
  /** 弹窗标题里显示的这条记录是谁的 / 是哪条 */
  title: { type: String, default: '' },
  /** 字段名 → 中文标签。传进来而不是在这里 if/else 分轨：
   *  两张表的 detail 字段名不同，但「怎么把 before/after 渲染成一张对照表」
   *  是同一件事。 */
  labels: { type: Object, default: () => ({}) },
})

defineEmits(['update:modelValue'])

const logs = ref([])
const loading = ref(false)

/** 后端 detail 里 `result` 存的是 pass/reject，直接显示英文没人看得懂 */
const VALUE_LABELS = { pass: '通过', reject: '打回' }

function show(v) {
  if (v === null || v === undefined || v === '') return '（空）'
  return VALUE_LABELS[v] ?? String(v)
}

function diffRows(log) {
  const before = log?.detail?.before
  const after = log?.detail?.after
  if (!before || !after) return []
  return Object.keys(after)
    .filter((k) => before[k] !== after[k])
    .map((k) => ({
      k,
      label: props.labels[k] || k,
      before: show(before[k]),
      after: show(after[k]),
    }))
}

function fmtTime(t) {
  if (!t) return ''
  // 后端给的是带时区的 ISO 串。这里只取到分钟——秒对「谁什么时候改的」没有意义。
  // 用 new Date 解析后按浏览器本地时区显示（用户看到的是自己表上的时间）。
  const d = new Date(t)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// ★ 每次打开都重新拉，不缓存。缓存的话用户改完再看，看到的还是打开前的历史，
//   而界面上没有任何东西能提示「这是旧的」。
watch(
  () => [props.modelValue, props.targetId],
  async ([open, id]) => {
    if (!open || !id) return
    loading.value = true
    logs.value = []
    try {
      logs.value = await request.get('/audit-logs/mine', {
        params: { target_type: props.targetType, target_id: id },
      })
    } catch {
      /* 拦截器已提示 */
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.spacer { flex: 1; }
.hist {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.hist-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 8px;
}
.hist-who { font-weight: 600; color: var(--el-text-color-primary); }
.hist-act {
  color: var(--crm-warn);
  background: #fdf6ec;
  border-radius: 4px;
  padding: 0 6px;
  font-size: 12px;
}
.hist-time { color: var(--el-text-color-secondary); font-size: 12px; }
.hist-diff {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.hist-diff th,
.hist-diff td {
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 5px 8px;
  text-align: left;
}
.hist-diff th { color: var(--el-text-color-secondary); font-weight: 500; }
.hist-diff .k { color: var(--el-text-color-secondary); width: 90px; }
.hist-diff .old { color: var(--el-text-color-placeholder); text-decoration: line-through; }
.hist-diff .new { color: var(--crm-teal); font-weight: 600; }
.hist-plain { font-size: 13px; color: var(--el-text-color-regular); }
</style>
