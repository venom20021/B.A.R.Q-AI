"""
BARQ Auto Applier -- Startup Test.

Verifies the pipeline instantiates and runs (even if it exits with no jobs found).
Run: python python/jobs/auto_applier/test_startup.py
"""

import asyncio
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from jobs.auto_applier.config import PROFILE, CONFIG
from jobs.auto_applier.pipeline.orchestrator import AutoApplyPipeline


async def main():
    sep = "=" * 50
    print(sep)
    print("BARQ Auto Applier -- Startup Test")
    print(sep)

    # 1. Config check
    print()
    print(f"[Config] Profile: {PROFILE.full_name}")
    print(f"  Education: {PROFILE.education}")
    print(f"  Skills: {len(PROFILE.skills)}")
    print(f"  Experiences: {len(PROFILE.experiences)}")
    print(f"  Ollama: {CONFIG.ollama_model}")
    print(f"  Browser headless: {CONFIG.headless}")
    print(f"  Telegram: {'OK' if CONFIG.telegram_bot_token else 'MISSING'} token")
    print(f"  LinkedIn: {'OK' if CONFIG.linkedin_email else 'MISSING'} credentials")

    # 2. Instantiate pipeline
    print()
    print("[Init] Initializing pipeline...")
    pipeline = AutoApplyPipeline()
    print("  [OK] Pipeline instantiated")

    # 3. Quick run (no browser)
    print()
    print("[Run] Running pipeline (discovery only)...")
    result = await pipeline.run(send_digest=False)

    print()
    print(f"[Result] Status: {result['status']}")
    print(f"  Jobs found: {result['jobs_found']}")
    print(f"  Jobs processed: {result['jobs_processed']}")
    print(f"  Errors: {len(result.get('errors', []))}")
    if result.get("elapsed_seconds"):
        print(f"  Elapsed: {result['elapsed_seconds']}s")

    print()
    print(sep)
    if result["status"] in ("complete", "idle"):
        print("[PASS] Pipeline startup test PASSED")
    else:
        print(f"[WARN] Pipeline returned: {result['status']}")
    print(sep)


if __name__ == "__main__":
    asyncio.run(main())
