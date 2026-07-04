# ⚡ BARQ — Voice-Controlled Desktop Assistant

**BARQ** (Barq Automated Research & Query) is a cyberpunk-themed Electron desktop application with a Python sidecar that automates job search, social media content creation, voice control, and more. It features a live dashboard with animated canvas visualizations (Arc Reactor, Guardian Wolf), real-time system monitoring, weather data, and an AI chat interface.

<div align="center">
  <img src="https://img.shields.io/badge/Electron-32-blue?logo=electron" alt="Electron" />
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react" alt="React" />
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/TypeScript-5.5-3178C6?logo=typescript" alt="TypeScript" />
  <img src="https://img.shields.io/badge/Tailwind-3.4-06B6D4?logo=tailwindcss" alt="Tailwind CSS" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License" />
</div>

---

## ✨ Features

### 🎙️ Voice Control
- **Wake word detection** ("Hey BARQ") using Vosk
- **Speech-to-text** via OpenAI Whisper
- **Text-to-speech** via edge-tts
- Voice commands for navigation, job scanning, content creation, and more

### 💼 Job Search Automation
- Scans 35+ job boards (LinkedIn, Indeed, Glassdoor, etc.)
- AI evaluates and scores matches using LLM (Ollama/OpenAI)
- Auto-generates tailored resumes and cover letters
- Automated application pipeline with approval workflow

### 📱 Social Media Content Pipeline
- **Trend research** across YouTube, TikTok, Instagram, Twitter/X
- **Script generation** with AI (topic → structured script)
- **Video rendering** with automated assembly
- **Multi-platform posting** (YouTube, TikTok, Instagram, Twitter)
- Analytics dashboard for follower growth, engagement, and revenue

### 📊 Dashboard & Visualizations
- **Arc Reactor** — animated plasma ring visualization with floating energy motes
- **Guardian Wolf** — cybernetic wolf head with glowing seam lines and pulsing eyes
- **Live system monitoring** — CPU, memory, network, and subsystem status panels
- **Real-time weather** — live weather data from OpenWeatherMap
- **Live stats** — voice commands, jobs scanned, scripts generated, session uptime

### 🧠 AI Chat Interface
- Always-on voice/listening mode with audio waveform visualization
- Conversational AI assistant for system commands
- Quick overlay for instant command input (Ctrl+Shift+I)

### 🔧 Additional Tools
- **File manager** with code preview
- **Web browser** with Playwright automation
- **System monitor** with process management
- **Memory & knowledge base**
- **Document generation**
- **Desktop automation**
- **Spotify control**
- **Stock market tracker**
- **Image generation** (Pollinations.ai)
- **Maps & directions**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Electron Main Process                        │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  Window Mgr  │  │  IPC Handler  │  │   Python Bridge       │ │
│  └─────────────┘  └──────────────┘  │  (Sidecar Manager)     │ │
│                                      └───────────┬────────────┘ │
└──────────────────────────────────────────────────┼──────────────┘
                                                   │ HTTP (port 8956)
┌──────────────────────────────────────────────────┼──────────────┐
│              Python Sidecar (FastAPI)            │              │
│  ┌──────────┐ ┌──────┐ ┌──────┐ ┌─────────────┐ ▼              │
│  │   Voice  │ │ Jobs │ │Social│ │ Web & Media │                │
│  │  Routes  │ │Routes│ │Routes│ │   Routes    │                │
│  └────┬─────┘ └──┬───┘ └──┬───┘ └──────┬──────┘                │
│       │          │        │            │                       │
│  ┌────┴──────────┴────────┴────────────┴──────┐                │
│  │          Database (SQLite/PostgreSQL)        │               │
│  └──────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              Electron Renderer (React + Vite)                   │
│  ┌─────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────────┐ │
│  │ Sidebar  │ │Title Bar │ │ Dashboard  │ │  AI Chat Panel   │ │
│  └─────────┘ └──────────┘ │ (ArcReactor│ └──────────────────┘ │
│                           │  + Wolf +  │                       │
│  ┌──────────────────────┐ │ Monitors)  │                       │
│  │  Jobs, Analytics,    │ └────────────┘                       │
│  │  Content, Files, ... │                                      │
│  └──────────────────────┘                                      │
└─────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Desktop Shell** | Electron 32 |
| **Frontend** | React 18, TypeScript 5.5, Vite |
| **Styling** | Tailwind CSS 3.4, Framer Motion |
| **Visualizations** | HTML5 Canvas (custom), recharts |
| **Python Backend** | FastAPI 0.115, Uvicorn |
| **Database** | SQLite (asyncpg-style), async SQL |
| **Voice** | Vosk (wake word), Whisper (STT), edge-tts (TTS) |
| **Automation** | Playwright, yfinance, spotipy |

---

## 🚀 Getting Started

### Prerequisites

- **Node.js** >= 18
- **Python** >= 3.11
- **pnpm** (recommended) or npm

### Installation

```bash
# Clone the repository
git clone https://github.com/venom20021/B.A.R.Q-AI.git
cd B.A.R.Q-AI

# Install Node.js dependencies
npm install

# Install Python dependencies
cd python
pip install -r requirements.txt
cd ..

# Copy environment file and configure
cp .env.example .env
# Edit .env with your API keys (see Configuration section)
```

### Development

```bash
# Start the Electron app (Vite HMR + Python sidecar)
npm run dev

# Or start the Python backend separately
npm run dev:python
```

### Production Build

```bash
# Build the Electron app
npm run build

# Package for distribution
npm run package
```

### Testing & Linting

