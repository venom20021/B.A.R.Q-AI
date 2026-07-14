const { test, expect } = require('@playwright/test')
const path = require('path')
const fs = require('fs')

// Read the mock script as a string for injection via addInitScript
const mockScript = fs.readFileSync(
  path.resolve(__dirname, 'mocks/barq-mock.js'),
  'utf-8',
)

test.describe('Agent Task via Voice Command — End-to-End Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(mockScript)
    // Navigate to root — MemoryRouter ignores URL bar
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)

    // Sidebar is collapsed (translateX -160px) — button is in DOM but off-screen.
    // Use native DOM click via evaluate() to bypass Playwright's viewport check.
    await page.evaluate(() => {
      const btn = document.querySelector('[title="Chat"]')
      if (btn) btn.click()
    })

    // Wait for ChatPage to render (confirm heading is visible)
    await page.waitForSelector('text=CHAT', { timeout: 5000 })
  })

  // ═══ Agent task: research and save ═══

  test('sends "research quantum computing and save to file" and shows agent task response', async ({ page }) => {
    const input = page.getByPlaceholder('Type a command or ask a question...')
    await expect(input).toBeVisible({ timeout: 5000 })

    await input.fill('research quantum computing and save to file')
    await input.press('Enter')

    // Wait for BARQ response
    const barqMessage = page.locator('.flex.justify-start .text-sm.font-exo')
    await expect(barqMessage.first()).toBeVisible({ timeout: 8000 })
    const renderedText = await barqMessage.first().textContent()
    expect(renderedText.length).toBeGreaterThan(20)

    // Should contain agent task-related keywords
    const hasTaskIndication =
      renderedText.toLowerCase().includes('research') ||
      renderedText.toLowerCase().includes('quantum') ||
      renderedText.toLowerCase().includes('summary') ||
      renderedText.toLowerCase().includes('processed') ||
      renderedText.toLowerCase().includes('prepared')
    expect(hasTaskIndication).toBeTruthy()
  })

  // ═══ Agent task: plan a trip ═══

  test('sends "plan a trip to Paris" and shows itinerary response', async ({ page }) => {
    const input = page.getByPlaceholder('Type a command or ask a question...')
    await expect(input).toBeVisible({ timeout: 5000 })

    await input.fill('plan a trip to Paris')
    await input.press('Enter')

    const barqMessage = page.locator('.flex.justify-start .text-sm.font-exo')
    await expect(barqMessage.first()).toBeVisible({ timeout: 8000 })

    const responseText = await barqMessage.first().textContent()
    expect(responseText.length).toBeGreaterThan(20)
    const hasTripIndication =
      responseText.toLowerCase().includes('trip') ||
      responseText.toLowerCase().includes('paris') ||
      responseText.toLowerCase().includes('itinerary') ||
      responseText.toLowerCase().includes('planned') ||
      responseText.toLowerCase().includes('hotel')
    expect(hasTripIndication).toBeTruthy()
  })

  // ═══ Agent task: analyze and report ═══

  test('sends "analyze this data and create a report" and shows analysis response', async ({ page }) => {
    const input = page.getByPlaceholder('Type a command or ask a question...')
    await expect(input).toBeVisible({ timeout: 5000 })

    await input.fill('analyze this data and create a report')
    await input.press('Enter')

    const barqMessage = page.locator('.flex.justify-start .text-sm.font-exo')
    await expect(barqMessage.first()).toBeVisible({ timeout: 8000 })

    const responseText = await barqMessage.first().textContent()
    expect(responseText.length).toBeGreaterThan(20)
    const hasAnalysisIndication =
      responseText.toLowerCase().includes('analyz') ||
      responseText.toLowerCase().includes('report') ||
      responseText.toLowerCase().includes('complete') ||
      responseText.toLowerCase().includes('insight')
    expect(hasAnalysisIndication).toBeTruthy()
  })

  // ═══ Agent task: could you research ═══

  test('sends "could you research the latest AI advancements" and shows research response', async ({ page }) => {
    const input = page.getByPlaceholder('Type a command or ask a question...')
    await expect(input).toBeVisible({ timeout: 5000 })

    await input.fill('could you research the latest AI advancements')
    await input.press('Enter')

    const barqMessage = page.locator('.flex.justify-start .text-sm.font-exo')
    await expect(barqMessage.first()).toBeVisible({ timeout: 8000 })

    const responseText = await barqMessage.first().textContent()
    expect(responseText.length).toBeGreaterThan(20)
    const hasResearchIndication =
      responseText.toLowerCase().includes('research') ||
      responseText.toLowerCase().includes('topic') ||
      responseText.toLowerCase().includes('information') ||
      responseText.toLowerCase().includes('latest') ||
      responseText.toLowerCase().includes('findings')
    expect(hasResearchIndication).toBeTruthy()
  })

  // ═══ Agent task: I need you to ═══

  test('sends "I need you to find the best restaurants near me" and shows task completion response', async ({ page }) => {
    const input = page.getByPlaceholder('Type a command or ask a question...')
    await expect(input).toBeVisible({ timeout: 5000 })

    await input.fill('I need you to find the best restaurants near me')
    await input.press('Enter')

    const barqMessage = page.locator('.flex.justify-start .text-sm.font-exo')
    await expect(barqMessage.first()).toBeVisible({ timeout: 8000 })

    const responseText = await barqMessage.first().textContent()
    expect(responseText.length).toBeGreaterThan(20)
    const hasTaskComplete =
      responseText.toLowerCase().includes('completed') ||
      responseText.toLowerCase().includes('done') ||
      responseText.toLowerCase().includes('taken care') ||
      responseText.toLowerCase().includes('ready') ||
      responseText.toLowerCase().includes('restaurant')
    expect(hasTaskComplete).toBeTruthy()
  })

  // ═══ Negative: simple command should NOT trigger agent task ═══

  test('sends "weather" and sees conversation response (not agent task)', async ({ page }) => {
    const input = page.getByPlaceholder('Type a command or ask a question...')
    await expect(input).toBeVisible({ timeout: 5000 })

    await input.fill('weather')
    await input.press('Enter')

    const barqMessage = page.locator('.flex.justify-start .text-sm.font-exo')
    await expect(barqMessage.first()).toBeVisible({ timeout: 8000 })

    const responseText = await barqMessage.first().textContent()
    // Should be a conversation response, not agent task specific
    expect(responseText.length).toBeGreaterThan(0)
    // The mock returns generic conversation for simple queries
    expect(responseText.toLowerCase()).toContain('received')
  })

  // ═══ Chat history preserves both user and BARQ messages ═══

  test('user message and BARQ response both appear in chat history', async ({ page }) => {
    const input = page.getByPlaceholder('Type a command or ask a question...')
    await expect(input).toBeVisible({ timeout: 5000 })

    await input.fill('compare these products and save results')
    await input.press('Enter')

    // Wait for user message to appear (justify-end)
    const userMessage = page.locator('.flex.justify-end .text-sm.font-exo')
    await expect(userMessage).toContainText('compare these products', { timeout: 8000 })

    // Wait for BARQ response (justify-start)
    const barqMessage = page.locator('.flex.justify-start .text-sm.font-exo')
    await expect(barqMessage.first()).toBeVisible({ timeout: 5000 })
    const barqText = await barqMessage.first().textContent()
    expect(barqText.length).toBeGreaterThan(20)
  })

  // ═══ Multiple turns preserves conversation context ═══

  test('supports multiple conversation turns', async ({ page }) => {
    const input = page.getByPlaceholder('Type a command or ask a question...')
    await expect(input).toBeVisible({ timeout: 5000 })

    // First turn — agent task
    await input.fill('research quantum computing and save to file')
    await input.press('Enter')

    // Wait for first response
    const barqMessages = page.locator('.flex.justify-start .text-sm.font-exo')
    await expect(barqMessages.first()).toBeVisible({ timeout: 8000 })

    // Second turn — follow-up conversation
    await input.fill('tell me more')
    await input.press('Enter')

    // Wait for second response — both BARQ messages should be visible
    const barqCount = await barqMessages.count()
    await expect(async () => {
      // Poll until we have 2 BARQ responses
      const count = await barqMessages.count()
      expect(count).toBe(2)
    }).toPass({ timeout: 5000 })

    // User messages should also be visible (2 user + 2 barq = 4 text elements)
    const allTextMessages = page.locator('.text-sm.font-exo')
    await expect(allTextMessages).toHaveCount(4, { timeout: 3000 })
  })
})
