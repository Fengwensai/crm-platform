<template>
  <div>
    <div class="filters">
      <span class="hint">
        团队决定<b>组长能看见谁的数据</b>：组长看到本组的全部记录，员工只看到自己的。
      </span>
      <div class="spacer"></div>
      <el-checkbox v-model="showArchived" size="small" @change="load">显示已归档</el-checkbox>
      <el-button type="primary" size="small" :icon="Plus" @click="openCreate">新建团队</el-button>
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" stripe empty-text="还没有团队">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="团队名称" min-width="150" />
      <el-table-column label="组长" width="140">
        <template #default="{ row }">
          <span v-if="row.leader_name">{{ row.leader_name }}</span>
          <el-tag v-else type="warning" size="small" effect="plain">未设组长</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="成员数" width="90" align="right">
        <template #default="{ row }">
          <span :class="row.member_count ? '' : 'dim'">{{ row.member_count }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="96">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small" effect="dark">
            {{ row.status === 'active' ? '正常' : '已归档' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.remark">{{ row.remark }}</span>
          <span v-else class="dim">—</span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="165">
        <template #default="{ row }">{{ fmt(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
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

    <div class="tip">
      组长由「账号」页设置：把某个人的角色改成<b>组长</b>并给他选这个团队。
      一个团队只能有一个组长——这一条由服务端强制，两边都设的话两人看到的是同一批数据，
      而界面上不会有任何异常。<br />
      归档只是让这个团队不再出现在「分配团队」的下拉里，成员和数据都还在；删除则要求先<b>移出所有成员</b>。
    </div>

    <el-dialog v-model="visible" :title="form.id ? '编辑团队' : '新建团队'" width="440px">
      <el-form :model="form" label-width="86px">
        <el-form-item label="团队名称" required>
          <el-input v-model="form.name" maxlength="64" placeholder="如 甲组 / 语音标注一组" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" maxlength="255" placeholder="选填" />
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
import request from '../../api/request'

const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const visible = ref(false)
const showArchived = ref(false)
const form = reactive({ id: null, name: '', remark: '' })

const fmt = (s) => (s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : '—')

async function load() {
  loading.value = true
  try {
    rows.value = await request.get('/teams', {
      params: showArchived.value ? { include_archived: true } : {},
    })
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { id: null, name: '', remark: '' })
  visible.value = true
}

function openEdit(row) {
  Object.assign(form, { id: row.id, name: row.name, remark: row.remark })
  visible.value = true
}

async function onSave() {
  if (!form.name.trim()) return ElMessage.warning('请填写团队名称')
  saving.value = true
  try {
    if (form.id) {
      await request.patch(`/teams/${form.id}`, { name: form.name.trim(), remark: form.remark })
      ElMessage.success('已保存')
    } else {
      await request.post('/teams', { name: form.name.trim(), remark: form.remark })
      ElMessage.success('已创建')
    }
    visible.value = false
    await load()
  } catch {
    /* 重名(409) 由拦截器提示 */
  } finally {
    saving.value = false
  }
}

async function toggle(row) {
  const next = row.status === 'active' ? 'archived' : 'active'
  await request.patch(`/teams/${row.id}`, { status: next })
  ElMessage.success(next === 'archived' ? '已归档' : '已恢复')
  await load()
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除团队「${row.name}」吗？有成员的团队删不掉，需要先把成员移到别的团队。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await request.delete(`/teams/${row.id}`)
    ElMessage.success('已删除')
    await load()
  } catch {
    /* 有成员时 422，拦截器提示 */
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
.hint { font-size: 13px; color: var(--el-text-color-secondary); }
.tip {
  margin-top: 14px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.8;
}
.dim { color: var(--el-text-color-placeholder); }
</style>
