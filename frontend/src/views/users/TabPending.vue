<template>
  <div>
    <div class="filters">
      <span class="hint">
        员工自助注册后卡在这里，<b>审批通过才能登录</b>；驳回时写的原因会显示给对方。
      </span>
      <div class="spacer"></div>
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" stripe empty-text="没有待审批的账号">
      <el-table-column prop="username" label="工号" width="150" />
      <el-table-column prop="name" label="姓名" width="140" />
      <el-table-column label="提交时间" min-width="170">
        <template #default="{ row }">{{ fmt(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button type="success" size="small" @click="openReview(row, 'approve')">通过</el-button>
          <el-button type="danger" size="small" plain @click="openReview(row, 'reject')">驳回</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="tip">
      工号是登录名，重复的工号在注册时就会被拒。若有员工报「工号已存在」，
      多半是他之前已经注册过——去「账号」页搜一下工号，重置密码即可，不用重新注册。<br />
      审批通过后，别忘了在「账号」页把他分到团队，否则组长看不到他的数据。
    </div>

    <el-dialog v-model="visible" :title="mode === 'approve' ? '通过审批' : '驳回注册'" width="440px">
      <p class="dlg-line"><b>{{ cur.name }}</b>（工号 {{ cur.username }}）</p>
      <el-input
        v-model="note"
        type="textarea"
        :rows="3"
        maxlength="255"
        show-word-limit
        :placeholder="mode === 'approve' ? '备注（可不填）' : '驳回原因，员工登录时会看到这句话'"
      />
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button :type="mode === 'approve' ? 'success' : 'danger'" :loading="saving" @click="onConfirm">
          {{ mode === 'approve' ? '确认通过' : '确认驳回' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import request from '../../api/request'

// ★ 把条数交给外层壳（UserManage.vue），它用这个数字点 tab 上的红点，
//   也让顶栏那个红点在审批完立刻归零。子组件自己改顶栏状态的话，
//   顶栏就成了一个谁都能写的全局变量。
const emit = defineEmits(['count'])

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const mode = ref('approve')
const cur = ref({})
const note = ref('')

const fmt = (s) => (s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : '—')

async function load() {
  loading.value = true
  try {
    rows.value = await request.get('/users/pending')
    emit('count', rows.value.length)
  } finally {
    loading.value = false
  }
}

function openReview(row, m) {
  cur.value = row
  mode.value = m
  note.value = ''
  visible.value = true
}

async function onConfirm() {
  if (mode.value === 'reject' && !note.value.trim()) {
    return ElMessage.warning('驳回请写明原因，员工需要知道问题出在哪')
  }
  saving.value = true
  try {
    await request.post(`/users/${cur.value.id}/${mode.value}`, { note: note.value })
    ElMessage.success(mode.value === 'approve' ? '已通过' : '已驳回')
    visible.value = false
    await load()
  } catch {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
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
  margin-bottom: 12px;
}
.spacer { flex: 1; }
.hint { font-size: 13px; color: var(--el-text-color-secondary); }
.tip {
  margin-top: 14px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}
.dlg-line { margin: 0 0 12px; }
</style>
