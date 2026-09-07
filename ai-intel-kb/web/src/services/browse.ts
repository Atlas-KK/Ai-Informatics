import type { BrowseFilters } from './contracts'

function appendOptional(params: URLSearchParams, key: string, value: string | undefined) {
  if (value) params.set(key, value)
}

export function buildBrowsePath(filters: BrowseFilters, page: number, pageSize: number) {
  const params = new URLSearchParams()
  appendOptional(params, 'topic', filters.topic)
  appendOptional(params, 'tier', filters.tier)
  appendOptional(params, 'source', filters.source.trim())
  appendOptional(params, 'tag', filters.tag.trim())
  if (filters.favorite !== undefined) params.set('favorite', String(filters.favorite))
  appendOptional(params, 'read_state', filters.readState)
  appendOptional(params, 'date_from', filters.dateFrom)
  appendOptional(params, 'date_to', filters.dateTo)
  if (filters.minimumScore > 0) params.set('min_score', String(filters.minimumScore))
  params.set('page', String(page))
  params.set('page_size', String(pageSize))

  const query = filters.query.trim()
  if (query) {
    params.set('q', query)
    params.set('sort', filters.sort)
    return `/api/search?${params.toString()}`
  }
  params.set('sort', filters.sort === 'RELEVANCE' ? 'PUBLISHED_DESC' : filters.sort)
  params.set('paged', 'true')
  return `/api/archive?${params.toString()}`
}

export const emptyBrowseFilters: BrowseFilters = {
  query: '',
  source: '',
  tag: '',
  dateFrom: '',
  dateTo: '',
  minimumScore: 0,
  sort: 'RELEVANCE',
}
