<template>
  <div class="page-wrap">
    <div class="toolbar">
      <span class="page-title">账号审批</span>
      <span class="page-sub" style="margin: 0">
        员工自助注册后卡在这里，审批通过才能登录填报
      </span>
      <div class="spacer"></div>
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading" stripe empty-text="没有待审批的账号">
        <el-table-column prop="username" label="工号" width="150" />
        <el-table-column prop="name" label="姓名" width="140" />
        <el-table-column label="提交时间" min-width="170">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button type="success" size="small" @click="openReview(row, 'approve')">通过</el-button>
            <el-button type="danger" size="small" plain @click="openReview(row, 'reject')">驳回</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="tip">
      提示：工号是登录名，重复的工号在注册时就会被拒。若有员工报「注册说工号已存在」，
      多半是自己之前已注册过——去
      <router-link to="/users">账号管理</router-link> 里搜一下工号，重置密码即可，不用重新注册。
    </div>

    <el-dialog v-model="visible" :title="mode === 'approve' ? '通过审批' : '驳回注册'" width="440px">
      <p class="dlg-line">
        <b>{{ cur.name }}</b>（工号 {{ cur.username }}）
      </p>
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
import request from '../api/request'

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const mode = ref('approve')
const cur = ref({})
const note = ref('')

function fmt(s) {
  return s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : '—'
}

async function load() {
  loading.value = true
  try {
    rows.value = await request.get('/users/pending')
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
</script>

<style scoped>
.tip {
  margin-top: 14px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}
.tip a { color: #66b1ff; text-decoration: none; }
.dlg-line { margin: 0 0 12px; }
</style>
