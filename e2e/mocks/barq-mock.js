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

// ─── Voice / Chat Mock Responses ─────────────────────────────────────────

function handleVoiceChatText(opts) {
  // opts is either the raw data object or an IPC-style { method, body, headers } envelope
  var data = (opts && opts.body && typeof opts.body === 'string')
    ? JSON.parse(opts.body)
    : opts
  var message = ((data && data.message) || '').toLowerCase()

  // Agent task pattern: research X and do Y
  if (/research\s+.+(?:and|then)\s+.+/.test(message)) {
    return {
      text: 'I researched ' + message.replace(/^research\s+/i, '').replace(/\s+(?:and|then).+$/i, '') + ' and prepared a summary. Key findings include quantum superposition, entanglement, and quantum gate operations. The results have been saved to a file.',
      action: 'agent_task',
    }
  }

  // Agent task pattern: find X and do Y
  if (/find\s+.+(?:and|then)\s+.+/.test(message)) {
    return {
      text: 'I found the requested information and summarized the results. The findings have been compiled into a report.',
      action: 'agent_task',
    }
  }

  // Agent task pattern: plan a trip/vacation
  if (/plan\s+.+(?:trip|vacation|itinerary)/.test(message)) {
    return {
      text: 'I have planned your ' + (message.match(/(?:trip|vacation|itinerary)/) || ['trip'])[0] + '. Here is the itinerary with flight options, hotel recommendations, and daily activities.',
      action: 'agent_task',
    }
  }

  // Agent task pattern: analyze X and do Y
  if (/analyze\s+.+(?:and|then)\s+.+/.test(message)) {
    return {
      text: 'Analysis complete. I have reviewed the data and created a detailed report with key insights and recommendations.',
      action: 'agent_task',
    }
  }

  // Agent task pattern: compare X and do Y
  if (/compare\s+.+(?:and|then)\s+.+/.test(message)) {
    return {
      text: 'Comparison is complete. I evaluated the options and saved the results highlighting pros and cons of each.',
      action: 'agent_task',
    }
  }

  // Agent task pattern: create a report/summary/analysis
  if (/create\s+a\s+(?:report|summary|analysis)\s+of/.test(message)) {
    return {
      text: 'I have created a comprehensive summary based on the provided information. It covers all key points in a structured format.',
      action: 'agent_task',
    }
  }

  // Agent task pattern: could you research/find/analyze
  if (/could you (?:research|find|analyze|look up|investigate)/.test(message)) {
    return {
      text: 'Sure! I have researched that topic and gathered the latest information. Here is what I found including recent developments and key insights.',
      action: 'agent_task',
    }
  }

  // Agent task pattern: I need you to
  if (/i need you to/.test(message)) {
    return {
      text: 'On it! I have completed the task you requested. Everything is taken care of and results are ready for your review.',
      action: 'agent_task',
    }
  }

  // Generic agent task fallback (any multi-step pattern)
  if (/\b(?:and|then)\b/.test(message) && message.split(' ').length > 4) {
    return {
      text: 'I have processed your multi-step request and completed all the tasks. Let me know if you need anything else.',
      action: 'agent_task',
    }
  }

  // Default conversation response for other messages
  return {
    text: 'I received your message. How can I help you today?',
    action: 'conversation',
  }
}


function handleVoiceStatus() {
  return {
    is_listening: false,
    wake_word: 'computer',
    language: 'en',
    stt_model: 'whisper',
    tts_model: 'edge-tts',
    tts_backend: 'edge',
    tts_voice: 'en-US-JennyNeural',
    sensitivity: 'medium',
    last_confidence: 0.95,
    conversation_active: false,
    conversation_turns: 0,
    is_speaking: false,
    is_processing: false,
    hands_free_mode: false,
    wake_greeting_enabled: false,
    weather_city: 'London',
    stt_text: '',
    response_text: '',
    recent_commands: [],
  }
}


// ─── Brain API Mock Data ─────────────────────────────────────────────────

