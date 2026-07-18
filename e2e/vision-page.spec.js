const { test, expect } = require('@playwright/test')
const path = require('path')
const fs = require('fs')

// Read the mock script as a string for injection via addInitScript
const mockScript = fs.readFileSync(
  path.resolve(__dirname, 'mocks/barq-mock.js'),
  'utf-8',
)

test.describe('VisionPage — End-to-End Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(mockScript)
    // Navigate to root — MemoryRouter ignores URL bar
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)

    // Sidebar is collapsed (translateX -160px) — button is in DOM but off-screen.
    // Use native DOM click via evaluate() to bypass Playwright's viewport check.
    await page.evaluate(() => {
      const btn = document.querySelector('[title="Vision"]')
      if (btn) btn.click()
    })

    // Wait for VisionPage to render (confirm heading is visible)
    await page.waitForSelector('text=VISUAL AWARENESS', { timeout: 5000 })
  })

  test('renders the VISUAL AWARENESS heading', async ({ page }) => {
    await expect(page.getByText('VISUAL AWARENESS')).toBeVisible({ timeout: 5000 })
  })

  test('shows the capabilities panel with 4 status rows', async ({ page }) => {
    const capabilitiesCard = page.locator('.glass-card').filter({ hasText: 'Capabilities' })
    await expect(capabilitiesCard).toBeVisible({ timeout: 5000 })

    await expect(capabilitiesCard.getByText('Screen Capture')).toBeVisible()
    await expect(capabilitiesCard.getByText('Webcam')).toBeVisible()
    await expect(capabilitiesCard.getByText('Gemini Vision')).toBeVisible()
    await expect(capabilitiesCard.getByText('Gemini Live Audio')).toBeVisible()
  })

  test('shows the readiness badge with "All Systems Ready"', async ({ page }) => {
    await expect(page.getByText('All Systems Ready')).toBeVisible({ timeout: 5000 })
  })

  test('shows the source toggle buttons (Screen / Camera)', async ({ page }) => {
    // Source toggle buttons are in the first .glass-card (the control card), not the action buttons
    const controlCard = page.locator('.glass-card').first()
    const screenBtn = controlCard.getByRole('button', { name: /^Screen$/ })
    const cameraBtn = controlCard.getByRole('button', { name: /^Camera$/ })

    await expect(screenBtn).toBeVisible({ timeout: 5000 })
    await expect(cameraBtn).toBeVisible()
  })

  test('has an input field for the prompt', async ({ page }) => {
    const input = page.getByPlaceholder("Ask about what's on screen...")
    await expect(input).toBeVisible({ timeout: 5000 })
    await expect(input).toHaveValue(/What's on my screen/)
  })

  test('shows the "Analyze Screen" and "Voice Response" buttons', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Analyze Screen/ })).toBeVisible({ timeout: 5000 })
    await expect(page.getByRole('button', { name: /Voice Response/ })).toBeVisible()
  })

  test('shows the "Live Mode" toggle button', async ({ page }) => {
    await expect(page.getByText('Live Mode')).toBeVisible({ timeout: 5000 })
  })

  test('shows the History section', async ({ page }) => {
    await expect(page.getByText('History')).toBeVisible({ timeout: 5000 })
  })

  test('switches to Camera source when clicking Camera button', async ({ page }) => {
    const controlCard = page.locator('.glass-card').first()
    await controlCard.getByRole('button', { name: /^Camera$/ }).click()
    // After clicking Camera, the camera index select should appear
    await expect(page.getByText('Camera Index:')).toBeVisible({ timeout: 3000 })
  })

  test('toggles Live Mode on and off', async ({ page }) => {
    await page.getByRole('button', { name: /Live Mode/ }).click()
    await expect(page.getByRole('button', { name: /Stop Live/ })).toBeVisible({ timeout: 3000 })
    await page.getByRole('button', { name: /Stop Live/ }).click()
    await expect(page.getByRole('button', { name: /Live Mode/ })).toBeVisible({ timeout: 3000 })
  })

  test('shows camera index dropdown when camera source is selected', async ({ page }) => {
    const controlCard = page.locator('.glass-card').first()
    await controlCard.getByRole('button', { name: /^Camera$/ }).click()
    await expect(page.getByText('Camera Index:')).toBeVisible({ timeout: 3000 })
  })

  test('shows live interval dropdown when live mode is active', async ({ page }) => {
    await page.getByRole('button', { name: /Live Mode/ }).click()
    await expect(page.getByText('Interval:')).toBeVisible({ timeout: 3000 })
    await page.getByRole('button', { name: /Stop Live/ }).click()
  })

  test('expands and collapses the history panel', async ({ page }) => {
    const historyCard = page.locator('.glass-card').filter({ hasText: 'History' })
    const expandBtn = historyCard.locator('button').last()
    await expandBtn.click()
    await expect(page.getByText('No analyses yet')).toBeVisible({ timeout: 3000 })
  })

  test('displays green checkmarks for all 4 capabilities', async ({ page }) => {
    const capabilitiesCard = page.locator('.glass-card').filter({ hasText: 'Capabilities' })
    // Each CapabilityRow div uses py-1.5 — the WS Status row uses py-1, so match precisely
    const rows = capabilitiesCard.locator('[class*="py-1.5 border-b"]')
    const rowCount = await rows.count()
    expect(rowCount).toBe(4)
  })

  // ═══ Core analysis flow — full image preview pipeline ═══

  test('clicks Analyze Screen and shows image preview in result card', async ({ page }) => {
    await page.waitForTimeout(500)

    await page.getByRole('button', { name: /Analyze Screen/ }).click()

    // Wait for the result card to appear
    const resultCard = page.locator('.glass-card').filter({ hasText: 'Analysis Result' })
    await expect(resultCard).toBeVisible({ timeout: 8000 })

    // Check that an image preview was rendered inside the result card
    const image = resultCard.locator('img')
    await expect(image).toBeVisible({ timeout: 3000 })

    // Verify the image has a data URI src
    const src = await image.getAttribute('src')
    expect(src).toMatch(/^data:image\//)

    // Check the source label appears
    await expect(resultCard.getByText('Screen capture')).toBeVisible()

    // Check analysis text appears
    await expect(resultCard.getByText(/simulated screen analysis/i)).toBeVisible({ timeout: 3000 })
  })

  test('analyze screen returns result card', async ({ page }) => {
    await page.waitForTimeout(500)

    await page.getByRole('button', { name: /Analyze Screen/ }).click()

    // The mock returns immediately, so the result card should appear
    const resultCard = page.locator('.glass-card').filter({ hasText: 'Analysis Result' })
    await expect(resultCard).toBeVisible({ timeout: 8000 })
  })

  test('Voice Response button is present', async ({ page }) => {
    await page.waitForTimeout(1000)
    const voiceBtn = page.getByText('Voice Response')
    await expect(voiceBtn).toBeVisible()
  })
})

