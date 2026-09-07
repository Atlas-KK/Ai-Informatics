import {
  BarChartOutlined,
  BookOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  HistoryOutlined,
  InboxOutlined,
  SettingOutlined,
  StarOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import type { AppPage } from './viewState'

type NavigationItem = NonNullable<MenuProps['items']>[number] & { key: AppPage }

const navigationLabel = (page: AppPage, label: string) => (
  <span data-page={page}>{label}</span>
)

export const navigationItems: NavigationItem[] = [
  { key: 'today', icon: <BarChartOutlined aria-hidden />, label: navigationLabel('today', '今日情报') },
  { key: 'topics', icon: <BookOutlined aria-hidden />, label: navigationLabel('topics', '专题档案') },
  { key: 'history', icon: <HistoryOutlined aria-hidden />, label: navigationLabel('history', '历史检索') },
  { key: 'sources', icon: <InboxOutlined aria-hidden />, label: navigationLabel('sources', '来源管理') },
  { key: 'quality', icon: <StarOutlined aria-hidden />, label: navigationLabel('quality', '质量反馈') },
  { key: 'runs', icon: <ClockCircleOutlined aria-hidden />, label: navigationLabel('runs', '运行记录') },
  { key: 'settings', icon: <SettingOutlined aria-hidden />, label: navigationLabel('settings', '系统设置') },
  { key: 'trash', icon: <DeleteOutlined aria-hidden />, label: navigationLabel('trash', '回收站') },
]
