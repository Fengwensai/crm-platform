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
.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0a1220;
  overflow: hidden;
}
.aurora {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
}
.aurora-a {
  width: 620px; height: 620px;
  left: -160px; top: -180px;
  background: radial-gradient(circle, rgba(64, 158, 255, 0.30), transparent 70%);
}
.aurora-b {
  width: 560px; height: 560px;
  right: -140px; bottom: -180px;
  background: radial-gradient(circle, rgba(0, 201, 176, 0.22), transparent 70%);
}

.card {
  position: relative;
  width: 380px;
  padding: 36px 34px 26px;
  border-radius: 18px;
  background: rgba(20, 31, 48, 0.86);
  -webkit-backdrop-filter: blur(14px);
          backdrop-filter: blur(14px);
  border: 1px solid rgba(255, 255, 255, 0.09);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
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
  background: linear-gradient(135deg, #409eff, #00c9b0);
  box-shadow: 0 8px 24px rgba(64, 158, 255, 0.42), inset 0 1px 0 rgba(255, 255, 255, 0.35);
  margin-bottom: 14px;
}
.brand h1 {
  margin: 0 0 6px;
  font-size: 21px;
  font-weight: 700;
  letter-spacing: 2px;
  background: linear-gradient(90deg, #ffffff 20%, #bcd6ff 60%, #8fd8ff 100%);
  -webkit-background-clip: text;
          background-clip: text;
  color: transparent;
}
.brand p {
  margin: 0;
  font-size: 13px;
  color: #8ba0b8;
  letter-spacing: 1px;
}

.submit {
  width: 100%;
  margin-top: 4px;
  letter-spacing: 4px;
  font-weight: 600;
  background: linear-gradient(90deg, #409eff, #00c9b0);
  border: none;
}
.submit:hover { opacity: 0.92; }

.foot {
  margin-top: 18px;
  text-align: center;
  font-size: 13px;
  color: #8ba0b8;
}
.foot a {
  color: #66b1ff;
  text-decoration: none;
}
.foot a:hover { text-decoration: underline; }
</style>
