"""
Gemini Live Connectivity Diagnostic.

Tests whether the Gemini Live audio WebSocket API is reachable
with the current API key and model name. Prints clear pass/fail
messages for each step.

Usage:
    python scripts/check_gemini_connect.py
"""
import asyncio
import os
import sys
sys.path.insert(0, '.')


async def diagnose():
    print("=" * 70)
    print("  Gemini Live Connectivity Diagnostic")
    print("=" * 70)

    # Step 1: Check API key
    try:
        from dotenv import load_dotenv
        load_dotenv('../.env')
    except Exception:
        pass

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("\n  [FAIL] GEMINI_API_KEY is NOT SET")
        print("  Add it to your .env file: GEMINI_API_KEY=your_key_here")
        return False
    print(f"\n  [OK] GEMINI_API_KEY is set ({api_key[:8]}...{api_key[-4:]})")

    # Step 2: Check google-genai package
    try:
        from google import genai
        from google.genai import types
        print("  [OK] google-genai package imported (v{})".format(
            getattr(genai, '__version__', 'unknown')
        ))
    except ImportError as e:
        print(f"  [FAIL] google-genai not installed: {e}")
        print("  Run: pip install google-genai")
        return False

    # Step 3: Create client
    try:
        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"},
        )
        print("  [OK] genai.Client created")
    except Exception as e:
        print(f"  [FAIL] genai.Client failed: {e}")
        return False

    # Step 4: List available models
    LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
    try:
        print(f"\n  Checking model: {LIVE_MODEL}")
        model_info = client.models.get(model=LIVE_MODEL)
        print(f"  [OK] Model found: {model_info.display_name or LIVE_MODEL}")
        print(f"  Description: {model_info.description[:120] if model_info.description else 'N/A'}")
    except Exception as e:
        print(f"  [WARN] Could not get model info: {e}")
        print("  The model might be a preview model that's been replaced.")
        print("  Trying to connect anyway...")

    # Step 5: Test WebSocket connection
    print("\n  Attempting Gemini Live WebSocket connection...")
    print("  (this takes 3-5 seconds)")
    try:
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon",
                    )
                )
            ),
        )
        cm = client.aio.live.connect(
            model=LIVE_MODEL,
            config=config,
        )
        session = await cm.__aenter__()

        # Wait for a welcome or setup message
        print("  [OK] WebSocket connected!")
        print(f"  Session type: {type(session).__name__}")
        print("  Session established successfully")

        # Close gracefully via context manager
        await cm.__aexit__(None, None, None)
        print("  [OK] Session closed cleanly")
        print("\n" + "=" * 70)
        print("  ✓ Gemini Live is fully operational!")
        print("=" * 70)
        return True

    except Exception as e:
        print(f"  [FAIL] WebSocket connection failed: {e}")
        print("\n  Possible causes:")
        print(f"    1. The model '{LIVE_MODEL}' may have expired or been renamed")
        print("    2. The API key may not have access to this model")
        print("    3. Network connectivity issue to Google's API")
        print("    4. Your Google Cloud project may need Gemini Live API enabled")
        return False


if __name__ == "__main__":
    success = asyncio.run(diagnose())
    sys.exit(0 if success else 1)