var MOCK_BRAINS_LIST = [
  {
    type: 'general',
    label: 'General Knowledge',
    description: 'General knowledge graph',
    color: '#818cf8',
    neon_glow: 'rgba(129,140,248,0.5)',
    icon: 'brain',
    nodes: 12,
    edges: 18,
  },
  {
    type: 'apple_notes',
    label: 'Apple Notes',
    description: 'Notes from Apple Notes',
    color: '#34d399',
    neon_glow: 'rgba(52,211,153,0.5)',
    icon: 'sticky-note',
    nodes: 8,
    edges: 10,
  },
  {
    type: 'google_docs',
    label: 'Google Docs',
    description: 'Documents from Google Docs',
    color: '#f472b6',
    neon_glow: 'rgba(244,114,182,0.5)',
    icon: 'file-text',
    nodes: 6,
    edges: 7,
  },
  {
    type: 'ai_chats',
    label: 'AI Chats',
    description: 'AI conversation history',
    color: '#c084fc',
    neon_glow: 'rgba(192,132,252,0.5)',
    icon: 'message-circle',
    nodes: 15,
    edges: 22,
  },
  {
    type: 'gemini_chats',
    label: 'Gemini Chats',
    description: 'Google Gemini conversation history',
    color: '#d946ef',
    neon_glow: 'rgba(217,70,239,0.5)',
    icon: 'sparkles',
    nodes: 10,
    edges: 14,
  },
]

var MOCK_BRAIN_GRAPHS = {
  general: {
    nodes: [
      { id: 'Quantum Computing' },
      { id: 'Machine Learning' },
      { id: 'Neural Networks' },
      { id: 'Python' },
      { id: 'Data Science' },
      { id: 'Algorithms' },
    ],
    links: [
      { source: 'Quantum Computing', target: 'Machine Learning', relation: 'related_to' },
      { source: 'Machine Learning', target: 'Neural Networks', relation: 'includes' },
      { source: 'Neural Networks', target: 'Python', relation: 'implemented_in' },
      { source: 'Data Science', target: 'Python', relation: 'uses' },
      { source: 'Data Science', target: 'Machine Learning', relation: 'depends_on' },
      { source: 'Algorithms', target: 'Data Science', relation: 'foundation_of' },
    ],
    _meta: {
      brain_type: 'general',
      label: 'General Knowledge',
      color: '#818cf8',
      neon_glow: 'rgba(129,140,248,0.5)',
      nodes: 6,
      edges: 6,
    },
  },
  apple_notes: {
    nodes: [
      { id: 'Meeting Notes' },
      { id: 'Project Alpha' },
      { id: 'Alice' },
      { id: 'Timeline Q1' },
    ],
    links: [
      { source: 'Meeting Notes', target: 'Project Alpha', relation: 'discusses' },
      { source: 'Alice', target: 'Project Alpha', relation: 'leads' },
      { source: 'Timeline Q1', target: 'Project Alpha', relation: 'deadline_for' },
    ],
    _meta: {
      brain_type: 'apple_notes',
      label: 'Apple Notes',
      color: '#34d399',
      neon_glow: 'rgba(52,211,153,0.5)',
      nodes: 4,
      edges: 3,
    },
  },
  google_docs: {
    nodes: [
      { id: 'Research Paper' },
      { id: 'Bibliography' },
      { id: 'Dr. Smith' },
    ],
    links: [
      { source: 'Research Paper', target: 'Bibliography', relation: 'cites' },
      { source: 'Dr. Smith', target: 'Research Paper', relation: 'authored' },
    ],
    _meta: {
      brain_type: 'google_docs',
      label: 'Google Docs',
      color: '#f472b6',
      neon_glow: 'rgba(244,114,182,0.5)',
      nodes: 3,
      edges: 2,
    },
  },
  ai_chats: {
    nodes: [
      { id: 'GPT-4' },
      { id: 'Prompt Engineering' },
      { id: 'Token Limits' },
      { id: 'Context Window' },
      { id: 'Temperature' },
    ],
    links: [
      { source: 'GPT-4', target: 'Prompt Engineering', relation: 'requires' },
      { source: 'GPT-4', target: 'Token Limits', relation: 'has' },
      { source: 'Context Window', target: 'Token Limits', relation: 'determines' },
      { source: 'Temperature', target: 'GPT-4', relation: 'parameter_of' },
    ],
    _meta: {
      brain_type: 'ai_chats',
      label: 'AI Chats',
      color: '#c084fc',
      neon_glow: 'rgba(192,132,252,0.5)',
      nodes: 5,
      edges: 4,
    },
  },
  gemini_chats: {
    nodes: [
      { id: 'Gemini 2.5 Flash' },
      { id: 'Multimodal' },
      { id: 'Real-time' },
      { id: 'Vision Analysis' },
      { id: 'Audio Understanding' },
    ],
    links: [
      { source: 'Gemini 2.5 Flash', target: 'Multimodal', relation: 'supports' },
      { source: 'Gemini 2.5 Flash', target: 'Real-time', relation: 'enables' },
      { source: 'Vision Analysis', target: 'Gemini 2.5 Flash', relation: 'uses' },
      { source: 'Audio Understanding', target: 'Gemini 2.5 Flash', relation: 'uses' },
    ],
    _meta: {
      brain_type: 'gemini_chats',
      label: 'Gemini Chats',
      color: '#d946ef',
      neon_glow: 'rgba(217,70,239,0.5)',
      nodes: 5,
      edges: 4,
    },
  },
}

