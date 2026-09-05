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
    evidence: [{
      evidence_id: 'evidence-1', source_id: 'source-primary',
      url: 'https://example.test/source', published_at: item.published_at, viewpoint: '来源观点',
    }],
  }],
  topic_idea: { title: '选题标题', outline: ['第一部分'], hook: '核心爆点' },
}
const settings = {
  schedule_time: '08:30',
  selection_threshold: 70,
  tier_caps: { MUST_READ: 3, IMPORTANT: 7, EXTENDED: 10 },
  topic_order: ['大模型与智能体', 'AI 产品形态与行业应用', 'AI 产品实战', 'AI 工程安全与可靠性'],
  default_sort: 'PUBLISHED_DESC',
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
      items: [item], topic_counts: { '大模型与智能体': 1 },
      tier_counts: { MUST_READ: 1, IMPORTANT: 0, EXTENDED: 0 },
      source_counts: { 'source-primary': 1 }, change_counts: { NEW: 1, UPDATED: 0 },
      seven_day_trend: { '2026-09-04': 1 }, data_complete: true,
      latest_run: { run_id: 'run-1', report_date: '2026-09-04', trigger_type: 'SCHEDULED', status: 'WAITING_RETRY', started_at: item.published_at, finished_at: null, attempted_sources: 2, successful_sources: 1, failed_sources: 1, archived_count: 1, pending_count: 1, error_code: 'WORK_ITEMS_WAITING_RETRY', retry_count: 1 },
    })
    if (url.pathname === '/api/archive' && url.searchParams.get('trash') === 'true') return json(route, [{ ...item, trash_state: 'TRASHED', trash_reason: '低质量' }])
    if (url.pathname === '/api/archive') return json(route, [item])
    if (url.pathname === `/api/archive/${item.event_id}`) return json(route, detail)
    if (url.pathname === '/api/sources' && request.method() === 'GET') return json(route, [{ source_id: 'source-primary', name: '官方博客', source_type: 'WEB', url: 'https://example.test', topic: item.topic, authority_level: 5, truncate_chars: 20000, state: 'ACTIVE' }])
    if (url.pathname === '/api/experts' && request.method() === 'GET') return json(route, [])
    if (url.pathname === '/api/runs') return json(route, [{ run_id: 'run-1', report_date: '2026-09-04', trigger_type: 'SCHEDULED', status: 'WAITING_RETRY', started_at: item.published_at, finished_at: null, attempted_sources: 2, successful_sources: 1, failed_sources: 1, archived_count: 1, pending_count: 1, error_code: 'WORK_ITEMS_WAITING_RETRY', retry_count: 1 }])
    if (url.pathname === '/api/feedback') return json(route, request.method() === 'GET' ? [{ feedback_id: 'feedback-1', reason: '信息密度不足', affected_dimension: 'information_density', original_score: 91, created_at: item.published_at }] : { feedback_id: 'feedback-2' })
    if (url.pathname === '/api/settings') return json(route, settings)
    if (url.pathname === '/api/configuration-status') return json(route, { semantic_search: false, expansion_search: true, intelligence_processing: true, retry_executor: true, feishu: false })
    if (url.pathname === '/api/search') return json(route, { items: [item], mode: 'KEYWORD', degraded: true })
    if (url.pathname.endsWith('/expansion-search')) return json(route, { status: 'SUCCEEDED', error_code: null, results: [{ result_id: 'extension-1', title: '扩展结果', url: 'https://external.test', summary: '补充资料', source_name: 'external', score: 88 }] })
    if (url.pathname === '/api/calibration/proposals') return json(route, { sample_count: 3, uncertainty: 'LOW', proposal: { proposal_id: 'proposal-1', affected_dimensions: ['information_density'], suggested_weights: { information_density: 0.2 }, estimated_impact: { changed_items: 2 } } })
    return json(route, { ok: true })
  })

  try {
    await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle' })
    await page.getByText('任务状态：WAITING_RETRY').waitFor()
    await page.getByText('来源构成').waitFor()
    await page.getByText(item.title).first().click()
    await page.getByText('选题建议').waitFor()
    await page.getByRole('button', { name: '搜索互联网' }).click()
    await page.getByText('扩展结果').waitFor()
    await page.getByRole('button', { name: '收藏并归档' }).click()
    await page.getByRole('button', { name: '剔除并移入回收站' }).click()
    await page.getByPlaceholder('请说明内容质量问题').fill('内容不符合当前关注方向')
    await page.getByRole('button', { name: 'OK' }).click()

    await page.locator('.ant-menu').getByText('历史检索').click()
    await page.getByPlaceholder('检索标题、摘要、正文、来源、标签和笔记').fill('Agent')
    await page.getByRole('button', { name: /检索/ }).click()
    await page.getByText('关键词检索（语义服务未配置）').waitFor()

    await page.locator('.ant-menu').getByText('来源管理').click()
    await page.getByRole('button', { name: /新增来源/ }).click()
    await page.getByLabel('名称').fill('新增来源')
    await page.getByLabel('URL').fill('https://new.example.test')
    await page.getByRole('button', { name: 'OK' }).click()

    await page.locator('.ant-menu').getByText('质量反馈').click()
    await page.getByRole('button', { name: '发起校准评估' }).click()
    await page.getByText('评分校准建议').waitFor()
    await page.getByRole('button', { name: /拒\s*绝/ }).click()

    await page.locator('.ant-menu').getByText('运行记录').click()
    await page.getByRole('button', { name: '重试失败阶段' }).click()

    await page.locator('.ant-menu').getByText('系统设置').click()
    await page.getByText('服务配置状态').waitFor()
    await page.getByRole('button', { name: '保存设置' }).click()

    await page.locator('.ant-menu').getByText('回收站').click()
    await page.getByText('低质量').waitFor()

    const required = [
      `POST /api/archive/${item.event_id}/expansion-search`,
      'POST /api/extension-results/extension-1/favorite',
      'POST /api/feedback',
      `POST /api/archive/${item.event_id}/trash`,
      'POST /api/sources',
      'POST /api/calibration/proposals',
      'POST /api/calibration/proposal-1/reject',
      'POST /api/runs/run-1/retry',
      'PUT /api/settings',
    ]
    for (const expected of required) {
      if (!mutations.includes(expected)) throw new Error(`missing browser mutation: ${expected}`)
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
