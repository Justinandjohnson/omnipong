import asyncio
from browser_manager import BrowserManager
from omnipong_scraper import OmniPongScraper
from models import Player
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

DATABASE_URL = "sqlite+aiosqlite:///./omnipong.db"

async def test_full_flow():
    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    try:
        await manager.login_omnipong()
        
        # 1. Find a valid tournament/league to scrape
        print("Finding a valid activity...")
        # e=1 is Leagues, usually has entries
        activities = await scraper.scrape_activities(1) 
        
        if activities:
            print(f"Sample Source ID: {activities[0]['source_id']}")


        target_id = None
        players = []
        
        # Try up to 10 activities
        for a in activities[:10]:
            if "t-tourney.asp?t=" in a['source_id'].lower():
                target_id = a['source_id']
                print(f"Trying target: {a['title']} ({target_id})")
                
                players = await scraper.scrape_tournament_entries(target_id)
                if players:
                    print(f"Success! Found {len(players)} players.")
                    break
                else:
                    print("No players found, trying next...")
        
        if not players:
            print("No valid tournament found in Leagues list. Trying Tournaments (e=0)...")
            activities = await scraper.scrape_activities(0)
            for a in activities[:5]:
                 if "t-tourney.asp?t=" in a['source_id'].lower():
                    target_id = a['source_id']
                    print(f"Trying target (Tournaments): {a['title']} ({target_id})")
                    players = await scraper.scrape_tournament_entries(target_id)
                    if players:
                        break
        
        if not players:
            print("Could not find any tournaments with extractable entries.")
            return

        print(f"Scraped {len(players)} players. First 3: {players[:3]}")

        # 3. Save to DB
        await scraper.save_tournament_players(players)
        
        # 4. Verify DB
        engine = create_async_engine(DATABASE_URL)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            stmt = select(Player).where(Player.rating_source == 'tournament_entry').limit(5)
            result = await session.execute(stmt)
            saved = result.scalars().all()
            print(f"Verified {len(saved)} players in DB with source 'tournament_entry':")
            for p in saved:
                print(f" - {p.name}: {p.rating} (State: {p.state})")

    except Exception as e:
        print(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(test_full_flow())