var MOCK_TIMELINE_GENERAL = [
  {
    timestamp: '2026-07-17T10:00:00Z',
    brain_type: 'general',
    subject: 'Quantum Computing',
    relation: 'related_to',
    object_: 'Machine Learning',
    is_new_edge: true,
  },
  {
    timestamp: '2026-07-17T09:30:00Z',
    brain_type: 'general',
    subject: 'Python',
    relation: 'used_for',
    object_: 'Data Science',
    is_new_edge: false,
  },
  {
    timestamp: '2026-07-16T22:00:00Z',
    brain_type: 'general',
    subject: 'Algorithms',
    relation: 'foundation_of',
    object_: 'Data Science',
    is_new_edge: true,
  },
]

var MOCK_TIMELINE_ALL = [
  {
    timestamp: '2026-07-17T11:00:00Z',
    brain_type: 'ai_chats',
    subject: 'GPT-4',
    relation: 'requires',
    object_: 'Prompt Engineering',
    is_new_edge: true,
  },
  {
    timestamp: '2026-07-17T10:00:00Z',
    brain_type: 'general',
    subject: 'Quantum Computing',
    relation: 'related_to',
    object_: 'Machine Learning',
    is_new_edge: true,
  },
  {
    timestamp: '2026-07-17T09:30:00Z',
    brain_type: 'general',
    subject: 'Python',
    relation: 'used_for',
    object_: 'Data Science',
    is_new_edge: false,
  },
  {
    timestamp: '2026-07-16T22:00:00Z',
    brain_type: 'general',
    subject: 'Algorithms',
    relation: 'foundation_of',
    object_: 'Data Science',
    is_new_edge: true,
  },
  {
    timestamp: '2026-07-16T20:00:00Z',
    brain_type: 'apple_notes',
    subject: 'Meeting Notes',
    relation: 'discusses',
    object_: 'Project Alpha',
    is_new_edge: false,
  },
  {
    timestamp: '2026-07-16T18:00:00Z',
    brain_type: 'google_docs',
    subject: 'Research Paper',
    relation: 'cites',
    object_: 'Bibliography',
    is_new_edge: true,
  },
  {
    timestamp: '2026-07-16T17:00:00Z',
    brain_type: 'gemini_chats',
    subject: 'Gemini 2.5 Flash',
    relation: 'supports',
    object_: 'Multimodal',
    is_new_edge: true,
  },
  {
    timestamp: '2026-07-16T16:00:00Z',
    brain_type: 'gemini_chats',
    subject: 'Vision Analysis',
    relation: 'uses',
    object_: 'Gemini 2.5 Flash',
    is_new_edge: false,
  },
]

var MOCK_BRAIN_STATS = {
  brain_type: 'general',
  nodes: 12,
  edges: 18,
  density: 0.1364,
  connected_components: 1,
  top_entities: [
    { entity: 'Machine Learning', centrality: 0.85 },
    { entity: 'Data Science', centrality: 0.72 },
    { entity: 'Python', centrality: 0.68 },
  ],
}