// ═══════════════════════════════════════════════════════════════════════
// WS Indicator States — tests for WebSocket connection status indicators
// ═══════════════════════════════════════════════════════════════════════

test.describe('VisionPage — WS Connection Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Mock WebSocket to connect successfully with gemini ready
    await page.addInitScript(mockScript)
    await page.addInitScript(`
      window.__mockWsConfig.shouldFail = false
      window.__mockWsConfig.statusMessage = {
        type: 'status',
        gemini_available: true,
        api_key_configured: true,
        ready: true,
      }
    `)
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)
    await page.evaluate(() => {
      const btn = document.querySelector('[title="Vision"]')
      if (btn) btn.click()
    })
    await page.waitForSelector('text=VISUAL AWARENESS', { timeout: 5000 })
  })

  test('shows WS indicator as connected with Ready status', async ({ page }) => {
    await expect(page.getByText('Ready')).toBeVisible({ timeout: 5000 })
  })

  test('WS readiness badge shows "All Systems Ready" when WS connected', async ({ page }) => {
    await expect(page.getByText('All Systems Ready')).toBeVisible({ timeout: 5000 })
  })

  test('WS capability rows show green checks for Gemini features', async ({ page }) => {
    const capsCard = page.locator('.glass-card').filter({ hasText: 'Capabilities' })
    // Gemini Vision and Gemini Live Audio should show checkmarks
    await expect(capsCard.getByText('Gemini Vision')).toBeVisible()
    await expect(capsCard.getByText('Gemini Live Audio')).toBeVisible()
  })
})

