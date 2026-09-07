import { fireEvent, render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import { describe, expect, it, vi } from 'vitest'
import { AppShell } from './AppShell'

describe('AppShell', () => {
  it('exposes an accessible navigation and reports menu activation', () => {
    const navigate = vi.fn()
    render(
      <ConfigProvider>
        <AppShell activePage="today" onNavigate={navigate}>
          <p>页面内容</p>
        </AppShell>
      </ConfigProvider>,
    )

    expect(screen.getByRole('navigation', { name: '主导航' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content')
    expect(screen.getByRole('link', { name: '跳到主内容' })).toHaveAttribute('href', '#main-content')
    const historyItem = screen.getByRole('menuitem', { name: '历史检索' })
    historyItem.focus()
    expect(historyItem).toHaveFocus()
    fireEvent.keyDown(historyItem, { key: 'Enter', code: 'Enter' })
    expect(navigate).toHaveBeenCalledWith('history')
  })

  it('offers an explicit keyboard-focusable collapse control', () => {
    render(
      <ConfigProvider>
        <AppShell activePage="today" onNavigate={() => undefined}>
          <p>页面内容</p>
        </AppShell>
      </ConfigProvider>,
    )

    const collapse = screen.getByRole('button', { name: '收起导航' })
    expect(collapse).toHaveAttribute('aria-controls', 'primary-navigation')
    expect(collapse).toHaveAttribute('aria-expanded', 'true')
    collapse.focus()
    expect(collapse).toHaveFocus()
    fireEvent.click(collapse)
    expect(screen.getByRole('button', { name: '展开导航' })).toHaveAttribute('aria-expanded', 'false')
  })
})