function handleBrainRequest(endpoint) {
  // /api/brain/list
  if (endpoint === '/api/brain/list') {
    return Promise.resolve(MOCK_BRAINS_LIST)
  }

  // /api/brain/{type}/visualize
  var visualizeMatch = endpoint.match(/^\/api\/brain\/([\w-]+)\/visualize$/)
  if (visualizeMatch) {
    var brainType = visualizeMatch[1]
    var graph = MOCK_BRAIN_GRAPHS[brainType]
    if (graph) {
      return Promise.resolve(JSON.parse(JSON.stringify(graph)))
    }
    return Promise.resolve({ nodes: [], links: [], _meta: null })
  }

  // /api/brain/{type}/stats
  var statsMatch = endpoint.match(/^\/api\/brain\/([\w-]+)\/stats$/)
  if (statsMatch) {
    return Promise.resolve(JSON.parse(JSON.stringify(MOCK_BRAIN_STATS)))
  }

  // /api/brain/timeline?limit=100 (all brains)
  if (endpoint === '/api/brain/timeline?limit=100') {
    return Promise.resolve(JSON.parse(JSON.stringify(MOCK_TIMELINE_ALL)))
  }

  // /api/brain/{type}/timeline?limit=100
  var timelineMatch = endpoint.match(/^\/api\/brain\/([\w-]+)\/timeline\?limit=100$/)
  if (timelineMatch) {
    return Promise.resolve(JSON.parse(JSON.stringify(MOCK_TIMELINE_GENERAL)))
  }

  return null
}


// ─── WebSocket Mock (for vision page tests) ─────────────────────────────────
// By default, WebSocket connections fail (simulating no backend running).
// Tests can override via page.addInitScript() before navigation.

window.__mockWsConfig = {
  shouldFail: true,          // Default: connection fails (like no WS backend)
  connectDelay: 50,
  statusMessage: {
    type: 'status',
    gemini_available: true,
    api_key_configured: true,
    ready: true,
  },
}

var OrigWebSocket = window.WebSocket

function MockWebSocket(url) {
  this.url = url
  this.readyState = 0
  this.CONNECTING = 0
  this.OPEN = 1
  this.CLOSING = 2
  this.CLOSED = 3
  this.onopen = null
  this.onmessage = null
  this.onerror = null
  this.onclose = null

  var self = this
  var config = window.__mockWsConfig

  // Register as active mock for test interaction
  window.__mockWs = self

  setTimeout(function () {
    if (config.shouldFail) {
      // Simulate connection failure (trigger onerror + onclose)
      self.readyState = 3
      if (self.onerror) self.onerror(new Event('error'))
      if (self.onclose) self.onclose(new CloseEvent('close', { code: 1006 }))
      return
    }

    // Simulate successful connection
    self.readyState = 1
    if (self.onopen) self.onopen(new Event('open'))

    // Send status message
    if (self.onmessage && config.statusMessage) {
      self.onmessage({ data: JSON.stringify(config.statusMessage) })
    }
  }, config.connectDelay)

  this.send = function () {
    // Tests can override this by reassigning on a specific mock instance
  }

  this.close = function () {
    self.readyState = 3
    if (self.onclose) self.onclose(new CloseEvent('close', { code: 1000 }))
    window.__mockWs = null
  }
}

window.WebSocket = MockWebSocket
window.WebSocket.CONNECTING = 0
window.WebSocket.OPEN = 1
window.WebSocket.CLOSING = 2
window.WebSocket.CLOSED = 3

// Helper for tests to push a message to the active mock WebSocket
window.__sendWsMessage = function (msg) {
  var ws = window.__mockWs
  if (ws && ws.onmessage) {
    ws.onmessage({ data: JSON.stringify(msg) })
  }
}


window.mockBarq = {
  python: {
    request: function (endpoint, options) {
      // Voice chat endpoint — responds to natural language commands
      if (endpoint === '/voice/chat/text') {
        return Promise.resolve(handleVoiceChatText(options || {}))
      }

      // Voice status — used by ChatPage to show mic status
      if (endpoint === '/voice/status') {
        return Promise.resolve(handleVoiceStatus())
      }

      // Health check — used by App for connection polling
      if (endpoint === '/health') {
        return Promise.resolve({ status: 'ok' })
      }

      // Brain API endpoints
      var brainResult = handleBrainRequest(endpoint)
      if (brainResult) {
        return brainResult
      }

      // Vision endpoint mocks (existing)
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
  onNavigate: function () {},
  onQuickOverlay: function () {},
}

Object.defineProperty(window, 'barq', {
  value: window.mockBarq,
  writable: true,
  configurable: true,
})
