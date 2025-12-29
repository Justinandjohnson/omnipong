import asyncio
import argparse
import sys
from browser_manager import BrowserManager
from omnipong_scraper import OmniPongScraper

async def run_sync(scope):
    print(f"Starting Tournament Sync (Scope: {scope})")
    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    try:
        if not await manager.login_omnipong():
            print("Login failed")
            return

        activities_to_sync = []

        if scope in ['history', 'all']:
            hist = await scraper.scrape_my_tournament_history()
            activities_to_sync.extend(hist)
        
        if scope in ['regional', 'all']:
            reg = await scraper.scrape_regional_tournaments()
            activities_to_sync.extend(reg)
            
        if activities_to_sync:
            await scraper.bulk_sync_tournaments(activities_to_sync)
        else:
            print("No tournaments found to sync.")

    except Exception as e:
        print(f"Error during sync: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await manager.stop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", default="regional", help="Scope: history, regional, all")
    args = parser.parse_args()
    
    asyncio.run(run_sync(args.scope))
