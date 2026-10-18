import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import { router } from './router'
import { store } from './store'

// 控制台调试辅助
window.__store = store

createApp(App).use(router).use(Antd).mount('#app')
