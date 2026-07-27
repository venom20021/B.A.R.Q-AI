"""Check the optimized resume content from the database."""
import sys
sys.path.insert(0, '.')
import asyncio
from database import jobs_dao

async def check():
    docs = await jobs_dao.get_active_documents(75)
    print(f"Documents found: {len(docs)}")
    for d in docs[:2]:
        content = d.get("content", "")
        print(f"\n--- Type: {d.get('document_type','?')} ({len(content)} chars) ---")
        print(content[:2500])

asyncio.run(check())
