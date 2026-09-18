<template>
  <div class="page-wrap">
    <el-card shadow="never">
      <el-tabs v-model="tab">
        <el-tab-pane name="pending">
          <template #label>
            <span class="tab-label">
              待审批
              <!-- 待审条数点在这，因为「有几个账号在等」是这一页唯一需要主动去看的东西
                   （其余三个 tab 的数据不会自己变）。 -->
              <el-badge v-if="pendingCount > 0" :value="pendingCount" class="tab-badge" />
            </span>
          </template>
          <TabPending @count="pendingCount = $event" />
        </el-tab-pane>

        <el-tab-pane label="账号" name="accounts">
          <TabAccounts />
        </el-tab-pane>

        <el-tab-pane label="团队" name="teams">
          <TabTeams />
        </el-tab-pane>

        <el-tab-pane label="操作留痕" name="audit">
          <TabAudit />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import TabPending from './users/TabPending.vue'
import TabAccounts from './users/TabAccounts.vue'
import TabTeams from './users/TabTeams.vue'
import TabAudit from './users/TabAudit.vue'

// ★ 三个非默认 tab 都是**进入时才挂载**的（`el-tab-pane` 默认懒渲染），
//   所以这一页不会一打开就并发发四个请求。
//   代价是「切到账号页 → 回待审批页」不会自动刷新——但每个 tab 内都有刷新按钮，
//   而且自动刷新会让用户在别处刚做的修改突然出现/消失，更难理解。
const tab = ref('pending')
const pendingCount = ref(0)
</script>

<style scoped>
.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.tab-badge :deep(.el-badge__content) {
  border: none;
}
</style>