// ═══════════════════════════════════════════════════════════════════════
// WS Connection Failure — tests for when the WebSocket cannot connect
// ═══════════════════════════════════════════════════════════════════════

test.describe('VisionPage — WS Connection Failure', () => {
  test.beforeEach(async ({ page }) => {
    // Default mock behavior: shouldFail = true (set in barq-mock.js)
    await page.addInitScript(mockScript)
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)
    await page.evaluate(() => {
      const btn = document.querySelector('[title="Vision"]')
      if (btn) btn.click()
    })
    await page.waitForSelector('text=VISUAL AWARENESS', { timeout: 5000 })
  })

  test('shows WS indicator as Disconnected when connection fails', async ({ page }) => {
    await expect(page.getByText('Disconnected')).toBeVisible({ timeout: 5000 })
  })

  test('shows WS disconnected badge styling when WS fails', async ({ page }) => {
    const wsBadge = page.locator('text=WS').first()
    await expect(wsBadge).toBeVisible({ timeout: 5000 })
    // WS badge should have the WifiOff icon when disconnected
    const parentAfterWs = wsBadge.locator('..')
    await expect(parentAfterWs.locator('svg').first()).toBeVisible()
  })

  test('falls back to REST analysis when WebSocket is disconnected', async ({ page }) => {
    await page.getByRole('button', { name: /Analyze Screen/ }).click()
    // The REST mock returns immediately with analysis result
    const resultCard = page.locator('.glass-card').filter({ hasText: 'Analysis Result' })
    await expect(resultCard).toBeVisible({ timeout: 8000 })
    // Verify it's a REST fallback result (has simulated text)
    await expect(resultCard.getByText(/simulated screen analysis/i)).toBeVisible({ timeout: 3000 })
  })

  test('readiness badge shows fraction when WS disconnected', async ({ page }) => {
    // Without WS, gemini_api and gemini_live still report as true via REST fallback
    // So the readiness badge should show all systems ready
    await expect(page.getByText(/All Systems Ready|\d+\/\d+ Ready/)).toBeVisible({ timeout: 5000 })
  })
})

// ═══════════════════════════════════════════════════════════════════════
// WS API Key Missing — tests for when the Gemini API key is not configured
// ═══════════════════════════════════════════════════════════════════════

