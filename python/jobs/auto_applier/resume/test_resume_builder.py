"""
DynamicResumeBuilder — startup verification script.

Tests:
  1. Config path creation (staged_resumes/ exists)
  2. Static fallback base_resume.pdf exists
  3. DynamicResumeBuilder instantiation
  4. AIResumeBridge instantiation + server check
  5. Profile-to-schema conversion
  6. Minimal PDF generation (static fallback path)
  7. Full 3-tier build (should fall to static since no Ollama/gemini server)
"""

import asyncio
import sys
from pathlib import Path

# Add python/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))


async def main() -> None:
    sep = "=" * 50
    passed = 0
    failed = 0

    def check(name: str, ok: bool) -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name}")

    print(sep)
    print("DynamicResumeBuilder -- Startup Verification")
    print(sep)

    # 1. Config + paths
    print("\n-- Config & paths --")
    from jobs.auto_applier.config import CONFIG, PROFILE

    check("Profile loads", bool(PROFILE.full_name))
    check("Education set", bool(PROFILE.education))
    check("Skills > 0", len(PROFILE.skills) > 10)
    check("Experiences > 0", len(PROFILE.experiences) >= 2)

    staged_dir = Path(CONFIG.project_root) / "data" / "staged_resumes"
    base_path = Path(CONFIG.project_root) / "data" / "base_resume.pdf"

    check("Staged dir exists", staged_dir.exists())
    check("base_resume.pdf exists", base_path.exists() and base_path.stat().st_size > 100)

    # 2. DynamicResumeBuilder instantiation
    print("\n-- DynamicResumeBuilder --")
    from jobs.auto_applier.resume.dynamic_builder import DynamicResumeBuilder, build_tailored_resume

    builder = DynamicResumeBuilder()
    check("Builder instantiated", builder is not None)

    # 3. AIResumeBridge instantiation
    print("\n-- AIResumeBridge --")
    from jobs.auto_applier.resume.ai_resume_bridge import AIResumeBridge, _to_resume_data_schema

    bridge = AIResumeBridge()
    check("Bridge instantiated", bridge is not None)

    # 4. Schema conversion
    print("\n-- Schema conversion --")
    schema = _to_resume_data_schema(
        job_description="Software Engineer role at Google. Need experience with Python, distributed systems.",
        template="modern",
    )
    check("Schema has personalInfo", "personalInfo" in schema)
    check("Schema has fullName", schema["personalInfo"]["fullName"] == "Sai Prabhat")
    check("Schema has education", len(schema.get("education", [])) > 0)
    check("Schema has experience", len(schema.get("experience", [])) > 0)
    check("Schema has skills", len(schema.get("skills", [])) > 0)
    check("Schema has template", schema.get("template") == "modern")

    # 5. Server check (expected: not running on CI)
    print("\n-- AI_Resume_Generator server check --")
    server_up = await bridge.is_server_running()
    check("Server reachable check (may be false)", isinstance(server_up, bool))

    # 6. Static fallback (should succeed since base_resume.pdf exists)
    print("\n-- 3-Tier build (expected: static fallback) --")
    result = await builder.build(
        job_description="Python backend developer",
        job_title="Software Engineer",
        company="Test Company",
        timeout=30,
    )
    check("Result has pdf_path", bool(result.pdf_path))
    check("Result status is not error", result.status != "error")
    check("PDF file exists", result.pdf_path and Path(result.pdf_path).exists())
    check("PDF has content", result.file_size_bytes > 100)
    check("Source is set", bool(result.source))
    print(f"  Status: {result.status}")
    print(f"  Source: {result.source}")
    print(f"  Path: {result.pdf_path}")
    print(f"  Size: {result.file_size_bytes} bytes")
    print(f"  Template: {result.template_used}")

    # 7. Quick one-shot function
    print("\n-- One-shot convenience function --")
    quick_result = await build_tailored_resume(
        job_description="Fullstack developer with React and .NET",
        job_title="Fullstack Developer",
        company="Acme Corp",
    )
    check("Quick build succeeded", quick_result.status != "error")
    check("Quick build PDF exists", bool(quick_result.pdf_path))
    print(f"  Status: {quick_result.status}")
    print(f"  Source: {quick_result.source}")

    # Summary
    print(f"\n{sep}")
    print(f"Results: {passed} passed, {failed} failed")
    print(sep)
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
