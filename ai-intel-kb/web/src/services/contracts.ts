import type { ArchiveItem, Tier } from '../types'

export type { TopicSummary } from '../types'

export interface ArchivePageResponse {
  items: ArchiveItem[]
  total: number
  page: number
  page_size: number
}

export interface SearchPageResponse extends ArchivePageResponse {
  query: string
  mode: 'KEYWORD' | 'HYBRID'
  degraded: boolean
  degraded_reason: string | null
}

export type BrowseSort = 'RELEVANCE' | 'PUBLISHED_DESC' | 'SCORE_DESC' | 'TIER_PRIORITY'

export interface BrowseFilters {
  query: string
  topic?: string
  tier?: Tier
  source: string
  tag: string
  favorite?: boolean
  readState?: 'READ' | 'UNREAD'
  dateFrom: string
  dateTo: string
  minimumScore: number
  sort: BrowseSort
}
