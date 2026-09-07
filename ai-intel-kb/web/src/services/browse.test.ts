import { describe, expect, it } from 'vitest'
import { buildBrowsePath, emptyBrowseFilters } from './browse'

describe('buildBrowsePath', () => {
  it('serializes all archive filters for server-side pagination', () => {
    const path = buildBrowsePath({
      query: '',
      topic: '大模型与智能体',
      tier: 'MUST_READ',
      source: 'source-primary',
      tag: 'Agent',
      favorite: true,
      readState: 'READ',
      dateFrom: '2026-09-01',
      dateTo: '2026-09-06',
      minimumScore: 80,
      sort: 'SCORE_DESC',
    }, 2, 20)

    const url = new URL(path, 'http://local.test')
    expect(url.pathname).toBe('/api/archive')
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      topic: '大模型与智能体',
      tier: 'MUST_READ',
      source: 'source-primary',
      tag: 'Agent',
      favorite: 'true',
      read_state: 'READ',
      date_from: '2026-09-01',
      date_to: '2026-09-06',
      min_score: '80',
      sort: 'SCORE_DESC',
      paged: 'true',
      page: '2',
      page_size: '20',
    })
  })

  it('uses search relevance only when a query is present', () => {
    const archive = new URL(buildBrowsePath(emptyBrowseFilters, 1, 20), 'http://local.test')
    expect(archive.pathname).toBe('/api/archive')
    expect(archive.searchParams.get('sort')).toBe('PUBLISHED_DESC')

    const search = new URL(
      buildBrowsePath({ ...emptyBrowseFilters, query: 'agent platform' }, 1, 20),
      'http://local.test',
    )
    expect(search.pathname).toBe('/api/search')
    expect(search.searchParams.get('q')).toBe('agent platform')
    expect(search.searchParams.get('sort')).toBe('RELEVANCE')
  })
})
