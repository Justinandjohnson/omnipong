import asyncio
from browser_manager import BrowserManager
from omnipong_scraper import OmniPongScraper, init_db

async def main():
    print("Initializing Database...")
    await init_db()
    
    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    
    try:
        # 1. Login handled implicitly by browser manager/scraper methods
        
        # 2. Scrape Activities (Leagues & Tournaments)
        activities = []
        for type_id in [0, 1, 2]: # Tournaments, Leagues, Camps
            print(f"Scraping Type {type_id}...")
            data = await scraper.scrape_activities(type_id)
            if data:
                activities.extend(data)
                await scraper.save_activities(data)
        
        # 3. Deep Scrape (Events & Details)
        print("Starting Deep Event/Detail Scrape...")
        # We focus on capturing *events* for upcoming tournaments
        # Iterate activities from DB to be safe
        from models import Activity
        from omnipong_scraper import AsyncSessionLocal
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as session:
            stmt = select(Activity).where(Activity.activity_type == 'tournament') # Focus on tournaments for now
            result = await session.execute(stmt)
            tournaments = result.scalars().all()
            
            for t in tournaments:
                # Scrape Events (Signup info)
                print(f"Checking events for {t.title}...")
                events = await scraper.scrape_activity_events(t.source_id)
                if events:
                    await scraper.save_activities([{"source_id": t.source_id, "events": events}])
                
                # Scrape Details (Flyer/Rules) if missing
                if not t.raw_details:
                     details = await scraper.scrape_activity_details(t.source_id)
                     if details:
                         t.flyer_url = details.get("flyer_url")
                         t.raw_details = details.get("raw_details")
                         session.add(t)
            await session.commit()

        # Scrape Matches (This will implicitly require login if not already done)
        # The browser manager handles the session.
        print("Scraping Match History...")
        await scraper.scrape_my_matches()
        
        print("Autoscrape Complete!")
        
    except Exception as e:
        print(f"Autoscrape Failed: {e}")
    finally:
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(main())
