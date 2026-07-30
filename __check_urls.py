"""Check how many jobs have missing URLs in the database."""
import asyncio
import sys
sys.path.insert(0, "python")

async def main():
    from database.connection import db_connection
    await db_connection.connect()

    # Check tables
    tables = await db_connection.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    table_names = [t["name"] for t in tables]
    print(f"Tables with 'job' in name: {[t for t in table_names if 'job' in t.lower()]}")

    if "job_listings" not in table_names:
        print("No job_listings table found!")
        await db_connection.close()
        return

    total = (await db_connection.fetch_one("SELECT COUNT(*) as c FROM job_listings"))["c"]
    no_url = (await db_connection.fetch_one(
        "SELECT COUNT(*) as c FROM job_listings WHERE source_url IS NULL OR source_url = ''"
    ))["c"]
    active_no = (await db_connection.fetch_one(
        "SELECT COUNT(*) as c FROM job_listings WHERE is_active = 1 AND (source_url IS NULL OR source_url = '')"
    ))["c"]

    print(f"\n{'='*60}")
    print("JOB URL AUDIT")
    print(f"{'='*60}")
    print(f"Total jobs:             {total}")
    print(f"No URL:                 {no_url} ({no_url*100//max(total,1)}%)")
    print(f"Active + No URL:        {active_no}")

    print(f"\nMissing URLs by board:")
    boards = await db_connection.fetch_all(
        "SELECT source_board, COUNT(*) as c FROM job_listings "
        "WHERE source_url IS NULL OR source_url = '' "
        "GROUP BY source_board ORDER BY c DESC"
    )
    for b in boards:
        print(f"  {b['source_board']:25s}: {b['c']}")

    print(f"\nSample missing:")
    samples = await db_connection.fetch_all(
        "SELECT title, company, source_board FROM job_listings "
        "WHERE source_url IS NULL OR source_url = '' "
        "ORDER BY scanned_at DESC LIMIT 8"
    )
    for s in samples:
        print(f"  {s['title'][:45]:45s} @ {s['company'][:25]:25s} [{s['source_board']}]")

    print(f"\nApplications:")
    apps = await db_connection.fetch_all(
        "SELECT status, COUNT(*) as c FROM applications GROUP BY status ORDER BY c DESC"
    )
    for a in apps:
        print(f"  {a['status']:25s}: {a['c']}")

    await db_connection.close()

asyncio.run(main())