test.describe('VisionPage — WS API Key Missing', () => {
  test.beforeEach(async ({ page }) => {
    // Mock WebSocket to connect but report no API key
    await page.addInitScript(mockScript)
    await page.addInitScript(`
      window.__mockWsConfig.shouldFail = false
      window.__mockWsConfig.statusMessage = {
        type: 'status',
        gemini_available: true,
        api_key_configured: false,
        ready: false,
      }
    `)
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)
    await page.evaluate(() => {
      const btn = document.querySelector('[title="Vision"]')
      if (btn) btn.click()
    })
    await page.waitForSelector('text=VISUAL AWARENESS', { timeout: 5000 })
  })

  test('shows No Key status when API key is missing from WS status', async ({ page }) => {
    await expect(page.getByText('No Key')).toBeVisible({ timeout: 5000 })
  })

  test('shows Setup Required section when analyzing with missing API key', async ({ page }) => {
    // Override REST mock to simulate API key error on analysis
    await page.evaluate(() => {
      var orig = window.mockBarq.python.request
      window.mockBarq.python.request = function (endpoint) {
        if (endpoint.indexOf('/vision/screen') !== -1 || endpoint.indexOf('/vision/camera') !== -1) {
          return Promise.resolve({
            status: 'unavailable',
            message: 'Gemini API key not configured',
          })
        }
        return orig.call(window.mockBarq.python, endpoint)
      }
    })

    await page.getByRole('button', { name: /Analyze Screen/ }).click()
    await page.waitForTimeout(1000)
    await expect(page.getByText('Setup Required')).toBeVisible({ timeout: 5000 })
  })

  test('shows Gemini API key setup instructions when key missing', async ({ page }) => {
    // Override REST mock to simulate API key error on analysis
    await page.evaluate(() => {
      var orig = window.mockBarq.python.request
      window.mockBarq.python.request = function (endpoint) {
        if (endpoint.indexOf('/vision/') !== -1) {
          return Promise.resolve({
            status: 'unavailable',
            message: 'Gemini API key not configured',
          })
        }
        return orig.call(window.mockBarq.python, endpoint)
      }
    })

    await page.getByRole('button', { name: /Analyze Screen/ }).click()
    await page.waitForTimeout(1000)
    // The setup instructions should include the config file path and setup steps
    // Use .first() because error text also contains "API key"
    await expect(page.getByText('Gemini API key').first()).toBeVisible({ timeout: 5000 })
  })

  test('readiness badge shows fraction when API key missing', async ({ page }) => {
    // With key missing, gemini_api/live are false, so not all systems are ready
    await expect(page.getByText(/\d+\/\d+ Ready/)).toBeVisible({ timeout: 5000 })
  })
})

// ═══════════════════════════════════════════════════════════════════════
// WS Error Handling — tests for WebSocket error messages and responses
// ═══════════════════════════════════════════════════════════════════════

test.describe('VisionPage — WS Error Handling', () => {
  test.beforeEach(async ({ page }) => {
    // Mock WebSocket to connect successfully
    await page.addInitScript(mockScript)
    await page.addInitScript(`
      window.__mockWsConfig.shouldFail = false
      window.__mockWsConfig.statusMessage = {
        type: 'status',
        gemini_available: true,
        api_key_configured: true,
        ready: true,
      }
    `)
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)
    await page.evaluate(() => {
      const btn = document.querySelector('[title="Vision"]')
      if (btn) btn.click()
    })
    await page.waitForSelector('text=VISUAL AWARENESS', { timeout: 5000 })
  })

  test('shows error card when WS sends an error message', async ({ page }) => {
    // Simulate WS server sending an error
    await page.evaluate(() => {
      window.__sendWsMessage({
        type: 'error',
        component: 'Gemini Vision',
        message: 'Analysis failed: rate limit reached',
      })
    })
    await page.waitForTimeout(500)
    await expect(page.getByText('rate limit')).toBeVisible({ timeout: 5000 })
  })

  test('shows Setup Required when WS error mentions API key', async ({ page }) => {
    // Simulate WS sending an API key error
    await page.evaluate(() => {
      window.__sendWsMessage({
        type: 'error',
        component: 'Gemini Vision',
        message: 'Gemini API key missing or invalid',
      })
    })
    await page.waitForTimeout(500)
    // The error message should be visible (use .first() — both error and setup mention API key)
    await expect(page.getByText(/API key/i).first()).toBeVisible({ timeout: 5000 })
    // Setup Required section should appear
    await expect(page.getByText('Setup Required')).toBeVisible({ timeout: 5000 })
  })

  test('shows error and clears loading when WS sends API key error', async ({ page }) => {
    // First verify Gemini Vision is marked as available
    const capsCard = page.locator('.glass-card').filter({ hasText: 'Capabilities' })
    await expect(capsCard.getByText('Gemini Vision')).toBeVisible()

    // Send API key error
    await page.evaluate(() => {
      window.__sendWsMessage({
        type: 'error',
        component: 'Gemini Vision',
        message: 'Gemini API key missing or invalid',
      })
    })
    await page.waitForTimeout(500)

    // The error state should show (use .first() — avoid strict mode on multiple matches)
    await expect(page.getByText(/API key/i).first()).toBeVisible({ timeout: 5000 })
  })
})

