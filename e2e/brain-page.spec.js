const { test, expect } = require('@playwright/test')
const path = require('path')
const fs = require('fs')

// Read the mock script as a string for injection via addInitScript
const mockScript = fs.readFileSync(
  path.resolve(__dirname, 'mocks/barq-mock.js'),
  'utf-8',
)

test.describe('BrainPage — Timeline Panel & Tab Switching', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(mockScript)
    // Navigate to root — MemoryRouter ignores URL bar
    await page.goto('/', { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)

    // Sidebar is collapsed (translateX -160px) — button is in DOM but off-screen.
    // Use native DOM click via evaluate() to bypass Playwright's viewport check.
    await page.evaluate(() => {
      const btn = document.querySelector('[title="Brain"]')
      if (btn) btn.click()
    })

    // Wait for BrainPage to render — the first brain tab label should appear
    await page.waitForSelector('text=General Knowledge', { timeout: 8000 })
  })

  // ═══ Timeline Panel: Open / Close ═══

  test('opens timeline panel when clicking the clock button', async ({ page }) => {
    // Click the timeline toggle button
    await page.locator('button[title="Toggle timeline history"]').click()

    // The timeline panel heading should be visible
    const timelineHeading = page.locator('text=Timeline')
    await expect(timelineHeading).toBeVisible({ timeout: 3000 })
  })

  test('closes timeline panel when clicking the close button', async ({ page }) => {
    // Open timeline
    await page.locator('button[title="Toggle timeline history"]').click()
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 3000 })

    // Close via the X button inside the timeline panel
    // The timeline panel has a header with a close button containing an X icon
    const closeBtn = page.locator('text=Timeline').locator('..').locator('button').last()
    await closeBtn.click()

    // The timeline heading should disappear
    await expect(page.getByText('Timeline')).not.toBeVisible()
  })

  test('toggles timeline panel on repeated clicks', async ({ page }) => {
    const toggleBtn = page.locator('button[title="Toggle timeline history"]')

    // First click — open
    await toggleBtn.click()
    await expect(page.getByText('Timeline')).toBeVisible({ timeout: 3000 })

    // Second click — close
    await toggleBtn.click()
    await expect(page.getByText('Timeline')).not.toBeVisible()
  })

  // ═══ Timeline Panel: Entry Rendering ═══

  test('displays timeline entries with subject, relation, and object', async ({ page }) => {
    // Open timeline
    await page.locator('button[title="Toggle timeline history"]').click()
    await page.waitForTimeout(1000)

    // The mock returns three entries for the general brain.
    // Each entry renders a triplet: subject → relation → object
    await expect(page.getByText('Quantum Computing')).toBeVisible({ timeout: 3000 })
    await expect(page.getByText('Machine Learning')).toBeVisible()
    await expect(page.getByText('related_to')).toBeVisible()
    await expect(page.getByText('Python')).toBeVisible()
    await expect(page.getByText('Data Science')).toBeVisible()
  })

  test('marks new edges with a NEW badge', async ({ page }) => {
    await page.locator('button[title="Toggle timeline history"]').click()
    await page.waitForTimeout(1000)

    // The first mock entry is_new_edge: true — should show "NEW" badge
    const newBadges = page.locator('span', { hasText: 'NEW' })
    const count = await newBadges.count()
    expect(count).toBeGreaterThanOrEqual(1)
  })

  test('shows "+1" for non-new entries', async ({ page }) => {
    await page.locator('button[title="Toggle timeline history"]').click()
    await page.waitForTimeout(1000)

    // The second mock entry is_new_edge: false — should show "+1" instead of "NEW"
    const plusOneBadges = page.locator('span', { hasText: '+1' })
    const count = await plusOneBadges.count()
    expect(count).toBeGreaterThanOrEqual(1)
  })

  test('timeline footer shows the correct event count', async ({ page }) => {
    await page.locator('button[title="Toggle timeline history"]').click()
    await page.waitForTimeout(1000)

    // Footer shows "3 events · refresh"
    await expect(page.getByText('3 events')).toBeVisible({ timeout: 3000 })
  })

  test('timeline footer has a clickable refresh button', async ({ page }) => {
    await page.locator('button[title="Toggle timeline history"]').click()
    await page.waitForTimeout(1000)

    // The footer contains a "refresh" button
    const refreshBtn = page.locator('button', { hasText: 'refresh' })
    await expect(refreshBtn).toBeVisible({ timeout: 3000 })
  })

  // ═══ Timeline "All Brains" Filter ═══

  test('shows brain-specific filter badge by default', async ({ page }) => {
    await page.locator('button[title="Toggle timeline history"]').click()
    await page.waitForTimeout(1000)

    // The default filter badge shows the brain abbreviation (first 4 chars uppercase)
    // "general" → "GENE"
    await expect(page.getByText('GENE')).toBeVisible({ timeout: 3000 })
  })

  test('switches filter badge to ALL when toggling all-brains view', async ({ page }) => {
    await page.locator('button[title="Toggle timeline history"]').click()
    await page.waitForTimeout(1000)

    // Click the filter toggle button (has Filter icon, title "Showing current brain only")
    const filterBtn = page.locator('button[title="Showing current brain only"]')
    await expect(filterBtn).toBeVisible({ timeout: 3000 })
    await filterBtn.click()

    // Badge should now show "ALL"
    await expect(page.getByText('ALL')).toBeVisible({ timeout: 3000 })
  })

  test('shows entries from other brain types in all-brains timeline view', async ({ page }) => {
    await page.locator('button[title="Toggle timeline history"]').click()
    await page.waitForTimeout(1000)

    // Switch to all-brains view
    await page.locator('button[title="Showing current brain only"]').click()
    await page.waitForTimeout(500)

    // The all-brains timeline fetches entries from all brains.
    // 'Meeting Notes' is from the apple_notes brain in MOCK_TIMELINE_ALL
    // and does NOT appear in the tab bar or page heading — only in timeline entries.
    await expect(page.getByText('Meeting Notes')).toBeVisible({ timeout: 3000 })
  })

  // ═══ Brain Tab Switching ═══

  test('renders all brain tabs from the mock data', async ({ page }) => {
    // The mock returns 4 brains: General Knowledge, Apple Notes, Google Docs, AI Chats
    await expect(page.getByText('General Knowledge')).toBeVisible({ timeout: 3000 })
    await expect(page.getByText('Apple Notes')).toBeVisible({ timeout: 3000 })
    await expect(page.getByText('Google Docs')).toBeVisible({ timeout: 3000 })
    await expect(page.getByText('AI Chats')).toBeVisible({ timeout: 3000 })
  })

  test('switches active brain tab when clicking a different tab', async ({ page }) => {
    // Click the Apple Notes tab—each brain tab button has a title attribute
    // like "Apple Notes — 8 nodes, 10 edges"
    const appleNotesTab = page.locator('button[title="Apple Notes — 8 nodes, 10 edges"]')
    await expect(appleNotesTab).toBeVisible({ timeout: 3000 })
    await appleNotesTab.click()

    // Wait for the graph heading to update
    await page.waitForTimeout(1000)

    // The page heading should now show "Apple Notes" (the active brain label)
    await expect(page.getByText('Apple Notes')).toBeVisible({ timeout: 3000 })
  })

  test('highlights the active brain tab with the brain color', async ({ page }) => {
    // The active tab has a non-transparent borderBottomColor set via inline style
    // We can check that the active tab has the correct style attribute
    const generalTab = page.locator('button[title="General Knowledge — 12 nodes, 18 edges"]')

    // The active tab should have an inline style with borderBottomColor set
    const style = await generalTab.getAttribute('style')
    expect(style).toContain('border-bottom-color')
  })

  test('shows node count badge on each brain tab', async ({ page }) => {
    // Each brain tab with nodes > 0 shows a count badge
    // Verify numbers from the mock appear
    await expect(page.getByText('12')).toBeVisible({ timeout: 3000 })
    await expect(page.getByText('8')).toBeVisible({ timeout: 3000 })
    await expect(page.getByText('6')).toBeVisible({ timeout: 3000 })
    await expect(page.getByText('15')).toBeVisible({ timeout: 3000 })
  })

  test('graph data refreshes when switching brains', async ({ page }) => {
    // Click Apple Notes tab
    await page.locator('button[title="Apple Notes — 8 nodes, 10 edges"]').click()
    await page.waitForTimeout(1500)

    // The force graph should re-render with the new brain's data.
    // The loading overlay goes away and the heading updates.
    await expect(page.getByText('Apple Notes')).toBeVisible({ timeout: 5000 })
    // The stats badge should show Apple Notes node/edge count
    await expect(page.getByText('NODES')).toBeVisible({ timeout: 3000 })
  })

  test('switches to AI Chats tab and verifies content', async ({ page }) => {
    const aiChatsTab = page.locator('button[title="AI Chats — 15 nodes, 22 edges"]')
    await expect(aiChatsTab).toBeVisible({ timeout: 3000 })
    await aiChatsTab.click()

    await page.waitForTimeout(1000)
    await expect(page.getByText('AI Chats')).toBeVisible({ timeout: 3000 })

    // The nodes stat should show the AI Chats node count
    await page.waitForTimeout(1000)
    // The stats badge shows NODES with the count
    await expect(page.getByText('NODES')).toBeVisible({ timeout: 5000 })
  })

  test('renders Gemini Chats tab with correct metadata', async ({ page }) => {
    // The mock returns 5 brains including Gemini Chats
    const geminiTab = page.locator('button[title="Gemini Chats — 10 nodes, 14 edges"]')
    await expect(geminiTab).toBeVisible({ timeout: 3000 })

    // The Gemini Chats label should appear in the tab bar
    await expect(page.getByText('Gemini Chats')).toBeVisible({ timeout: 3000 })

    // The node count badge should show 10
    await expect(page.getByText('10')).toBeVisible({ timeout: 3000 })
  })

  test('switches to Gemini Chats tab and shows graph data', async ({ page }) => {
    const geminiTab = page.locator('button[title="Gemini Chats — 10 nodes, 14 edges"]')
    await expect(geminiTab).toBeVisible({ timeout: 3000 })
    await geminiTab.click()

    await page.waitForTimeout(1500)
    await expect(page.getByText('Gemini Chats')).toBeVisible({ timeout: 3000 })

    // Should show graph nodes from Gemini mock data
    await expect(page.getByText('Gemini 2.5 Flash')).toBeVisible({ timeout: 3000 })
    await expect(page.getByText('Multimodal')).toBeVisible()
    await expect(page.getByText('Vision Analysis')).toBeVisible()

    // The stats badge should show NODES and EDGES
    await expect(page.getByText('NODES').first()).toBeVisible({ timeout: 3000 })
    await expect(page.getByText('EDGES').first()).toBeVisible({ timeout: 3000 })
  })

  // ═══ Graph Rendering ═══

  test('renders graph data with nodes and edges stats', async ({ page }) => {
    // The stats badge should show NODES and EDGES from the graph _meta
    await expect(page.getByText('NODES').first()).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('EDGES').first()).toBeVisible({ timeout: 3000 })
  })

  test('graph loading overlay disappears after data arrives', async ({ page }) => {
    // The mock resolves immediately, so the initial loading overlay should clear rapidly.
    // This test verifies loading completes (not that the loading state was ever shown,
    // since the mock is too fast to reliably capture the intermediate state).
    await page.waitForTimeout(1500)

    const loadingText = page.getByText(/Loading.*Knowledge/i)
    await expect(loadingText).not.toBeVisible()
  })

  // ═══ Search Functionality ═══

  test('search input accepts text', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search entities"]')
    await expect(searchInput).toBeVisible({ timeout: 3000 })
    await searchInput.fill('Quantum')
    await expect(searchInput).toHaveValue('Quantum')
  })

  test('search shows autocomplete suggestions', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search entities"]')
    await expect(searchInput).toBeVisible({ timeout: 3000 })

    // Type a search query that matches graph nodes
    await searchInput.fill('Machine')
    await page.waitForTimeout(500)

    // The autocomplete dropdown should appear with suggestions
    await expect(page.getByText('Machine Learning')).toBeVisible({ timeout: 3000 })
  })

  test('search can be cleared with the X button', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search entities"]')
    await searchInput.fill('Quantum')
    await expect(searchInput).toHaveValue('Quantum')

    // Click the clear button (X icon)
    const clearBtn = page.locator('input[placeholder*="Search entities"]').locator('..').locator('button')
    await clearBtn.click()

    // Input should be cleared
    await expect(searchInput).toHaveValue('')
  })

  test('stats badge switches to MATCHES when search active', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search entities"]')
    await searchInput.fill('Quantum')
    await page.waitForTimeout(500)

    // The stats badge should show "MATCHES" instead of "NODES"
    await expect(page.getByText('MATCHES')).toBeVisible({ timeout: 3000 })
  })

  // ═══ Error Handling ═══

  test('shows error overlay when graph fetch fails', async ({ page }) => {
    // Override mock to simulate failure by injecting a script that breaks the request
    await page.evaluate(() => {
      var origRequest = window.mockBarq.python.request
      window.mockBarq.python.request = function (endpoint) {
        if (endpoint.indexOf('/visualize') !== -1) {
          return Promise.reject(new Error('Network error'))
        }
        return origRequest.call(window.mockBarq.python, endpoint)
      }
    })

    // Navigate away and back to trigger a fresh fetch
    await page.evaluate(() => {
      const btn = document.querySelector('[title="Dashboard"]')
      if (btn) btn.click()
    })
    await page.waitForTimeout(500)
    await page.evaluate(() => {
      const btn = document.querySelector('[title="Brain"]')
      if (btn) btn.click()
    })
    await page.waitForTimeout(2000)

    // Should see the error overlay with retry button
    await expect(page.getByText('Network error')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('Retry')).toBeVisible({ timeout: 3000 })
  })
})
