import asyncio
from browser_manager import BrowserManager

async def main():
    m = BrowserManager()
    try:
        if await m.login_stadium():
            await m.sync_user_rating()
    finally:
        await m.stop()

if __name__ == "__main__":
    asyncio.run(main())
