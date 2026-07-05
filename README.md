# BARQ - Voice-Controlled AI Desktop Assistant

**BARQ** is a voice-first AI desktop assistant that combines wake word detection, natural language understanding, and automation into a single, cross-platform application. Think Alexa for your computer — control apps, search jobs, create content, and more, all by voice.

Built with **Python (FastAPI)** for the backend and **Electron + React** for the desktop UI, BARQ runs on **macOS** and **Windows**.

---

## Features

### 🎤 Voice Control
- **Wake word detection** — Always-listening (Vosk), hands-free wake word activation
- **Conversation mode** — Natural back-and-forth like Alexa/Gemini; no need to say the wake word for every turn
- **VAD endpointing** — Automatically detects when you stop speaking
- **Barge-in** — Interrupt BARQ mid-response by speaking over it
- **Multilingual** — English + Hindi wake word support
- **Configurable wake word** — Change it anytime via API

### 🧠 AI-Powered Conversation
- **Local LLM** — Runs on Ollama (llama3.1, llama3.2, phi4, or any model)
- **Conversation memory** — Maintains context across multi-turn conversations
- **Natural speech** — Edge TTS for high-quality text-to-speech

### 💼 Job Search Automation
- **Multi-board scanning** — Searches LinkedIn, Indeed, Glassdoor, Greenhouse, Lever, Ashby, Workday, and more
- **ATS-optimized matching** — AI evaluates and scores jobs against your resume
- **Auto-apply** — Playwright-based form filling for major ATS platforms
- **Resume parsing** — Extracts structured data from Markdown resumes
- **Cover letter & cold email generation** — AI-crafted, tailored to each job

### 📱 Social Media Pipeline
- **Trend research** — Discovers trending topics across platforms
- **Script generation** — AI writes content scripts for videos
- **Video rendering** — Automated short-form video creation
- **Cross-platform posting** — Schedule and publish to multiple platforms

### 🖥️ Desktop Automation
- **Screen OCR** — Capture and extract text from any screen region
- **Smart Drop Zones** — Auto-organize files with rule-based sorting
- **AI Wallpaper** — Generate or search for wallpapers by description
- **Workflow protocols** — Create and run custom automation workflows

### 🔧 Developer Tools
- **Git operations** — Full git integration via voice
- **Package manager** — npm, pip, brew commands by voice
- **Localhost tunneling** — Expose local ports via cloudflared
- **Terminal streaming** — Real-time command output via SSE

