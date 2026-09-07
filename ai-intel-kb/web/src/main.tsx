import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import 'antd/dist/reset.css'
import './styles/tokens.css'
import './App.css'
import App from './App'
import { appTheme } from './app/theme'

const root = document.getElementById('root')

if (!root) {
  throw new Error('Missing #root application mount point')
}

createRoot(root).render(
  <StrictMode>
    <ConfigProvider theme={appTheme}>
      <App />
    </ConfigProvider>
  </StrictMode>,
)
