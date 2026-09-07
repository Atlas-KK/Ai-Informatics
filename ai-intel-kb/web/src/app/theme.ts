import type { ThemeConfig } from 'antd'

export const appTheme: ThemeConfig = {
  token: {
    colorPrimary: '#1677ff',
    colorInfo: '#1677ff',
    colorSuccess: '#16a34a',
    colorWarning: '#d97706',
    colorError: '#dc2626',
    colorBgLayout: '#f5f7fb',
    colorBgContainer: '#ffffff',
    colorText: '#172033',
    colorTextSecondary: '#667085',
    colorBorderSecondary: '#e5eaf2',
    borderRadius: 8,
    borderRadiusLG: 12,
    fontSize: 14,
    fontFamily:
      "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif",
  },
  components: {
    Card: {
      headerFontSize: 16,
      paddingLG: 20,
    },
    Layout: {
      bodyBg: '#f5f7fb',
      headerBg: '#ffffff',
      siderBg: '#071a2f',
    },
    Menu: {
      darkItemBg: '#071a2f',
      darkItemSelectedBg: '#1677ff',
      itemBorderRadius: 8,
    },
  },
}
