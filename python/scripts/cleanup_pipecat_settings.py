"""
Delete orphaned Pipecat settings from the database.
Run: python scripts/cleanup_pipecat_settings.py
"""
import asyncio
import sys
sys.path.insert(0, '.')


async def main():
    from database.connection import db_connection
    from database import settings_dao

    db = await db_connection.connect()

    # Find all Pipecat settings
    rows = await db.fetch_all(
        'SELECT key, value, category FROM user_settings WHERE key LIKE ?',
        ('pipecat_%',)
    )

    if not rows:
        print('No Pipecat settings found — already clean!')
        return

    print(f'Found {len(rows)} Pipecat settings:')
    for r in rows:
        val = str(r['value'])[:40]
        print(f'  {r["key"]} = {val}... (cat: {r["category"]})')

    # Delete them
    for r in rows:
        key = r['key']
        deleted = await settings_dao.delete_setting(key)
        print(f'  Deleted {key}: {deleted} row(s) affected')

    # Verify
    remaining = await db.fetch_all(
        'SELECT key FROM user_settings WHERE key LIKE ?',
        ('pipecat_%',)
    )
    if remaining:
        print(f'ERROR: {len(remaining)} Pipecat settings STILL remain!')
        for r in remaining:
            print(f'  {r["key"]}')
    else:
        print('All Pipecat settings deleted successfully!')

    await db_connection.close()


asyncio.run(main())
