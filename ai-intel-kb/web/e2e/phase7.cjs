const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require('playwright')

const webRoot = path.resolve(__dirname, '..')
const distRoot = path.join(webRoot, 'dist')
const browserCandidates = [
  process.env.AI_INTEL_E2E_BROWSER,
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].filter(Boolean)

function contentType(file) {
  if (file.endsWith('.html')) return 'text/html; charset=utf-8'
  if (file.endsWith('.js')) return 'text/javascript; charset=utf-8'
  if (file.endsWith('.css')) return 'text/css; charset=utf-8'
  if (file.endsWith('.svg')) return 'image/svg+xml'
  return 'application/octet-stream'
}

const item = {
  event_id: '70000000-0000-4000-8000-000000000001',
  version_no: 1,
  change_type: 'NEW',
  title: 'Agent Platform launch',
  topic: '大模型与智能体',
  summary: '产品情报摘要',
  content: '只读归档正文',
  content_hash: 'a'.repeat(64),
  score_id: 'score-1',
  quality_score: 91,
  score_version: 1,
  score_dimensions: {
    source_authority: 90, timeliness: 100, reach: 70, information_density: 90, innovation: 88,
  },
  tier: 'MUST_READ',
  published_at: '2026-09-04T01:00:00+00:00',
  source_ids: ['source-primary'],
  favorite: false,
  pinned: false,
  read_state: 'UNREAD',
  trash_state: 'ACTIVE',
  trash_reason: null,
  note: '',
  tags: ['智能体'],
}
const detail = {
  ...item,
  versions: [{
    version_no: 1,
    change_type: 'NEW',
    canonical_title: item.title,
    summary: item.summary,
    content: item.content,
    content_hash: item.content_hash,
    created_at: item.published_at,
    source_language: 'en',
    original_text: 'Original content',
    zh_translation: '中文译文',
    key_conclusions: ['结论'],
    pm_value: '产品价值',
    tags: ['智能体'],
    quality_score: 91,
    tier: 'MUST_READ',
    score_version: 1,
    score_dimensions: item.score_dimensions,
    score_rationales: { source_authority: '来自官方一手材料' },
    scored_at: item.published_at,
    evidence: [{
      evidence_id: 'evidence-1', source_id: 'source-primary',
      url: 'https://example.test/source', published_at: item.published_at, viewpoint: '来源观点',
      source_name: '官方博客', source_type: 'WEB', source_state: 'ACTIVE',
      published_at_unknown: false, first_seen_at: item.published_at,
      supporting_source_count: 1, valid_source_count: 1, coverage_percent: 100,
    }],
  }],
  topic_idea: null,
}
const generatedIdea = {
  idea_id: 'idea-1', trigger: 'MANUAL', title: '选题标题', outline: ['第一部分'],
  hook: '核心爆点', support_evidence_ids: ['evidence-1'], created_at: item.published_at,
  support_sources: [{ evidence_id: 'evidence-1', source_name: '官方博客', url: 'https://example.test/source', viewpoint: '来源观点' }],
}
const settings = {
  schedule_time: '08:30',
  selection_threshold: 70,
  tier_caps: { MUST_READ: 10, IMPORTANT: 20, EXTENDED: 20 },
  topic_order: ['大模型与智能体', 'AI 产品形态与行业应用', 'AI 产品实战', 'AI 工程安全与可靠性'],
  default_sort: 'PUBLISHED_DESC',
  github_rules: { daily_trending: true, weekly_trending: true, seven_day_star_growth: true, ai_relevance: true, whitelist: ['openai/openai-python'] },
  updated_at: '2026-09-04T00:00:00Z',
}

