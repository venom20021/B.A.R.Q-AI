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
