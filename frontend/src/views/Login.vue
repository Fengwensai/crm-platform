<template>
  <div class="login-page">
    <div class="aurora aurora-a"></div>
    <div class="aurora aurora-b"></div>

    <div class="card">
      <div class="brand">
        <span class="brand-mark"><el-icon :size="22" color="#fff"><DataLine /></el-icon></span>
        <h1>工作量统计平台</h1>
        <p>员工每日标注量 · 填报与统计</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent>
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="工号" clearable @keyup.enter="onSubmit">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" show-password @keyup.enter="onSubmit">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-button type="primary" class="submit" :loading="loading" @click="onSubmit">
          登 录
        </el-button>
      </el-form>

      <div class="foot">
        还没有账号？<router-link to="/register">员工自助注册</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入工号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function onSubmit() {
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  loading.value = true
  try {
    await auth.login(form.username.trim(), form.password)
    ElMessage.success(`欢迎回来，${auth.user?.name || auth.user?.username}`)
    router.push('/')
  } catch {
    // 具体原因（待审批 / 已停用 / 密码错）由响应拦截器统一弹出
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* 浅色登录页。
   ★ 这里原来是 v1 的深色极光：`#0a1220` 底 + 两团高饱和模糊光斑 + 半透明深色玻璃卡。
     整站 v2 换成浅色后它被漏掉了（`theme.css` 早就翻浅，只有这一个路由还是黑的）。
   翻浅时最容易漏的两处，和 AppLayout 当时踩的是同一对：
   ① `.brand h1` 的白→浅蓝渐变文字（`background-clip:text` + `color:transparent`）
      在白底上**完全看不见**——必须换成纯色；
   ② `.brand-mark` 那圈 `rgba(64,158,255,0.42)` 的发光投影在白底上是脏斑，要压下去。
   品牌锚点（渐变方块 + 青绿强调色）保留：它们在浅色底上比深色底更清楚。 */
.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-bg-color-page);
  overflow: hidden;
}
/* 光斑留着，但透明度从 0.30/0.22 降到 0.10——浅底上再高就是脏斑而不是氛围 */
.aurora {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
}
.aurora-a {
  width: 620px; height: 620px;
  left: -160px; top: -180px;
  background: radial-gradient(circle, rgba(64, 158, 255, 0.10), transparent 70%);
}
.aurora-b {
  width: 560px; height: 560px;
  right: -140px; bottom: -180px;
  background: radial-gradient(circle, rgba(13, 148, 136, 0.10), transparent 70%);
}

.card {
  position: relative;
  width: 380px;
  padding: 36px 34px 26px;
  border-radius: 18px;
  /* 白底实心，不再需要 backdrop-filter——那层模糊是给半透明深色玻璃用的，
     浅色下留着只会让文字发虚。 */
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
}

.brand {
  text-align: center;
  margin-bottom: 26px;
}
.brand-mark {
  width: 52px; height: 52px;
  border-radius: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #409eff, #0d9488);
  box-shadow: 0 8px 20px rgba(64, 158, 255, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.35);
  margin-bottom: 14px;
}
.brand h1 {
  margin: 0 0 6px;
  font-size: 21px;
  font-weight: 700;
  letter-spacing: 2px;
  /* ★ 不能再用渐变文字：`color:transparent` + `background-clip:text` 在白底上
     等于把标题擦掉。深色纯色就够，字重和字距已经把分量给足了。 */
  color: var(--el-text-color-primary);
}
.brand p {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  letter-spacing: 1px;
}

.submit {
  width: 100%;
  margin-top: 4px;
  letter-spacing: 4px;
  font-weight: 600;
  background: linear-gradient(90deg, #409eff, #0d9488);
  border: none;
}
.submit:hover { opacity: 0.92; }

.foot {
  margin-top: 18px;
  text-align: center;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.foot a {
  color: var(--el-color-primary);
  text-decoration: none;
}
.foot a:hover { text-decoration: underline; }
</style>