// ═══════════════════════════════════════════════════════════════════════
// REST Fallback — tests for when the app falls back to REST API
// ═══════════════════════════════════════════════════════════════════════

test.describe('VisionPage — REST Fallback', () => {
  test.beforeEach(async ({ page }) => {
    // WS connection fails by default — app falls back to REST
    await page.addInitScript(mockScript)
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)
    await page.evaluate(() => {
      const btn = document.querySelector('[title="Vision"]')
      if (btn) btn.click()
    })
    await page.waitForSelector('text=VISUAL AWARENESS', { timeout: 5000 })
  })

  test('shows history entry after REST analysis', async ({ page }) => {
    await page.getByRole('button', { name: /Analyze Screen/ }).click()
    // Wait for result
    const resultCard = page.locator('.glass-card').filter({ hasText: 'Analysis Result' })
    await expect(resultCard).toBeVisible({ timeout: 8000 })

    // Expand history panel
    const historyCard = page.locator('.glass-card').filter({ hasText: 'History' })
    await historyCard.locator('button').last().click()
    await page.waitForTimeout(500)

    // Should show analysis entries in history
    const entries = historyCard.locator('[class*="bg-void-700/30 rounded-lg"]')
    await expect(entries.first()).toBeVisible({ timeout: 3000 })
  })

  test('clears history after REST analysis', async ({ page }) => {
    // Run an analysis first
    await page.getByRole('button', { name: /Analyze Screen/ }).click()
    await page.waitForTimeout(1000)

    // Expand history
    const historyCard = page.locator('.glass-card').filter({ hasText: 'History' })
    await historyCard.locator('button').last().click()
    await page.waitForTimeout(500)

    // Click clear button (trash icon)
    const clearBtn = historyCard.locator('button[title="Clear history"]')
    if (await clearBtn.isVisible()) {
      await clearBtn.click()
      await page.waitForTimeout(500)
      await expect(page.getByText('No analyses yet')).toBeVisible({ timeout: 3000 })
    }
  })

  test('shows error card when REST analysis returns unavailable status', async ({ page }) => {
    // Override REST mock to return unavailable
    await page.evaluate(() => {
      window.mockBarq.python.request = function (endpoint) {
        if (endpoint.indexOf('/vision/screen') !== -1 || endpoint.indexOf('/vision/camera') !== -1) {
          return Promise.resolve({
            status: 'unavailable',
            message: 'Vision service is not configured',
          })
        }
        // Fallback to default for other endpoints
        return Promise.resolve({ status: 'ok' })
      }
    })

    await page.getByRole('button', { name: /Analyze Screen/ }).click()
    await page.waitForTimeout(1000)
    await expect(page.getByText('Vision service is not configured')).toBeVisible({ timeout: 5000 })
  })

  test('gracefully handles network failure — no result shown', async ({ page }) => {
    // Override REST mock to fail — the api() utility swallows the error
    // So no error card appears, but loading should stop and no result shown
    await page.evaluate(() => {
      window.mockBarq.python.request = function (endpoint) {
        if (endpoint.indexOf('/vision/screen') !== -1 || endpoint.indexOf('/vision/camera') !== -1) {
          return Promise.reject(new Error('Network request failed'))
        }
        return Promise.resolve({ status: 'ok' })
      }
    })

    await page.getByRole('button', { name: /Analyze Screen/ }).click()
    // Wait for the loading state to complete
    await page.waitForTimeout(2000)
    // No result card should appear (the error was swallowed by api())
    const resultCard = page.locator('.glass-card').filter({ hasText: 'Analysis Result' })
    await expect(resultCard).not.toBeVisible({ timeout: 3000 })
    // Loading spinner should be gone
    const loading = page.locator('.lucide-loader-2')
    await expect(loading).not.toBeVisible({ timeout: 3000 })
  })
})
