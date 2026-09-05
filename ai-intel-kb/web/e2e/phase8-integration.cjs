const fs = require('node:fs')
const http = require('node:http')
const os = require('node:os')
const path = require('node:path')
const { spawn, spawnSync } = require('node:child_process')
const { chromium } = require('playwright')

const projectRoot = path.resolve(__dirname, '..', '..')
const webRoot = path.join(projectRoot, 'web')
const distRoot = path.join(webRoot, 'dist')
const python = path.join(projectRoot, '.venv', 'Scripts', 'python.exe')
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-intel-phase8-'))
const backendPort = 18080
const dateParts = Object.fromEntries(new Intl.DateTimeFormat('en', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
}).formatToParts(new Date()).map(({ type, value }) => [type, value]))
const reportDate = `${dateParts.year}-${dateParts.month}-${dateParts.day}`
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
  return 'application/octet-stream'
}

function waitForHealth(backend, backendOutput) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 20000
    const poll = () => {
      if (backend.exitCode !== null) {
        reject(new Error(`backend exited before health check: ${backendOutput()}`))
        return
      }
      const request = http.get(`http://127.0.0.1:${backendPort}/health`, (response) => {
        response.resume()
        if (response.statusCode === 200) return resolve()
        if (Date.now() >= deadline) return reject(new Error('backend health check timed out'))
        setTimeout(poll, 200)
      })
      request.on('error', () => {
        if (Date.now() >= deadline) reject(new Error('backend health check timed out'))
        else setTimeout(poll, 200)
      })
    }
    poll()
  })
}

async function main() {
  const backend = spawn(python, ['-B', '-m', 'ai_intel.main'], {
    cwd: projectRoot,
    env: {
      ...process.env, AI_INTEL_DATA_DIR: dataDir,
      AI_INTEL_HOST: '127.0.0.1', AI_INTEL_PORT: String(backendPort),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  })
  let backendLogs = ''
  backend.stdout.on('data', (chunk) => { backendLogs += chunk.toString() })
  backend.stderr.on('data', (chunk) => { backendLogs += chunk.toString() })
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://127.0.0.1').pathname
    const relative = pathname === '/' ? 'index.html' : pathname.replace(/^\//, '')
    const candidate = path.resolve(distRoot, relative)
    const file = candidate.startsWith(distRoot) && fs.existsSync(candidate)
      ? candidate : path.join(distRoot, 'index.html')
    response.writeHead(200, { 'Content-Type': contentType(file) })
    response.end(fs.readFileSync(file))
  })
  let browser
  try {
    await waitForHealth(backend, () => backendLogs.slice(-4000))
    const seeded = spawnSync(python, [
      '-B', path.join(projectRoot, 'scripts', 'phase8_seed_performance.py'),
      '--data-dir', dataDir, '--report-date', reportDate, '--count', '10000',
    ], { cwd: projectRoot, encoding: 'utf8', windowsHide: true })
    if (seeded.status !== 0) throw new Error(seeded.stderr || 'performance seed failed')
    process.stdout.write(seeded.stdout)
    await new Promise((resolve, reject) => {
      const onError = (error) => reject(error)
      server.once('error', onError)
      server.listen(4174, '127.0.0.1', () => {
        server.removeListener('error', onError)
        resolve()
      })
    })
    const executablePath = browserCandidates.find((value) => fs.existsSync(value))
    if (!executablePath) throw new Error('Chrome or Edge is required for browser integration E2E')
    browser = await chromium.launch({
      executablePath, headless: true,
      args: ['--disable-web-security', '--disable-site-isolation-trials'],
    })
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    page.setDefaultTimeout(30000)
    page.on('requestfailed', (request) => {
      console.error(`browser request failed: ${request.url()} ${request.failure()?.errorText}`)
    })
    page.on('pageerror', (error) => console.error(`browser page error: ${error.message}`))
    await page.route('http://127.0.0.1:8000/**', (route) => {
      route.continue({ url: route.request().url().replace(':8000', `:${backendPort}`) })
    })
    const started = performance.now()
    const dashboardResponse = page.waitForResponse(
      (response) => response.url().includes('/api/dashboard'),
    )
    await page.goto('http://127.0.0.1:4174', { waitUntil: 'domcontentloaded' })
    const dashboard = await dashboardResponse
    const dashboardPayload = await dashboard.json()
    if (!dashboard.ok() || dashboardPayload.total_count !== 10000) {
      throw new Error(`dashboard response mismatch: ${dashboard.status()} ${JSON.stringify(dashboardPayload)}`)
    }
    await page.waitForFunction(() => {
      const value = document.querySelector('.ant-statistic-content-value')?.textContent ?? ''
      return value.replace(/\D/g, '') === '10000'
    })
    const coldLoadSeconds = (performance.now() - started) / 1000
    if (coldLoadSeconds > 5) throw new Error(`10k browser cold load exceeded 5s: ${coldLoadSeconds}`)

    await page.locator('.ant-menu').getByText('来源管理').click()
    await page.getByRole('button', { name: /新增来源/ }).click()
    await page.getByLabel('名称').fill('真实集成来源')
    await page.getByLabel('URL').fill('https://integration.example.test')
    await page.getByRole('button', { name: 'OK' }).click()
    await page.getByText('真实集成来源').waitFor()
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.ant-menu').getByText('来源管理').click()
    await page.getByText('真实集成来源').waitFor()

    const filterSeconds = await page.evaluate(async () => {
      const startedAt = performance.now()
      const response = await fetch('http://127.0.0.1:8000/api/archive?topic=' + encodeURIComponent('大模型与智能体') + '&tier=IMPORTANT&limit=1000')
      if (!response.ok || (await response.json()).length !== 1000) throw new Error('10k filter response mismatch')
      return (performance.now() - startedAt) / 1000
    })
    if (filterSeconds > 2) throw new Error(`10k browser filter exceeded 2s: ${filterSeconds}`)
    console.log(JSON.stringify({
      case: 'phase8-real-browser-10k', cold_load_seconds: coldLoadSeconds,
      filter_seconds: filterSeconds, browser: executablePath, cpu: os.cpus()[0]?.model,
      cpu_count: os.cpus().length, memory_bytes: os.totalmem(), platform: os.platform(), arch: os.arch(),
    }))
  } finally {
    if (browser) await browser.close()
    if (server.listening) await new Promise((resolve) => server.close(resolve))
    if (backend.exitCode === null) {
      const backendStopped = new Promise((resolve) => backend.once('exit', resolve))
      backend.kill()
      await Promise.race([backendStopped, new Promise((resolve) => setTimeout(resolve, 3000))])
    }
    if (backend.exitCode === null && process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(backend.pid), '/t', '/f'], { windowsHide: true })
    }
    fs.rmSync(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 })
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