---

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| Ollama | Latest | [ollama.ai](https://ollama.ai) — for local LLM |
| ffmpeg | Latest | Required for audio playback ([download](https://ffmpeg.org/download.html)) |
| Vosk model | ~50 MB | Auto-detected from `models/vosk/` |

### 1. Clone & Install

**macOS / Linux:**
```bash
git clone https://github.com/venom20021/B.A.R.Q-AI.git
cd barq

# Install Python dependencies
pip install -r python/requirements.txt
pip install -r python/requirements-dev.txt

# Install Node.js dependencies
npm install

# Download Vosk model (English)
cd python/models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
mv vosk-model-small-en-us-0.15 vosk
cd ../..
```

**Windows:**
```batch
:: Run in Command Prompt or PowerShell
git clone https://github.com/venom20021/B.A.R.Q-AI.git
cd barq

:: Install Python dependencies
pip install -r python\requirements.txt
pip install -r python\requirements-dev.txt

:: Install Node.js dependencies
npm install

:: Download Vosk model using PowerShell
cd python\models
powershell -Command "Invoke-WebRequest -Uri https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -OutFile vosk-model-small-en-us-0.15.zip"
tar -xf vosk-model-small-en-us-0.15.zip
move vosk-model-small-en-us-0.15 vosk
cd ..\..
```

### 2. Pull an Ollama model

```bash
# Recommended for speed vs quality balance
ollama pull llama3.2:3b

# Or for higher quality (slower)
ollama pull llama3.1
```

### 3. Start the services

**macOS / Linux — using the dev script:**
```bash
python scripts/dev.py
```

Or manually in two terminals:
```bash
# Terminal 1: Start the FastAPI server
cd python
python3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8956

# Terminal 2: Start the desktop UI
# In the project root
npm run dev
```

**Windows — using the batch file:**
```batch
:: Double-click or run in Command Prompt
scripts\start.bat
```

Or manually in two Command Prompt windows:
```batch
:: Window 1: Start the FastAPI server
cd python
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8956

:: Window 2: Start the desktop UI
npm run dev
```

### 4. Test voice control

```bash
# Check server health
curl http://127.0.0.1:8956/health

# Start voice detection
curl -X POST http://127.0.0.1:8956/voice/start

# Test text chat
curl -X POST http://127.0.0.1:8956/voice/chat/text \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello! What can you do?"}'

# Test chat with TTS audio
curl -X POST http://127.0.0.1:8956/voice/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Tell me about yourself"}'

# Check voice status
curl http://127.0.0.1:8956/voice/status
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              Electron Desktop UI             │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
│  │  React   │ │  Tray    │ │ Wake Receiver │  │
│  │  (Vite)  │ │  Icon    │ │  (port 8112)  │  │
│  └────┬─────┘ └──────────┘ └──────┬───────┘  │
│       │ IPC                       │ HTTP      │
├───────┴───────────────────────────┴──────────┤
│          Python Sidecar (FastAPI)             │
│  ┌──────────┐ ┌────────┐ ┌───────────────┐   │
│  │  Voice   │ │  Jobs  │ │  Social Media │   │
│  │  Control │ │  Pipeline│ │  Pipeline    │   │
│  ├──────────┤ ├────────┤ ├───────────────┤   │
│  │  Desktop │ │  Web   │ │  Documents    │   │
│  │  Automation│ │  Media │ │  Generation   │   │
│  ├──────────┤ ├────────┤ ├───────────────┤   │
│  │  System  │ │ Memory │ │  Analytics    │   │
│  │  Control │ │ & Know.│ │               │   │
│  └──────────┘ └────────┘ └───────────────┘   │
│              │         │                     │
│         ┌────┘         └────┐                │
│     ┌───▼───┐          ┌───▼────┐           │
│     │ Ollama │          │ SQLite │           │
│     │ (LLM)  │          │  (DB)  │           │
│     └───────┘          └────────┘           │
└─────────────────────────────────────────────┘
```

### Key Components

| Component | Technology | Role |
|---|---|---|
| **Frontend** | Electron + React + Vite | Desktop UI, tray icon, wake receiver |
| **Backend** | Python FastAPI (uvicorn) | REST API, business logic, AI integration |
| **Voice** | Vosk (wake word) + Whisper (STT) + Edge TTS | Speech recognition & synthesis |
| **LLM** | Ollama (llama3.2:3b) | Natural language understanding & generation |
| **Database** | SQLite + aiosqlite | Persistent storage for jobs, settings, analytics |
| **Browser** | Playwright | ATS form filling, web scraping |
| **Desktop** | PyAutoGUI, MSS, PyTesseract | Screen OCR, keyboard/mouse automation |

---

## API Reference

The Python backend exposes a REST API on `http://127.0.0.1:8956`. Full OpenAPI docs at `/docs` when `BARQ_DEBUG=true`.

### Voice Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/voice/start` | Start wake word detection |
| POST | `/voice/stop` | Stop wake word detection |
| POST | `/voice/chat` | Send message, get text + audio response |
| POST | `/voice/chat/text` | Send message, get text-only response |
| POST | `/voice/command` | Process a voice command |
| POST | `/voice/transcribe` | Record + transcribe microphone input |
| POST | `/voice/wake-word` | Change the wake word dynamically |
| POST | `/voice/conversation-mode` | Enable/disable hands-free conversation mode |
| POST | `/voice/conversation/start` | Start a conversation session |
| POST | `/voice/conversation/end` | End conversation |
| GET | `/voice/status` | Get voice system status |
| GET | `/voice/mic-level` | Get current microphone level |
| POST | `/voice/sensitivity` | Set detection sensitivity (low/medium/high) |
| POST | `/voice/language` | Switch language (en/hi) |
| POST | `/voice/set-tts-voice` | Change TTS voice |

### System Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/system/launch-app` | Launch an application by name |
| POST | `/system/close-app` | Close an application |
| POST | `/system/terminal/run` | Execute a terminal command |
| POST | `/system/git` | Execute git operations |
| POST | `/system/package-manager` | npm/pip/brew commands |
| GET | `/system/monitors` | List connected monitors |
| POST | `/system/tunnel/expose` | Expose a local port |

### Job Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/jobs/scan` | Scan job boards for listings |
| GET | `/jobs/matches` | Get matched jobs |
| POST | `/jobs/{id}/optimize` | Optimize resume for a job |
| POST | `/jobs/{id}/cover-letter` | Generate cover letter |
| POST | `/jobs/{id}/cold-mail` | Generate cold email |

### Desktop Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/desktop/ocr/capture` | Capture screen region + OCR |
| POST | `/desktop/wallpaper/set` | Set wallpaper by description |
| POST | `/desktop/keyboard` | Inject keyboard input |
| POST | `/desktop/protocols/create` | Create an automation workflow |

---

## Configuration

Configuration is managed through environment variables or a `.env` file in the project root.

### Key Settings

| Variable | Default | Description |
|---|---|---|
| `SIDECAR_HOST` | `127.0.0.1` | Python backend host |
| `SIDECAR_PORT` | `8956` | Python backend port |
| `BARQ_DEBUG` | `false` | Enable debug mode + API docs |
| `VOSK_MODEL_PATH` | `models/vosk` | Path to Vosk English model |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Ollama model to use |
| `WHISPER_MODEL` | `base` | Whisper model size |
| `DATABASE_URL` | `sqlite+aiosqlite:///barq.db` | Database connection |
| `CAREER_OPS_PATH` | `~/career-ops` | Path for resume/job files |

### Model Selection

For best performance, use these Ollama models:

| Model | Size | Speed | Quality | Command |
|---|---|---|---|---|
| `tinyllama:1.1b` | 1.1B | ⚡ Very Fast | ⭐ Basic | `ollama pull tinyllama` |
| `llama3.2:3b` | 3B | 🚀 Fast | ⭐⭐ Good | `ollama pull llama3.2:3b` |
| `phi4:2.7b` | 2.7B | 🚀 Fast | ⭐⭐⭐ Better | `ollama pull phi` |
| `llama3.1` | 8B | 🐢 Slow | ⭐⭐⭐⭐ Best | `ollama pull llama3.1` |

---

## Cross-Platform Support

BARQ is designed to run on both **macOS** and **Windows**.

### macOS (Tested)
- Vosk wake word detection ✓
- Edge TTS audio playback ✓
- Ollama LLM ✓
- Desktop automation ✓
- System tray ✓

### Windows (Supported)
- Python path detection handled automatically
- Port freeing with `taskkill` built in
- Window management via `pygetwindow`
- Wallpaper setting via `ctypes`
- App launching via `os.startfile`

### CI/CD
GitHub Actions runs linting, type-checking, building, and Python tests on every push.

---

## Development

### Project Structure

```
barq/
├── src/                    # Electron + React frontend
│   ├── main/               # Electron main process
│   │   ├── index.ts        # App entry point, wake receiver
│   │   ├── ipc.ts          # IPC handlers
│   │   ├── python-bridge.ts # Python sidecar manager
│   │   └── tray.ts         # System tray
│   ├── preload/            # Electron preload scripts
│   └── renderer/           # React UI
│       └── src/
│           ├── components/ # UI components
│           ├── pages/      # Page views
│           ├── hooks/      # Custom React hooks
│           └── styles/     # CSS/Tailwind
├── python/                 # Python backend
│   ├── main.py             # FastAPI app entry
│   ├── config.py           # Settings management
│   ├── voice/              # Voice control module
│   ├── jobs/               # Job search pipeline
│   ├── social/             # Social media pipeline
│   ├── analytics/          # Analytics aggregation
│   ├── ai/                 # LLM conversation
│   ├── system_control/     # OS-level operations
│   ├── desktop_automation/ # Screen OCR, wallpaper
│   ├── web_media/          # Web browsing, media
│   ├── documents/          # PPT, Excel, PDF generation
│   ├── notifications/      # Multi-channel notifications
│   ├── memory_knowledge/   # Vector memory store
│   ├── database/           # SQLite DAOs
│   └── tests/              # Python test suite
├── scripts/                # Development scripts
├── .github/workflows/      # CI/CD pipeline
├── package.json            # Node dependencies
├── electron-builder.yml     # Electron packaging config
└── README.md               # This file
```

### Running Tests

```bash
# Python tests
cd python && pytest tests/ -v

# TypeScript type checks
npm run typecheck

# Frontend tests
npm run test

# Lint
npm run lint
```

---

## API Example: Full Voice Conversation

```bash
# 1. Start the voice system
curl -X POST http://127.0.0.1:8956/voice/start

# 2. Enable hands-free conversation mode
curl -X POST http://127.0.0.1:8956/voice/conversation-mode \
  -H 'Content-Type: application/json' \
  -d '{"enabled":true}'

# 3. Check system status
curl http://127.0.0.1:8956/voice/status

# 4. Change the wake word
curl -X POST http://127.0.0.1:8956/voice/wake-word \
  -H 'Content-Type: application/json' \
  -d '{"wake_word":"hey barq"}'

# 5. Chat with BARQ (text-only)
curl -X POST http://127.0.0.1:8956/voice/chat/text \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello! What can you help me with?"}'

# 6. Chat with BARQ (with TTS audio response)
curl -X POST http://127.0.0.1:8956/voice/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Tell me something interesting"}'
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [Vosk](https://alphacephei.com/vosk/) — Offline speech recognition
- [OpenAI Whisper](https://github.com/openai/whisper) — Speech-to-text
- [Edge TTS](https://github.com/rany2/edge-tts) — Text-to-speech
- [Ollama](https://ollama.ai) — Local LLM inference
- [FastAPI](https://fastapi.tiangolo.com) — Python web framework
- [Electron](https://www.electronjs.org) — Desktop app framework
