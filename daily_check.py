import asyncio
import os
import sys
import json
from datetime import datetime, timedelta
from browser_manager import BrowserManager
from omnipong_scraper import OmniPongScraper, AsyncSessionLocal, init_db
from models import Activity, Notification
from sqlalchemy import select

# Add backend to path for tournament_intelligence
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "rubberr/backend")))
from tournament_intelligence import get_tournament_intelligence

async def daily_check():
    print("Starting daily tournament check...")
    await init_db() # Ensure tables (including Notification) exist
    
    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    
    try:
        # 1. Sync tournaments (Region 8/Texas)
        print("Syncing regional tournaments...")
        # Since we don't have a specific regional sync method that returns new ones,
        # we sync and then find those with 'last_scraped' within the last few minutes.
        # Or better: track seen source_ids.
        
        # For simplicity in this demo, let's just trigger the regional sync
        activities = await scraper.scrape_activities(0) # 0 = Tournaments
        if activities:
            # Filter for TX/Region 8
            tx_cities = ["plano", "austin", "houston", "san antonio", "dallas", "richardson", "irving", "katy", "allen", "colleyville", "round rock", "fort worth", "lubbock", "el paso", "arlington"]
            tx_activities = [a for a in activities if any(city in (a.get('city_state') or "").lower() for city in tx_cities)]
            
            async with AsyncSessionLocal() as session:
                for a in tx_activities:
                    print(f"Processing regional tournament: {a['title']}")
                    
                    # 1. Scrape full event details (Fees, Ratings) to ensure AI has data
                    print(f"Scraping events for {a['title']}...")
                    try:
                        events_data = await scraper.scrape_activity_events(a['source_id'])
                        a['events'] = events_data
                    except Exception as e:
                        print(f"Failed to scrape events for {a['title']}: {e}")
                        a['events'] = []

                    # 2. Save/Update Activity & Events in DB
                    await scraper.save_activities([a])
                    await session.commit()
                    
                    # 3. Generate Fresh AI Insights
                    # Note: get_tournament_intelligence now fetches user rating internally
                    intelligence = get_tournament_intelligence(a['title'])
                    
                    # 4. Upsert Notification
                    # Check if notification already exists for this tournament
                    # We look for a notification where content->>'title' matches
                    # SQLite JSON extraction syntax or just basic loop if simple
                    
                    # Simple approach: Check if we have a notification for this title today? 
                    # Or just check if one exists and update it.
                    # For this demo, let's just create a new one if it doesn't exist, or update the existing one.
                    
                    # We'll search for 'new_tournament' type and matching title in content
                    from models import Notification
                    stmt = select(Notification).where(Notification.type == 'new_tournament')
                    n_res = await session.execute(stmt)
                    existing_notifs = n_res.scalars().all()
                    
                    target_notif = None
                    for n in existing_notifs:
                        try:
                            c = json.loads(n.content) if isinstance(n.content, str) else n.content
                            if c.get('title') == a['title']:
                                target_notif = n
                                break
                        except:
                            continue
                    
                    new_content = json.dumps({
                        "title": a['title'],
                        "date": a['date_range'],
                        "location": a['city_state'],
                        "recommendation": intelligence.get('recommendations', [{}])[0] if intelligence.get('recommendations') else {}
                    })

                    if target_notif:
                        print(f"Updating existing notification for {a['title']}")
                        target_notif.content = new_content
                        # Mark as unread so user sees the update? Optional.
                        # target_notif.read = False 
                    else:
                        print(f"Creating new notification for {a['title']}")
                        notif = Notification(
                            type='new_tournament',
                            content=new_content
                        )
                        session.add(notif)
                    
                    await session.commit()

        print("Daily check complete.")
        
    except Exception as e:
        print(f"Daily check failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(daily_check())
