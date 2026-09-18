<template>
  <div class="page-wrap">
    <div class="toolbar">
      <span class="page-title">项目管理</span>
      <span class="page-sub" style="margin: 0">员工填报时从这里选项目</span>
      <div class="spacer"></div>
      <el-button type="primary" size="small" :icon="Plus" @click="openCreate">新建项目</el-button>
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading" stripe empty-text="还没有项目，先建一个">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="code" label="项目编号" width="160" />
        <el-table-column prop="name" label="项目名称" min-width="180" />
        <!-- 「单位」列已去掉：v2 的数量口径是 2D/3D 框数，单位恒为「框」。
             留着这一列的话，后台里会有人继续维护它，而它不影响任何一处计算。
             列本身还在库里（DROP COLUMN 不可逆），只是接口和界面都不再提它。 -->
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="dark">
              {{ row.status === 'active' ? '进行中' : '已归档' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="165">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              link
              :type="row.status === 'active' ? 'warning' : 'success'"
              size="small"
              @click="toggle(row)"
            >{{ row.status === 'active' ? '归档' : '恢复' }}</el-button>
            <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="tip">
      归档的项目不再出现在员工的填报下拉里，但历史数据完整保留、统计照常计入——项目做完了一般用归档，不要删。<br />
      删除只对「从没被填报过」的项目有效；已经有数据的会拒绝，以免历史记录变成孤儿。
    </div>

    <el-dialog v-model="visible" :title="form.id ? '编辑项目' : '新建项目'" width="440px">
      <el-form :model="form" label-width="86px">
        <el-form-item label="项目编号" required>
          <el-input v-model="form.code" :disabled="!!form.id" placeholder="如 PRJ-2026-01，唯一" maxlength="64" />
        </el-form-item>
        <el-form-item label="项目名称" required>
          <el-input v-model="form.name" maxlength="128" placeholder="如 语音转写第一批" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import request from '../api/request'

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const form = reactive({ id: null, code: '', name: '' })

const fmt = (s) => (s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : '—')

async function load() {
  loading.value = true
  try {
    rows.value = await request.get('/projects')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { id: null, code: '', name: '' })
  visible.value = true
}

function openEdit(row) {
  Object.assign(form, { id: row.id, code: row.code, name: row.name })
  visible.value = true
}

async function onSave() {
  if (!form.code.trim()) return ElMessage.warning('请填写项目编号')
  if (!form.name.trim()) return ElMessage.warning('请填写项目名称')
  saving.value = true
  try {
    if (form.id) {
      await request.patch(`/projects/${form.id}`, { name: form.name.trim() })
      ElMessage.success('已保存')
    } else {
      await request.post('/projects', { code: form.code.trim(), name: form.name.trim() })
      ElMessage.success('已创建')
    }
    visible.value = false
    await load()
  } catch {
    /* 编号重复(409) 等由拦截器提示 */
  } finally {
    saving.value = false
  }
}

async function toggle(row) {
  const next = row.status === 'active' ? 'archived' : 'active'
  await request.patch(`/projects/${row.id}`, { status: next })
  ElMessage.success(next === 'archived' ? '已归档' : '已恢复')
  await load()
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除项目「${row.name}」吗？只有从没被填报过的项目才能删。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await request.delete(`/projects/${row.id}`)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* 有数据时 422，拦截器提示改用归档 */
  }
}

onMounted(load)
</script>

<style scoped>
.tip {
  margin-top: 14px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.8;
}
</style>