```bash
# TypeScript type checking
npm run typecheck

# Run tests
npm test

# Lint
npm run lint
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and configure the following:

### Required for Voice Control
| Variable | Description |
|----------|-------------|
| `OLLAMA_HOST` | Local LLM endpoint (default: `http://127.0.0.1:11434`) |
| `OLLAMA_MODEL` | LLM model (default: `llama3.1`) |

### Required for Job Search
| Variable | Description |
|----------|-------------|
| `LINKEDIN_EMAIL` | LinkedIn account email |
| `LINKEDIN_PASSWORD` | LinkedIn account password |
| `OPENAI_API_KEY` | OpenAI key (for resume/cover letter generation) |

### Required for Social Media
| Variable | Description |
|----------|-------------|
| `YOUTUBE_API_KEY` | YouTube Data API key |
| `TWITTER_API_KEY` | Twitter/X API key |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Graph API token |
| `TIKTOK_ACCESS_TOKEN` | TikTok API token |

### Required for Weather
| Variable | Description |
|----------|-------------|
| `OPENWEATHER_API_KEY` | OpenWeatherMap API key |

### Notifications
| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID |
| `SMTP_HOST` / `SMTP_PORT` | SMTP server config |
| `SMTP_USER` / `SMTP_PASS` | SMTP credentials |

---

## 🎮 Usage

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` | Reactor mode (default) |
| `2` | Split mode (Reactor + Wolf) |
| `3` | Wolf mode (fullscreen) |
| `Ctrl+Shift+I` | Quick overlay command input |

### Voice Commands

Say "Hey BARQ" (wake word), then:
- *"scan jobs"* — trigger job board scanning
- *"check trends"* — fetch trending topics
- *"dashboard"* / *"home"* — navigate to dashboard
- *"analytics"* / *"stats"* — view analytics
- *"weather in London"* — check weather
- *"open settings"* — go to settings
- *"stock AAPL"* — check stock prices

---

## 📁 Project Structure

```
B.A.R.Q/
├── src/
│   ├── main/               # Electron main process
│   │   ├── index.ts         # App entry, window creation
│   │   ├── python-bridge.ts # Python sidecar manager
│   │   └── ipc.ts           # IPC handler registrations
│   ├── preload/
│   │   └── index.ts         # Context bridge (safe API)
│   └── renderer/
│       └── src/
│           ├── App.tsx       # Root component with routing
│           ├── components/   # UI components
│           │   ├── ArcReactor.tsx     # Plasma ring visualization
│           │   ├── GuardianWolf.tsx   # Wolf head visualization
│           │   ├── ArcMonitorPanel.tsx # System monitor panels
│           │   ├── AiChatPanel.tsx    # AI chat interface
│           │   ├── Sidebar.tsx        # Navigation sidebar
│           │   ├── TitleBar.tsx       # Custom title bar
│           │   └── ...               # Other components
│           └── pages/        # Route pages
│               ├── DashboardPage.tsx  # Main dashboard
│               ├── AnalyticsPage.tsx  # Career & social analytics
│               ├── JobsPage.tsx       # Job search
│               ├── ContentPage.tsx    # Content studio
│               └── ...               # Other pages
├── python/                   # Python sidecar
│   ├── main.py               # FastAPI application
│   ├── config.py             # Configuration & settings
│   ├── database.py           # Database layer
│   ├── voice/                # Voice control routes
│   ├── jobs/                 # Job search routes
│   ├── social/               # Social media routes
│   ├── analytics/            # Analytics routes
│   ├── web_media/            # Web & media routes
│   ├── notifications/        # Notification routes
│   ├── documents/            # Document generation
│   ├── memory_knowledge/     # Memory & knowledge base
│   ├── system_control/       # System control
│   └── desktop_automation/   # Desktop automation
├── resources/                # Static resources
├── scripts/                  # Build & utility scripts
├── package.json              # Node dependencies
├── electron.vite.config.ts   # Vite configuration
├── tailwind.config.ts        # Tailwind configuration
└── vitest.config.mts         # Vitest configuration
```

---

## 🔌 API Overview

The Python sidecar runs on `http://127.0.0.1:8956` and provides:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `POST /voice/start` | Start wake word detection |
| `POST /voice/stop` | Stop wake word detection |
| `POST /voice/command` | Process a voice command |
| `GET /voice/status` | Voice system status |
| `POST /jobs/scan` | Trigger job board scan |
| `GET /jobs/matches` | Get evaluated job matches |
| `GET /jobs/status` | Job search status |
| `POST /social/generate-script` | Generate content script |
| `POST /social/render-video` | Render video from script |
| `POST /social/post` | Post to platforms |
| `GET /social/status` | Social module status |
| `GET /web/weather?city=` | Current weather |
| `GET /web/stocks/{ticker}` | Stock price data |
| `POST /web/browse` | Web browsing automation |
| `GET /analytics/career` | Career analytics |
| `GET /analytics/social` | Social analytics |

---

## 🧪 Testing

```bash
# Run all tests
npm test

# Run with watch mode
npm run test:watch

# TypeScript type checking
npm run typecheck
```

---

## 🛠️ Development

### Creating New Pages
1. Create a page component in `src/renderer/src/pages/`
2. Add it to the routing in `src/renderer/src/App.tsx`
3. Add a navigation item in `src/renderer/src/components/Sidebar.tsx`

### Adding Python API Endpoints
1. Create or edit a route file in `python/<module>/routes.py`
2. Register the router in `python/main.py`
3. Access from frontend via `window.barq.python.request('/your/endpoint')`

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
  Built with ⚡ by <a href="https://github.com/venom20021">venom20021</a>
</div>
