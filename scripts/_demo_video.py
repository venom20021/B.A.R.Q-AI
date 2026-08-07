"""Phase 1b end-to-end demo: real stock footage + captions + voiceover render."""
import asyncio
import sys

sys.path.insert(0, "/home/ubuntu/barq/python")

from social.video import VideoAssembler  # noqa: E402


async def main():
    va = VideoAssembler()

    # 1) Prove the Pexels key works end-to-end
    clips = await va._fetch_stock_footage("coffee sunrise", count=2)
    print(f"STOCK-FOOTAGE: {len(clips)} clip(s) downloaded")
    for c in clips:
        print("  clip:", c)

    # 2) Full render with the real footage + auto voiceover
    script = {
        "topic": "morning productivity",
        "script": (
            "Hook: Mornings are a blank canvas.\n"
            "Content: A calm routine beats a crowded calendar. "
            "Start with the hardest task first and protect your focus "
            "before the world takes it.\n"
            "CTA: Follow for more productivity tips."
        ),
        "sections": ["Hook", "Content", "CTA"],
        "visual_cues": ["coffee", "sunrise", "desk"],
    }
    out = await va.render(
        script,
        "/home/ubuntu/barq/data/phase1_demo.mp4",
        stock_footage_paths=clips,
    )
    size = out.stat().st_size if out.exists() else -1
    print(f"RENDERED: {out} size={size} bytes")
    if size > 0:
        print("RENDER-OK")


asyncio.run(main())
