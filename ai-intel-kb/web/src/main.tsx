import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import 'antd/dist/reset.css'
import './App.css'
import App from './App'

const root = document.getElementById('root')

if (!root) {
  throw new Error('Missing #root application mount point')
}

createRoot(root).render(
  <StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#1890ff',
          borderRadius: 2,
          fontSize: 14,
        },
      }}
    >
      <App />
    </ConfigProvider>
  </StrictMode>,
)
