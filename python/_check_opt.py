"""Debug optimizer output from database."""
import sys
sys.path.insert(0, '.')
import asyncio
from database import db_connection

async def check():
    # Get the latest application doc (application_id=75)
    rows = await db_connection.fetch_all(
        "SELECT document_type, content, file_path FROM application_documents WHERE application_id = ? ORDER BY id DESC",
        (75,)
    )
    print(f"Docs found: {len(rows)}")
    for r in rows:
        content = r["content"] or ""
        print(f"\n=== Type: {r['document_type']} ({len(content)} chars) ===")
        print(content[:2000])

asyncio.run(check())