async function main() {
  if (!fs.existsSync(path.join(distRoot, 'index.html'))) throw new Error('web/dist is missing')
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://127.0.0.1').pathname
    const relative = pathname === '/' ? 'index.html' : pathname.replace(/^\//, '')
    const candidate = path.resolve(distRoot, relative)
    const file = candidate.startsWith(distRoot) && fs.existsSync(candidate) ? candidate : path.join(distRoot, 'index.html')
    response.writeHead(200, { 'Content-Type': contentType(file) })
    response.end(fs.readFileSync(file))
  })
  await new Promise((resolve) => server.listen(4173, '127.0.0.1', resolve))

  const executablePath = browserCandidates.find((value) => fs.existsSync(value))
  if (!executablePath) throw new Error('Chrome or Edge is required for browser E2E')
  const browser = await chromium.launch({ executablePath, headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  page.setDefaultTimeout(15000)
  page.on('pageerror', (error) => console.error('browser page error:', error))
  const mutations = []
  let expansionSearchCount = 0
  let trashed = false
  let deleted = false
  let sourceRecords = [{ source_id: 'source-primary', name: '官方博客', source_type: 'WEB', url: 'https://example.test', topic: item.topic, authority_level: 5, truncate_chars: 20000, state: 'ACTIVE' }]
  let activeVersion = 1
  let proposalSerial = 0
  const proposals = []
  const json = (route, value, status = 200) => route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(value),
  })
  await page.route('http://127.0.0.1:8000/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const key = `${request.method()} ${url.pathname}`
    if (request.method() !== 'GET') mutations.push(key)
    if (url.pathname === '/api/dashboard') return json(route, {
      report_date: '2026-09-04', window_start: '2026-08-29', total_count: 1,
      today_count: 1, items: [item],
      topic_summaries: [
        { name: '大模型与智能体', count: 1, tags: [{ name: '智能体', count: 1 }] },
        { name: 'AI 产品形态与行业应用', count: 0, tags: [] },
        { name: 'AI 产品实战', count: 0, tags: [] },
        { name: 'AI 工程安全与可靠性', count: 0, tags: [] },
      ], topic_counts: { '大模型与智能体': 1 },
      tier_counts: { MUST_READ: 1, IMPORTANT: 0, EXTENDED: 0 },
      source_counts: { 'source-primary': 1 }, change_counts: { NEW: 1, UPDATED: 0 },
      seven_day_trend: { '2026-09-04': 1 }, data_complete: true,
      latest_run: { run_id: 'run-1', report_date: '2026-09-04', trigger_type: 'SCHEDULED', status: 'WAITING_RETRY', started_at: item.published_at, finished_at: null, attempted_sources: 2, successful_sources: 1, failed_sources: 1, archived_count: 1, pending_count: 1, error_code: 'WORK_ITEMS_WAITING_RETRY', retry_count: 1 },
    })
    if (url.pathname === '/api/archive' && url.searchParams.get('trash') === 'true') return json(route, trashed && !deleted ? [{ ...item, trash_state: 'TRASHED', trash_reason: '低质量' }] : [])
    if (url.pathname === '/api/archive' && url.searchParams.get('paged') === 'true') return json(route, { items: [item], total: 1, page: 1, page_size: 20 })
    if (url.pathname === '/api/archive') return json(route, [item])
    if (url.pathname === `/api/archive/${item.event_id}` && request.method() === 'GET') return json(route, detail)
    if (url.pathname === `/api/archive/${item.event_id}/metadata`) {
      const metadata = request.postDataJSON()
      Object.assign(item, metadata)
      Object.assign(detail, metadata)
      return json(route, detail)
    }
    if (url.pathname === `/api/archive/${item.event_id}/note`) {
      detail.note = request.postDataJSON().body
      item.note = detail.note
      return json(route, { body: detail.note })
    }
    if (url.pathname === `/api/archive/${item.event_id}/trash`) {
      trashed = true
      return json(route, { status: 'TRASHED' })
    }
    if (url.pathname === `/api/archive/${item.event_id}/restore`) {
      trashed = false
      return json(route, { status: 'ACTIVE' })
    }
    if (url.pathname === `/api/archive/${item.event_id}` && request.method() === 'DELETE') {
      deleted = true
      return json(route, { status: 'DELETED' })
    }
    if (url.pathname === '/api/sources' && request.method() === 'GET') return json(route, sourceRecords)
    if (url.pathname === '/api/sources' && request.method() === 'POST') {
      const created = { source_id: 'source-new', state: 'ACTIVE', ...request.postDataJSON() }
      sourceRecords = [...sourceRecords, created]
      return json(route, created)
    }
    if (url.pathname === '/api/sources/source-primary/state') {
      sourceRecords = sourceRecords.map((source) => source.source_id === 'source-primary' ? { ...source, state: request.postDataJSON().state } : source)
      return json(route, sourceRecords[0])
    }
    if (url.pathname === '/api/sources/source-primary' && request.method() === 'DELETE') {
      sourceRecords = sourceRecords.filter((source) => source.source_id !== 'source-primary')
      return json(route, { status: 'DELETED' })
    }
    if (url.pathname === '/api/source-operations') return json(route, [{ source_id: 'source-primary', latest_collection: { created_at: item.published_at, status: 'COLLECTED', title: item.title }, latest_failure: null }])
    if (url.pathname === '/api/experts' && request.method() === 'GET') return json(route, [])
    if (url.pathname === '/api/runs') return json(route, [{ run_id: 'run-1', report_date: '2026-09-04', trigger_type: 'SCHEDULED', status: 'WAITING_RETRY', started_at: item.published_at, finished_at: null, attempted_sources: 2, successful_sources: 1, failed_sources: 1, archived_count: 1, pending_count: 1, error_code: 'WORK_ITEMS_WAITING_RETRY', retry_count: 1 }])
    if (url.pathname === '/api/runs/run-1') return json(route, {
      run_id: 'run-1', report_date: '2026-09-04', trigger_type: 'SCHEDULED', status: 'WAITING_RETRY',
      started_at: item.published_at, finished_at: item.published_at, window_start: '2026-08-29T00:00:00Z',
      window_end: item.published_at, deadline_at: item.published_at, heartbeat_at: item.published_at,
      attempted_sources: 2, successful_sources: 1, failed_sources: 1, archived_count: 1,
      pending_count: 1, error_code: 'WORK_ITEMS_WAITING_RETRY', retry_count: 1,
      work_items: [{ aggregate_version_id: 'aggregate-1', canonical_title: item.title, stage: 'SCORING', status: 'WAITING_RETRY', updated_at: item.published_at }],
      retryable_work_items: [{ aggregate_version_id: 'aggregate-1', canonical_title: item.title, stage: 'SCORING', status: 'WAITING_RETRY', updated_at: item.published_at }],
      source_failures: [{ source_id: 'source-primary', source_type: 'WEB', stage: 'FETCH', status: 'FAILED', reason: 'fixture source failure', retry_count: 1, occurred_at: item.published_at }],
      timeline: [{ event_type: 'pipeline_run_finished', created_at: item.published_at, status: 'WAITING_RETRY', error_code: 'WORK_ITEMS_WAITING_RETRY' }],
      digest: { digest_id: 'digest-1', report_date: '2026-09-04', version_no: 1, markdown_path: 'digests/2026-09-04-v0001.md', created_at: item.published_at, segments: [{ segment_id: 'segment-1', segment_no: 1, status: 'FAILED', attempt_count: 1, error_code: 'FEISHU_SEND_FAILED', updated_at: item.published_at }] },
    })
    if (url.pathname === '/api/runs/run-1/retry') return json(route, { retried: [{ aggregate_version_id: 'aggregate-1', stage: 'SCORING' }], failed: [] })
    if (url.pathname === '/api/digests/digest-1/retry-failed-segments') return json(route, { status: 'SUCCESS', retried_segment_ids: ['segment-1'], successful_segments: 1, failed_segments: 0 })
    if (url.pathname === '/api/feedback') return json(route, request.method() === 'GET' ? [{ feedback_id: 'feedback-1', score_id: 'score-1', aggregate_version_id: 'aggregate-1', canonical_title: item.title, reason: '信息密度不足', affected_dimension: 'information_density', original_score: 91, outcome: 'REMOVED', content_features: { origin: 'DETAIL' }, score_version: 1, score_revision: 1, created_at: item.published_at }] : { feedback_id: 'feedback-2' })
    if (url.pathname === '/api/settings') return json(route, settings)
    if (url.pathname === '/api/configuration-status') return json(route, { services: { semantic_search: false, expansion_search: true, intelligence_processing: true, retry_executor: true, feishu: false }, missing_items: ['语义检索服务', '飞书推送'] })
    if (url.pathname === '/api/scoring-config') return json(route, { version: 1, weights: { source_authority: 0.3, timeliness: 0.25, reach: 0.15, information_density: 0.15, innovation: 0.15 } })
    if (url.pathname === '/api/search') return json(route, {
      items: [item], total: 1, page: 1, page_size: 20,
      query: url.searchParams.get('q'), mode: 'KEYWORD', degraded: true,
      degraded_reason: 'SEMANTIC_PROVIDER_NOT_CONFIGURED',
    })
    if (url.pathname.endsWith('/expansion-search')) {
      expansionSearchCount += 1
      if (expansionSearchCount === 3) return json(route, { search_run_id: 'search-3', status: 'FAILED', error_code: 'EXPANSION_SEARCH_FAILED', results: [] })
      const resultId = `extension-${expansionSearchCount}`
      return json(route, { search_run_id: `search-${expansionSearchCount}`, status: 'SUCCEEDED', error_code: null, results: [{ result_id: resultId, title: `扩展结果 ${expansionSearchCount}`, url: `https://external.test/${expansionSearchCount}`, summary: '补充资料', source_name: 'external', score: 88 }] })
    }
    if (url.pathname.endsWith('/topic-idea')) {
      detail.topic_idea = generatedIdea
      return json(route, { status: 'SUCCEEDED', created: true, idea: generatedIdea })
    }
    if (url.pathname === '/api/extension-results/extension-1/favorite') return json(route, { event_id: 'extension-event-1', deduplicated: false })
    if (url.pathname === '/api/extension-results/extension-2/favorite') return json(route, { event_id: item.event_id, deduplicated: true })
    if (url.pathname === '/api/calibration/workbench') return json(route, {
      active_version: activeVersion,
      configs: [1, 2].filter((version) => version === 1 || proposalSerial > 0).map((version) => ({ version, weights: { source_authority: 0.3, timeliness: 0.25, reach: 0.15, information_density: 0.15, innovation: 0.15 }, source_overrides: {}, status: version === activeVersion ? 'ACTIVE' : 'INACTIVE', is_active: version === activeVersion, created_at: item.published_at })),
      proposals,
      audits: [{ audit_id: 'audit-1', old_config_version: null, new_config_version: 1, action: 'INITIALIZE', created_at: item.published_at }],
      rescore_targets: [{ aggregate_version_id: 'aggregate-1', canonical_title: item.title, score_id: 'score-1', latest_score: 91, config_version: 1, score_revision: 1, score_count: 1, created_at: item.published_at }],
    })
    if (url.pathname === '/api/calibration/proposals') {
      proposalSerial += 1
      const proposal = { proposal_id: `proposal-${proposalSerial}`, base_config_version: activeVersion, affected_dimensions: ['information_density'], suggested_weights: { source_authority: 0.29, timeliness: 0.24, reach: 0.14, information_density: 0.19, innovation: 0.14 }, estimated_impact: { scope: 'future scores only' }, sample_count: 24, uncertainty: 'LOW', decision: null, new_config_version: null, created_at: item.published_at }
      proposals.push(proposal)
      return json(route, { sample_count: 24, uncertainty: 'LOW', proposal })
    }
    if (/^\/api\/calibration\/proposal-\d+\/(confirm|reject)$/.test(url.pathname)) {
      const proposal = proposals.find((value) => url.pathname.includes(value.proposal_id))
      proposal.decision = url.pathname.endsWith('/confirm') ? 'CONFIRMED' : 'REJECTED'
      if (proposal.decision === 'CONFIRMED') {
        activeVersion = 2
        proposal.new_config_version = 2
      }
      return json(route, proposal)
    }
    if (url.pathname === '/api/calibration/config/1/rollback') {
      activeVersion = 1
      return json(route, { active_version: 1 })
    }
    if (url.pathname === '/api/calibration/rescore') return json(route, { appended: [{ aggregate_version_id: 'aggregate-1', latest_score: 91, new_score: 89, new_score_id: 'score-2', config_version: activeVersion, score_count: 2 }] })
    return json(route, { ok: true })
  })

  try {
    await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle' })
    await page.getByText('任务状态：WAITING_RETRY').waitFor()
    await page.getByText('来源构成').waitFor()
    const screenshotDir = process.env.AI_INTEL_E2E_SCREENSHOT_DIR
    if (process.env.AI_INTEL_E2E_SCREENSHOT) {
      await page.screenshot({ path: process.env.AI_INTEL_E2E_SCREENSHOT, fullPage: false })
    }
    if (screenshotDir) {
      fs.mkdirSync(screenshotDir, { recursive: true })
      await page.screenshot({ path: path.join(screenshotDir, 'dashboard-1440x1000.png'), fullPage: false })
      await page.locator('.ant-menu').getByText('专题档案').click()
      await page.getByRole('heading', { name: '专题档案' }).waitFor()
      await page.getByText(item.title).waitFor()
      await page.screenshot({ path: path.join(screenshotDir, 'topics-1440x1000.png'), fullPage: false })
      await page.locator('.ant-menu').getByText('今日情报').click()
      await page.getByText(item.title).first().waitFor()
    }
    await page.getByText(item.title).first().click()
    await page.getByText('选题建议').waitFor()
    await page.getByRole('button', { name: '收藏' }).click()
    await page.getByRole('button', { name: '置顶' }).click()
    await page.getByRole('button', { name: '标为已读' }).click()
    await page.getByRole('textbox', { name: '个人笔记' }).fill('UI-8 浏览器持久化笔记')
    await page.getByRole('button', { name: '保存笔记' }).click()
    await page.getByText('笔记已保存').waitFor()
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByText(item.title).first().click()
    await page.getByRole('button', { name: '已收藏' }).waitFor()
    await page.getByRole('button', { name: '已置顶' }).waitFor()
    await page.getByRole('button', { name: '标为未读' }).waitFor()
    if (await page.getByRole('textbox', { name: '个人笔记' }).inputValue() !== 'UI-8 浏览器持久化笔记') throw new Error('metadata or note did not persist after refresh')
    if (screenshotDir) {
      await page.screenshot({ path: path.join(screenshotDir, 'detail-body-1440x1000.png'), fullPage: false })
      await page.getByRole('tab', { name: '来源与观点' }).click()
      await page.getByText('来源覆盖率').waitFor()
      await page.screenshot({ path: path.join(screenshotDir, 'detail-evidence-1440x1000.png'), fullPage: false })
      await page.getByRole('tab', { name: '历史版本' }).click()
      await page.getByText('当前查看 v1').waitFor()
      await page.screenshot({ path: path.join(screenshotDir, 'detail-versions-1440x1000.png'), fullPage: false })
    }
    await page.getByRole('tab', { name: '选题建议' }).click()
    await page.getByRole('button', { name: '生成选题建议' }).click()
    await page.getByRole('heading', { name: '选题标题' }).waitFor()
    if (screenshotDir) {
      await page.getByText('核心爆点', { exact: true }).first().waitFor()
      await page.screenshot({ path: path.join(screenshotDir, 'detail-ideas-1440x1000.png'), fullPage: false })
    }
    await page.getByRole('button', { name: '扩展搜索' }).click()
    await page.getByText('扩展结果 1').waitFor()
    await page.getByRole('button', { name: '收藏并归档' }).click()
    await page.locator('.ant-popover:visible, .ant-modal:visible').getByRole('button', { name: 'OK' }).click()
    await page.getByText('已新建正式情报').waitFor()
    await page.getByText('已新建正式情报').scrollIntoViewIfNeeded()
    if (screenshotDir) await page.screenshot({ path: path.join(screenshotDir, 'expansion-new-1440x1000.png'), fullPage: false })
    await page.getByRole('button', { name: '扩展搜索' }).click()
    await page.getByText('扩展结果 2').waitFor()
    await page.getByRole('button', { name: '收藏并归档' }).click()
    await page.locator('.ant-popover:visible, .ant-modal:visible').getByRole('button', { name: 'OK' }).click()
    await page.getByText('已关联已有情报').waitFor()
    await page.getByText('已关联已有情报').scrollIntoViewIfNeeded()
    if (screenshotDir) await page.screenshot({ path: path.join(screenshotDir, 'expansion-deduplicated-1440x1000.png'), fullPage: false })
    await page.getByRole('button', { name: '扩展搜索' }).click()
    await page.getByText('扩展搜索失败；原情报未发生变化。').waitFor()
    await page.getByText('扩展搜索失败；原情报未发生变化。').scrollIntoViewIfNeeded()
    if (screenshotDir) await page.screenshot({ path: path.join(screenshotDir, 'expansion-failure-1440x1000.png'), fullPage: false })
    await page.getByRole('button', { name: '剔除并移入回收站' }).click()
    await page.getByPlaceholder('请说明内容质量问题').fill('内容不符合当前关注方向')
    await page.locator('.ant-popover:visible, .ant-modal:visible').getByRole('button', { name: 'OK' }).click()

    await page.locator('.ant-menu').getByText('历史检索').click()
    await page.getByPlaceholder('检索标题、摘要、正文、来源、标签和笔记').fill('Agent')
    await page.getByRole('button', { name: /检索/ }).click()
    await page.getByText('当前使用关键词检索').waitFor()
    if (screenshotDir) {
      await page.locator('.ant-message').waitFor({ state: 'hidden' })
      await page.screenshot({ path: path.join(screenshotDir, 'history-search-1440x1000.png'), fullPage: false })
    }

    await page.locator('.ant-menu').getByText('来源管理').click()
    await page.getByRole('heading', { name: '来源管理' }).waitFor()
    if (screenshotDir) {
      await page.screenshot({ path: path.join(screenshotDir, 'sources-information-1440x1000.png'), fullPage: false })
      await page.getByRole('tab', { name: '专家白名单' }).click()
      await page.screenshot({ path: path.join(screenshotDir, 'sources-experts-1440x1000.png'), fullPage: false })
      await page.getByRole('tab', { name: 'GitHub 规则' }).click()
      await page.getByText('本地 7 日 Star 增长').waitFor()
      await page.screenshot({ path: path.join(screenshotDir, 'sources-github-1440x1000.png'), fullPage: false })
      await page.getByRole('tab', { name: '信息源' }).click()
    }
    await page.getByRole('button', { name: /新增来源/ }).click()
    await page.getByLabel('名称').fill('新增来源')
    await page.getByLabel('URL').fill('not-a-valid-url')
    const sourcePostsBeforeValidation = mutations.filter((value) => value === 'POST /api/sources').length
    await page.locator('.ant-popover:visible, .ant-modal:visible').getByRole('button', { name: 'OK' }).click()
    await page.locator('.ant-form-item-explain-error').waitFor()
    if (mutations.filter((value) => value === 'POST /api/sources').length !== sourcePostsBeforeValidation) throw new Error('invalid source URL bypassed client validation')
    await page.getByLabel('URL').fill('https://new.example.test')
    await page.locator('.ant-popover:visible, .ant-modal:visible').getByRole('button', { name: 'OK' }).click()
    await page.getByText('来源已保存').waitFor()
    await page.getByRole('button', { name: /暂\s*停/ }).first().click()
    await page.getByRole('button', { name: /恢\s*复/ }).first().click()
    await page.getByRole('button', { name: /删\s*除/ }).first().click()
    await page.locator('.ant-popover:visible, .ant-modal:visible').getByRole('button', { name: 'OK' }).click()
    await page.getByText('已停止后续采集').waitFor()

    await page.locator('.ant-menu').getByText('质量反馈').click()
    await page.getByRole('heading', { name: '质量反馈与评分校准' }).waitFor()
    if (screenshotDir) {
      await page.locator('.ant-message').waitFor({ state: 'hidden' })
      await page.screenshot({ path: path.join(screenshotDir, 'quality-feedback-1440x1000.png'), fullPage: false })
    }
    await page.getByRole('tab', { name: '校准工作台' }).click()
    await page.getByRole('button', { name: '基于当前反馈生成建议' }).click()
    await page.getByText('待确认建议 · 基于 score-v1').waitFor()
    await page.getByRole('button', { name: '审核并确认' }).click()
    await page.locator('.ant-popover:visible, .ant-modal:visible').getByRole('button', { name: 'OK' }).click()
    await page.getByText('新评分版本已启用').waitFor()
    await page.getByRole('button', { name: '基于当前反馈生成建议' }).click()
    await page.getByText('待确认建议 · 基于 score-v2').waitFor()
    if (screenshotDir) {
      await page.screenshot({ path: path.join(screenshotDir, 'quality-calibration-1440x1000.png'), fullPage: false })
    }
    await page.getByRole('button', { name: '拒绝建议' }).click()
    await page.getByText('校准建议已拒绝').waitFor()
    await page.getByRole('tab', { name: '版本历史' }).click()
    await page.getByLabel('选择历史评分版本').click()
    await page.getByText('score-v1', { exact: true }).last().click()
    await page.getByRole('button', { name: '确认回退' }).click()
    await page.locator('.ant-popover:visible, .ant-modal:visible').getByRole('button', { name: 'OK' }).click()
    await page.getByText('已回退到评分配置 v1').waitFor()
    await page.getByRole('tab', { name: '历史重评分' }).click()
    await page.getByRole('checkbox').last().check()
    await page.getByRole('button', { name: '执行历史重评分' }).click()
    await page.locator('.ant-popover:visible').filter({ hasText: '确认重评' }).getByRole('button', { name: 'OK' }).click({ force: true })
    await page.waitForTimeout(500)
    if (!mutations.includes('POST /api/calibration/rescore')) throw new Error('historical rescore confirmation did not submit')

    await page.locator('.ant-menu').getByText('运行记录').click()
    await page.getByText('本地日报已保留').waitFor()
    if (screenshotDir) await page.screenshot({ path: path.join(screenshotDir, 'runs-detail-1440x1000.png'), fullPage: false })
    await page.getByRole('button', { name: '重试失败阶段及后续' }).click()
    await page.getByRole('button', { name: '仅重发失败分段' }).click()

    await page.locator('.ant-menu').getByText('系统设置').click()
    await page.getByText('采集窗口', { exact: true }).waitFor()
    if (screenshotDir) {
      await page.locator('.ant-message').waitFor({ state: 'hidden' })
      await page.screenshot({ path: path.join(screenshotDir, 'settings-schedule-1440x1000.png'), fullPage: false })
      await page.getByRole('tab', { name: '评分分层' }).click()
      await page.getByText('当前评分配置 v1').waitFor()
      await page.screenshot({ path: path.join(screenshotDir, 'settings-score-1440x1000.png'), fullPage: false })
      await page.getByRole('tab', { name: '显示顺序' }).click()
      await page.screenshot({ path: path.join(screenshotDir, 'settings-order-1440x1000.png'), fullPage: false })
      await page.getByRole('tab', { name: '服务状态' }).click()
      await page.getByText('存在未配置服务').waitFor()
      await page.screenshot({ path: path.join(screenshotDir, 'settings-services-1440x1000.png'), fullPage: false })
      await page.getByRole('tab', { name: '采集调度' }).click()
    }
    await page.getByRole('button', { name: '保存设置' }).click()

    await page.locator('.ant-menu').getByText('回收站').click()
    await page.getByText('低质量').waitFor()
    await page.getByRole('button', { name: /恢\s*复/ }).last().click()
    await page.getByText('回收站为空').waitFor()
    await page.locator('[data-menu-id$="-today"]').click({ force: true })
    await page.getByText(item.title).first().click()
    await page.getByRole('button', { name: '剔除并移入回收站' }).click()
    await page.getByPlaceholder('请说明内容质量问题').fill('验证永久删除闭环')
    await page.locator('.ant-popover:visible, .ant-modal:visible').getByRole('button', { name: 'OK' }).click()
    await page.locator('.ant-menu').getByText('回收站').click()
    await page.getByRole('button', { name: /永久删除/ }).click()
    await page.locator('.ant-popover:visible, .ant-modal:visible').getByRole('button', { name: 'OK' }).click()
    await page.getByText('回收站为空').waitFor()

    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByText(item.title).first().waitFor()
    const viewportOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
    if (viewportOverflow) throw new Error('small-screen layout causes document-level horizontal overflow')
    if (screenshotDir) await page.screenshot({ path: path.join(screenshotDir, 'mobile-390x844.png'), fullPage: false })
    await page.keyboard.press('Tab')
    if (await page.locator(':focus').textContent() !== '跳到主内容') throw new Error('skip link is not the first keyboard focus target')
    if (await page.locator('main#main-content').count() !== 1) throw new Error('main content landmark is missing')

    const required = [
      `POST /api/archive/${item.event_id}/expansion-search`,
      `POST /api/archive/${item.event_id}/topic-idea`,
      `PATCH /api/archive/${item.event_id}/metadata`,
      `PUT /api/archive/${item.event_id}/note`,
      'POST /api/extension-results/extension-1/favorite',
      'POST /api/extension-results/extension-2/favorite',
      'POST /api/feedback',
      `POST /api/archive/${item.event_id}/trash`,
      'POST /api/sources',
      'POST /api/sources/source-primary/state',
      'DELETE /api/sources/source-primary',
      'POST /api/calibration/proposals',
      'POST /api/calibration/proposal-1/confirm',
      'POST /api/calibration/proposal-2/reject',
      'POST /api/calibration/config/1/rollback',
      'POST /api/calibration/rescore',
      'POST /api/runs/run-1/retry',
      'POST /api/digests/digest-1/retry-failed-segments',
      'PUT /api/settings',
      `POST /api/archive/${item.event_id}/restore`,
      `DELETE /api/archive/${item.event_id}`,
    ]
    for (const expected of required) {
      if (!mutations.includes(expected)) throw new Error(`missing browser mutation: ${expected}`)
    }
    if (mutations.filter((value) => value === `POST /api/archive/${item.event_id}/expansion-search`).length !== 3) {
      throw new Error('expansion search success/deduplication/failure branches were not all exercised')
    }
    console.log(`Phase 7 browser E2E passed (${required.length} mutations verified).`)
  } finally {
    await browser.close()
    await new Promise((resolve) => server.close(resolve))
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
