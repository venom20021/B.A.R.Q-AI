// Mock BARQ API — injected into the page before app loads during e2e tests.
// The real window.barq is provided by Electron's preload script.
// This is plain JS so it can be passed to page.addInitScript() as a string.

const MOCK_VISION_RESPONSES = {
  '/vision/check': {
    capabilities: {
      screen_capture: true,
      webcam: true,
      gemini_api: true,
      gemini_live: true,
    },
    missing: [],
  },

  '/vision/screen': function (body) {
    var parsed = JSON.parse(body)
    return {
      status: 'success',
      text: 'This is a simulated screen analysis. You asked: "' + parsed.prompt + '". The screen shows a code editor with a dark theme.',
      source: 'screen',
      mime_type: 'image/jpeg',
      image_size_bytes: 24576,
      image_base64:
        'data:image/jpeg;base64,' +
        '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a' +
        'HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy' +
        'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL',
    }
  },
}

function defaultResponse(endpoint) {
  if (endpoint.indexOf('/vision/') !== -1) {
    return { status: 'success', text: 'Mock response for ' + endpoint }
  }
  return { status: 'ok' }
}

window.mockBarq = {
  python: {
    request: function (endpoint, options) {
      var mockFn = MOCK_VISION_RESPONSES[endpoint]
      if (mockFn) {
        if (typeof mockFn === 'function') {
          return Promise.resolve(mockFn((options && options.body) || '{}'))
        }
        return Promise.resolve(mockFn)
      }
      return Promise.resolve(defaultResponse(endpoint))
    },
  },
  voice: { start: function () {}, stop: function () {}, command: function () {} },
  system: { command: { clearApprovals: function () {} } },
  overlay: { show: function () {}, hide: function () {}, toggle: function () {} },
  jobs: { scan: function () {} },
  social: { trends: function () {} },
}

Object.defineProperty(window, 'barq', {
  value: window.mockBarq,
  writable: true,
  configurable: true,
})
