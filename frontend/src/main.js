import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as Icons from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
// ★ 深色变量表与 `document.documentElement.classList.add('dark')` 一起删掉了。
//   这里原来 import 的是 element-plus 的 dark/css-vars.css，它只提供
//   `html.dark { … }` 那一套变量——留着它本身无害（没有 .dark 类就不生效），
//   但它是「哪天顺手加回深色模式」的入口。浅色站不留这个入口。
import './styles/theme.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
for (const [name, comp] of Object.entries(Icons)) {
  app.component(name, comp)
}
app.mount('#app')
