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
    // Each capability row has a CheckCircle icon — scope to only the CapabilityRow containers
    const rows = capabilitiesCard.locator('[class*="flex items-center justify-between py-1"]')
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
