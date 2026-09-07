export const appPages = [
  'today',
  'topics',
  'history',
  'sources',
  'quality',
  'runs',
  'settings',
  'trash',
] as const

export type AppPage = (typeof appPages)[number]

export interface ViewState {
  page: AppPage
  detailEventId: string | null
  selectedTopic: string | null
}

export const initialViewState: ViewState = {
  page: 'today',
  detailEventId: null,
  selectedTopic: null,
}

export function isAppPage(value: string): value is AppPage {
  return appPages.includes(value as AppPage)
}
