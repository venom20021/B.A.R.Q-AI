# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('D:\\Projects\\B.A.R.Q-AI\\scripts\\..\\python\\models\\vosk', 'models/vosk'), ('D:\\Projects\\B.A.R.Q-AI\\scripts\\..\\python\\models\\vosk\\README', 'models/vosk/')]
binaries = []
hiddenimports = ['agent.routes', 'agent.vision_routes', 'agent.agent_executor', 'agent.agent_planner', 'agent.error_handler', 'agent.skill_registry', 'agent.task_queue', 'ai.conversation', 'ai.responder', 'analytics.career', 'analytics.social', 'api.routes', 'database.analytics_dao', 'database.connection', 'database.jobs_dao', 'database.schema', 'database.settings_dao', 'database.social_dao', 'desktop_automation.routes', 'external_apis.clients', 'external_apis.routes', 'graph_brain', 'jobs.applier', 'jobs.cold_mail', 'jobs.cover_letter', 'jobs.evaluator', 'jobs.matcher', 'jobs.optimizer', 'jobs.pdf_generator', 'jobs.pipeline', 'jobs.response_tracker', 'jobs.resume_parser', 'jobs.scanner', 'memory_knowledge.routes', 'notifications.base', 'notifications.desktop', 'notifications.email_smtp', 'notifications.manager', 'notifications.telegram', 'social.calendar', 'social.poster', 'social.script', 'social.trends', 'social.video', 'system_control.command_whitelist', 'system_control.routes', 'utils.callback_guards', 'utils.ollama_client', 'voice.action_log', 'voice.audio_device', 'voice.conversation_listener', 'voice.interrupt_handler', 'voice.pipeline', 'voice.routes', 'voice.speech', 'voice.wake_word', 'web_media.routes']
tmp_ret = collect_all('fastapi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('uvicorn')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('httpx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('aiosqlite')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('vosk')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('sounddevice')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('edge_tts')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('faster_whisper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('yfinance')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('numpy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('psutil')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('av')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'pandas', 'tkinter', 'PyQt5', 'PySide2', 'PySide6', 'notebook', 'IPython', 'test', 'unittest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='barq-sidecar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='barq-sidecar',
)
