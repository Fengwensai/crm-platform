<template>
  <div class="reg-page">
    <div class="aurora aurora-a"></div>
    <div class="aurora aurora-b"></div>

    <div class="card">
      <div class="brand">
        <span class="brand-mark"><el-icon :size="22" color="#fff"><UserFilled /></el-icon></span>
        <h1>员工注册</h1>
        <p>提交后需管理员审批，通过后即可登录填报</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent>
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="工号（登录用）" clearable>
            <template #prefix><el-icon><Postcard /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="name">
          <el-input v-model="form.name" placeholder="姓名" clearable>
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码（至少 6 位）" show-password>
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item prop="confirm">
          <el-input v-model="form.confirm" type="password" placeholder="确认密码" show-password @keyup.enter="onSubmit">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-button type="primary" class="submit" :loading="loading" @click="onSubmit">
          提交注册
        </el-button>
      </el-form>

      <div class="foot">
        已有账号？<router-link to="/login">返回登录</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api/request'

const router = useRouter()
const formRef = ref()
const loading = ref(false)

const form = reactive({ username: '', name: '', password: '', confirm: '' })

const rules = {
  username: [
    { required: true, message: '请输入工号', trigger: 'blur' },
    { min: 2, max: 64, message: '工号长度 2~64 位', trigger: 'blur' }
  ],
  name: [
    { required: true, message: '请输入姓名', trigger: 'blur' },
    { max: 64, message: '姓名最长 64 位', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 128, message: '密码至少 6 位', trigger: 'blur' }
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_r, v, cb) =>
        v === form.password ? cb() : cb(new Error('两次输入的密码不一致')),
      trigger: 'blur'
    }
  ]
}

async function onSubmit() {
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  loading.value = true
  try {
    await request.post('/auth/register', {
      username: form.username.trim(),
      name: form.name.trim(),
      password: form.password
    })
    await ElMessageBox.alert(
      '注册成功。请等待管理员审批通过后再登录填报。',
      '已提交',
      { confirmButtonText: '去登录', type: 'success' }
    )
    router.push('/login')
  } catch {
    // 工号重复（409）等由拦截器弹出
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.reg-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0a1220;
  overflow: hidden;
  padding: 24px 0;
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
  padding: 34px 34px 24px;
  border-radius: 18px;
  background: rgba(20, 31, 48, 0.86);
  -webkit-backdrop-filter: blur(14px);
          backdrop-filter: blur(14px);
  border: 1px solid rgba(255, 255, 255, 0.09);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
}

.brand {
  text-align: center;
  margin-bottom: 22px;
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
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 2px;
  background: linear-gradient(90deg, #ffffff 20%, #bcd6ff 60%, #8fd8ff 100%);
  -webkit-background-clip: text;
          background-clip: text;
  color: transparent;
}
.brand p {
  margin: 0;
  font-size: 12.5px;
  color: #8ba0b8;
}

.submit {
  width: 100%;
  margin-top: 4px;
  letter-spacing: 3px;
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
