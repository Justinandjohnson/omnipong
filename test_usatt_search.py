import asyncio
import os
import sys
from browser_manager import BrowserManager

async def test_search():
    manager = BrowserManager()
    try:
        player = "Dawson, Jerry"
        print(f"Testing search for: {player}")
        result = await manager.search_usatt_player(player)
        print("Result:")
        print(result)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(test_search())
