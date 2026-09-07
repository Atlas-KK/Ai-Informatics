import {
  DatabaseOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons'
import { Button, Layout, Menu, Tag, Typography } from 'antd'
import type { KeyboardEvent, ReactNode } from 'react'
import { useState } from 'react'
import { navigationItems } from './navigation'
import { isAppPage, type AppPage } from './viewState'

const { Content, Header, Sider } = Layout
const { Text } = Typography

interface AppShellProps {
  activePage: AppPage
  busy?: boolean
  children: ReactNode
  onNavigate: (page: AppPage) => void
  overlay?: ReactNode
}

export function AppShell({ activePage, busy = false, children, onNavigate, overlay }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(false)
  const activateMenuItem = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    const target = event.target instanceof HTMLElement ? event.target : null
    const page = target
      ?.closest('[role="menuitem"]')
      ?.querySelector<HTMLElement>('[data-page]')
      ?.dataset.page
    if (!page || !isAppPage(page)) return
    event.preventDefault()
    onNavigate(page)
  }

  return (
    <Layout className="app-shell">
      <a className="skip-link" href="#main-content">跳到主内容</a>
      <Sider
        collapsible
        collapsed={collapsed}
        trigger={null}
        breakpoint="lg"
        onBreakpoint={setCollapsed}
      >
        <div className="brand" aria-label="AI 情报知识库">
          <DatabaseOutlined />
          <span>{collapsed ? 'AI' : 'AI 情报知识库'}</span>
        </div>
        <nav id="primary-navigation" aria-label="主导航">
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[activePage]}
            items={navigationItems}
            onKeyDown={activateMenuItem}
            onClick={({ key }) => {
              if (isAppPage(key)) onNavigate(key)
            }}
          />
        </nav>
      </Sider>
      <Layout>
        <Header className="app-header">
          <Button
            type="text"
            className="collapse-button"
            aria-label={collapsed ? '展开导航' : '收起导航'}
            aria-controls="primary-navigation"
            aria-expanded={!collapsed}
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed((value) => !value)}
          />
          <Text className="app-title">AI 产品经理情报知识库</Text>
          <Tag color="processing">Local Workspace</Tag>
        </Header>
        <Content id="main-content" role="main" tabIndex={-1} className="app-content" aria-busy={busy}>{children}</Content>
      </Layout>
      {overlay}
    </Layout>
  )
}
