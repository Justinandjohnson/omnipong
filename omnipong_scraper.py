import asyncio
from browser_manager import BrowserManager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import delete
from models import Activity, Base, Event, Match, Player
from datetime import datetime
import re

DATABASE_URL = "sqlite+aiosqlite:///./omnipong.db"
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database initialized.")

class OmniPongScraper:
    def __init__(self, browser_manager: BrowserManager):
        self.browser_manager = browser_manager

    async def scrape_activities(self, type_id: int):
        """
        type_id: 0 for Tournaments, 1 for Leagues, 2 for Camps/Classes
        """
        page = await self.browser_manager.get_page()
        
        # Relay console logs to terminal
        page.on("console", lambda msg: print(f"BROWSER DEBUG: {msg.text}"))

        url = f"https://www.omnipong.com/t-tourney.asp?e={type_id}"
        print(f"Scraping activities from {url}...")
        await page.goto(url)
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(3)

        # High-fidelity extraction
        activities_data = await page.evaluate("""
            () => {
                const results = [];
                const allTables = Array.from(document.querySelectorAll('table'));
                
                for (const table of allTables) {
                    const rows = Array.from(table.rows);
                    if (rows.length <= 1) continue;
                    
                    let headerIndex = -1;
                    let colMap = {};

                    // Look for a header row ANYWHERE in the first 5 rows
                    for (let i = 0; i < Math.min(rows.length, 5); i++) {
                        const text = rows[i].innerText.toLowerCase();
                        if (text.includes('action') && (text.includes('name') || text.includes('info'))) {
                            headerIndex = i;
                            const hCells = Array.from(rows[i].cells);
                            hCells.forEach((c, idx) => {
                                const t = c.innerText.toLowerCase();
                                if (t.includes('name')) colMap['name'] = idx;
                                if (t.includes('city')) colMap['location'] = idx;
                                if (t.includes('date')) colMap['date'] = idx;
                                if (t.includes('contact')) colMap['contact'] = idx;
                            });
                            break;
                        }
                    }
                    
                    if (headerIndex === -1) continue;
                    
                    console.log('--- FOUND DATA TABLE ---');

                    // Find region header above this table
                    let region = "Unknown Region";
                    let current = table;
                    while (current && current !== document.body) {
                        let prev = current.previousElementSibling;
                        while (prev) {
                            const pText = prev.innerText.trim();
                            if (pText && pText.length > 2 && pText.length < 100 && (prev.tagName === 'H3' || prev.tagName === 'B' || prev.tagName === 'FONT' || prev.tagName === 'P')) {
                                region = pText;
                                break;
                            }
                            prev = prev.previousElementSibling;
                        }
                        if (region !== "Unknown Region") break;
                        current = current.parentElement;
                    }

                    for (let i = headerIndex + 1; i < rows.length; i++) {
                        const row = rows[i];
                        const cells = Array.from(row.cells);
                        if (cells.length < 4) continue;
                        
                        let source_id = null;
                        let title = cells[colMap['name'] || 2]?.innerText.trim();
                        let location_cell = cells[colMap['location'] || 3]?.innerText.trim() || region;
                        let date_str = cells[colMap['date'] || 4]?.innerText.trim();
                        let contact_html = cells[colMap['contact'] || 5]?.innerHTML || "";

                        // Extract ID
                        const elements = Array.from(row.querySelectorAll('a, input, button'));
                        for (const el of elements) {
                            const href = el.getAttribute('href') || "";
                            const onclick = el.getAttribute('onclick') || "";
                            const nameAttr = el.getAttribute('name') || "";
                            const val = el.getAttribute('value') || "";
                            const combined = href + " " + onclick;
                            
                            const idMatch = combined.match(/[Tt]-tourney\\.asp\\?[^'"]+/i);
                            if (idMatch) {
                                source_id = idMatch[0].replace(/&amp;/g, '&');
                            } else if (nameAttr === 'id' && val) {
                                source_id = `T-tourney.asp?id=${val}`;
                            }
                        }

                        if (source_id && title) {
                            results.push({
                                "source_id": source_id,
                                "title": title,
                                "location": location_cell,
                                "date": date_str,
                                "contact_html": contact_html
                            });
                        }
                    }
                }
                return results;
            }
        """)

        activities = []
        for data in activities_data:
            # Basic parsing of contact_html for name/email/phone
            import re
            email_match = re.search(r'mailto:([\w\.-]+@[\w\.-]+)', data["contact_html"])
            email = email_match.group(1) if email_match else None
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(data["contact_html"], 'html.parser')
            contact_text = soup.get_text(separator='\n').strip().split('\n')
            contact_name = contact_text[0] if contact_text else None
            contact_phone = contact_text[1] if len(contact_text) > 1 else None

            activities.append({
                "source": "omnipong",
                "source_id": data["source_id"],
                "title": data["title"],
                "location": data["location"],
                "city_state": data["location"],
                "date_range": data["date"],
                "activity_type": "tournament" if type_id == 0 else ("league" if type_id == 1 else "camp"),
                "status": "upcoming",
                "url": url,
                "contact_name": contact_name,
                "contact_email": email,
                "contact_phone": contact_phone
            })
        
        print(f"Extracted {len(activities)} valid activities")    
        return activities

    async def scrape_activity_details(self, source_id: str):
        """
        Navigate to the info page for a specific activity to get more details.
        """
        page = await self.browser_manager.get_page()
        # Ensure source_id is a full path or relative
        path = source_id if source_id.startswith('/') else f"/{source_id}"
        url = f"https://www.omnipong.com{path}"
        print(f"Scraping details from {url}...")
        try:
            await page.goto(url)
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(1)
            
            details = await page.evaluate("""
                () => {
                    const bodyText = document.body.innerText;
                    const links = Array.from(document.querySelectorAll('a'));
                    const flyerLink = links.find(l => l.href.toLowerCase().includes('.pdf'))?.href || null;
                    
                    return {
                        "flyer_url": flyerLink,
                        "raw_details": bodyText.substring(0, 2000) 
                    };
                }
            """)
            return details
        except Exception as e:
            print(f"Error scraping details for {source_id}: {e}")
            return None

    async def scrape_contacts(self):
        """
        Extract contacts from the activities (type_id 2)
        """
        activities = await self.scrape_activities(2)
        contacts = []
        for a in activities:
            if a["contact_name"] or a["contact_email"]:
                contacts.append({
                    "name": a["contact_name"],
                    "email": a["contact_email"],
                    "phone": a["contact_phone"],
                    "role": "Coach",
                    "club_affiliation": a["location"],
                    "source_url": a["url"]
                })
        return contacts, activities

    async def save_activities(self, activities_data):
        print(f"Preparing to sync {len(activities_data)} activities...")
        async with AsyncSessionLocal() as session:
            for i, data in enumerate(activities_data):
                from sqlalchemy import select
                stmt = select(Activity).where(Activity.source_id == data["source_id"])
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    for key, value in data.items():
                        if hasattr(existing, key) and key != 'events':
                            setattr(existing, key, value)
                    existing.last_scraped = datetime.utcnow()
                    
                    # Update Events if provided
                    if "events" in data and data["events"]:
                        # Clear old events to avoid duplicates (simple sync)
                        from models import Event
                        await session.execute(delete(Event).where(Event.activity_id == existing.id))
                        for evt_data in data["events"]:
                            evt = Event(**evt_data)
                            evt.activity_id = existing.id
                            session.add(evt)
                            
                else:
                    activity = Activity(**data)
                    session.add(activity)
                    await session.flush() # Get ID
                    
                    if "events" in data and data["events"]:
                        from models import Event
                        for evt_data in data["events"]:
                            evt = Event(**evt_data)
                            evt.activity_id = activity.id
                            session.add(evt)
            
            await session.commit()
            print(f"Successfully synced {len(activities_data)} activities")

    async def deep_scrape_all(self, limit=None):
        """
        Iterate through all activities and fetch deep details if missing.
        """
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            stmt = select(Activity).where(Activity.raw_details == None)
            if limit:
                stmt = stmt.limit(limit)
            
            result = await session.execute(stmt)
            activities = result.scalars().all()
            
            print(f"Found {len(activities)} activities needing details...")
            
            for i, activity in enumerate(activities):
                print(f"[{i+1}/{len(activities)}] Scraping details for: {activity.title}")
                details = await self.scrape_activity_details(activity.source_id)
                if details:
                    activity.flyer_url = details["flyer_url"]
                    activity.raw_details = details["raw_details"]
                    activity.last_scraped = datetime.utcnow()
                    
                    if i % 10 == 0:
                        await session.commit()
                        print(f"Saved {i+1} details...")
            
            await session.commit()
            print("Deep scrape complete.")

    async def scrape_activity_events(self, source_id: str):
        """
        Navigates to the entry page for an activity and scrapes the available events.
        """
    async def scrape_activity_events(self, source_id: str):
        """
        Navigates to the entry page by finding the 'Enter' button on the list page.
        """
        page = await self.browser_manager.get_page()
        
        # Determine list URL based on source_id or lookup
        # Simple heuristic: T-tourney.asp usually implies e=0 (Tournament) or e=1 (League)
        # We can try e=0 first, then e=1 if not found.
        
        # Optimization: We should pass the type or guess it. 
        # For this implementation, we will search both e=0 and e=1 if needed.
        
        # Search all types: 0 (Tourney), 1 (League), 2 (Camp) + Regional
        list_urls = [
            "https://www.omnipong.com/t-tourney.asp?e=0", 
            "https://www.omnipong.com/t-tourney.asp?e=1",
            "https://www.omnipong.com/t-tourney.asp?e=2",
            "https://www.omnipong.com/T-tourney.asp?t=8&Region=8&y=&k=&e=0"
        ]
        entry_url = None
        
        print(f"Searching for 'Enter' button for {source_id}...")
        
        for list_url in list_urls:
            await page.goto(list_url)
            await page.wait_for_load_state("domcontentloaded")
            
            # Find the row that contains a link to source_id AND has an 'Enter' button/link
            found_url = await page.evaluate(f"""
                () => {{
                    const targetId = "{source_id}";
                    const rMatch = targetId.match(/[?&]r=(\\d+)/);
                    const rId = rMatch ? rMatch[1] : null;
                    
                    const rows = Array.from(document.querySelectorAll('tr'));
                    
                    for (const row of rows) {{
                        const links = Array.from(row.querySelectorAll('a'));
                        const hasTarget = (() => {{
                            const combinedText = row.innerHTML + " " + row.innerText;
                            if (rId && combinedText.includes("r=" + rId)) return true;
                            if (rId && combinedText.includes("h=" + rId)) return true;
                            if (targetId && combinedText.includes(targetId)) return true;
                            return false;
                        }})();
                        
                        if (hasTarget) {{
                            const enterLink = links.find(l => l.innerText.toLowerCase().includes('enter') && !l.innerText.toLowerCase().includes('info'));
                            if (enterLink) return enterLink.href;
                            
                            const inputs = Array.from(row.querySelectorAll('input, button'));
                            const enterBtn = inputs.find(b => (b.value || b.innerText || "").toLowerCase().includes('enter'));
                            if (enterBtn) {{
                                const onclick = enterBtn.getAttribute('onclick');
                                if (onclick) {{
                                    const match = onclick.match(/open_window\\('([^']+)'/);
                                    const path = match ? match[1].split("',")[0] : null;
                                    return path ? (path.startsWith('http') ? path : "https://www.omnipong.com/" + path.replace(/&amp;/g, '&')) : null;
                                }}
                            }}
                        }}
                    }}
                    return null;
                }}
            """)
            
            if found_url:
                entry_url = found_url
                break
        
        if not entry_url:
            print(f"Could not find 'Enter' button for {source_id} on list pages.")
            return []

        print(f"Found entry URL: {entry_url}. Navigating...")
        await page.goto(entry_url)
        await page.wait_for_load_state("domcontentloaded")
        
        # 1. Look for 'Events' button to show the list
        has_events_btn = await page.evaluate("""
            () => {
                const btns = Array.from(document.querySelectorAll('input, button'));
                const eBtn = btns.find(b => (b.value || b.innerText || "").toLowerCase() === 'events');
                if (eBtn) {
                    eBtn.click();
                    return true;
                }
                return false;
            }
        """)
        
        if has_events_btn:
            print("Clicked 'Events' button... waiting for table.")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)

        # 2. Extract Events
        events_data = await page.evaluate("""
            () => {
                const results = [];
                const tables = Array.from(document.querySelectorAll('table.omnipong'));
                // Target table that contains 'eligible' or headers like Action, Event Name, Fee
                const table = tables.find(t => t.innerText.toLowerCase().includes('event name') || t.innerText.toLowerCase().includes('eligible'));
                
                if (!table) return [];
                
                const rows = Array.from(table.rows);
                let colMap = {};
                
                for (let row of rows) {
                    const cells = Array.from(row.cells);
                    const text = row.innerText.toLowerCase();
                    
                    // Detect header row
                    if (text.includes('event name') || text.includes('eligible')) {
                        cells.forEach((c, idx) => {
                            const t = c.innerText.toLowerCase();
                            if (t.includes('event name') || t.includes('eligible')) colMap['name'] = idx;
                            else if (t.includes('fee')) colMap['fee'] = idx;
                            else if (t.includes('rating') && !t.includes('limit')) colMap['rating'] = idx; // Some show your rating?
                            else if (t.includes('limit')) colMap['rating_limit'] = idx;
                            else if (t.includes('time')) colMap['time'] = idx;
                        });
                        continue;
                    }
                    
                    // Skip section separators or rows without enough cells
                    if (cells.length < 3) continue;
                    if (text.includes('reason')) continue; // Skip "Events you are not eligible to play" header row
                    
                    let name = colMap['name'] !== undefined ? cells[colMap['name']].innerText.trim() : "";
                    // Clean name (e.g. "ABCD Singles : 41 slots left" -> "ABCD Singles")
                    name = name.split(':')[0].trim();
                    
                    let feeStr = colMap['fee'] !== undefined ? cells[colMap['fee']].innerText.trim() : "0";
                    let fee = parseFloat(feeStr.replace(/[^0-9.]/g, '')) || 0;
                    
                    let ratingStr = colMap['rating_limit'] !== undefined ? cells[colMap['rating_limit']].innerText.trim() : "0";
                    let rating = parseInt(ratingStr.replace(/[^0-9]/g, '')) || 0;
                    
                    // Fallback: Extract from name if not in explicit column
                    if (rating === 0) {
                        // Try multiple common patterns for rating limits
                        const patterns = [
                            /Under\s*(\d+)/i,           // "Under 1400", "Under1400"
                            /Below\s*(\d+)/i,           // "Below 1400"
                            /U\s*(\d+)/i,               // "U1400", "U 1400"
                            /(\d+)\s*(?:and\s*)?Under/i // "1400 Under", "1400 and Under"
                        ];
                        
                        for (const pattern of patterns) {
                            const match = name.match(pattern);
                            if (match) {
                                rating = parseInt(match[1]);
                                break;
                            }
                        }
                    }
                    
                    let time = colMap['time'] !== undefined ? cells[colMap['time']].innerText.trim() : "";

                    if (name && name.length > 2 && !name.toLowerCase().includes('eligible')) {
                        results.push({
                            "name": name,
                            "fee": fee,
                            "rating_limit": rating,
                            "start_time": time,
                            "status": "Open"
                        });
                    }
                }
                return results;
            }
        """)
        print(f"Scraped {len(events_data)} events.")
        return events_data

    async def scrape_my_matches(self):
        """
        Navigates to the user's match history (Ratings page) and scrapes results.
        """
        page = await self.browser_manager.get_page()
        print("Scraping Match History from Ratings page...")
        # Common URL for detailed history/rating change
        await page.goto("https://www.omnipong.com/Members.asp?s=4")
        await page.wait_for_load_state("domcontentloaded")

        matches = await page.evaluate("""
            () => {
                const results = [];
                const tables = Array.from(document.querySelectorAll('table'));
                // Look for table with Date, Event, Opponent, Rating, Result
                for (const table of tables) {
                    const rows = Array.from(table.rows);
                    if (rows.length < 2) continue;
                    
                    let headerIndex = -1;
                    let colMap = {};
                    
                    for (let i = 0; i < Math.min(rows.length, 5); i++) {
                        const text = rows[i].innerText.toLowerCase();
                        if (text.includes('opponent') && text.includes('score')) {
                            headerIndex = i;
                            const cells = rows[i].cells;
                            console.log('DEBUG: Found Match Table Headers:', Array.from(cells).map(c => c.innerText));
                            for (let j = 0; j < cells.length; j++) {
                                const cText = cells[j].innerText.toLowerCase();
                                if (cText.includes('date')) colMap['date'] = j;
                                else if (cText.includes('opponent')) colMap['opponent'] = j;
                                else if (cText.includes('rating')) colMap['rating'] = j;
                                else if (cText.includes('score')) colMap['score'] = j;
                                else if (cText.includes('won') || cText.includes('loss')) colMap['result'] = j; 
                            }
                            break;
                        }
                    }
                    
                    if (headerIndex === -1) continue;
                    
                    for (let i = headerIndex + 1; i < rows.length; i++) {
                        const cells = rows[i].cells;
                        if (cells.length < 3) continue;

                        let dateStr = colMap['date'] !== undefined ? cells[colMap['date']].innerText.trim() : "";
                        let opponent = colMap['opponent'] !== undefined ? cells[colMap['opponent']].innerText.trim() : "";
                        let rating = colMap['rating'] !== undefined ? cells[colMap['rating']].innerText.trim() : "0";
                        let score = colMap['score'] !== undefined ? cells[colMap['score']].innerText.trim() : "";
                        
                        // Heuristic for result if column missing: check color or implied win/loss?
                        // Usually OmniPong has W/L column or color coding.
                        // We will just store the raw score for now.
                        
                        if (dateStr && opponent) {
                           results.push({
                               "date_str": dateStr,
                               "opponent_name": opponent,
                               "opponent_rating": parseInt(rating) || 0,
                               "score_summary": score,
                               "source": "omnipong"
                           }); 
                        }
                    }
                }
                return results;
            }
        """)
        
        # Save matches
        if matches:
            print(f"Found {len(matches)} matches. Saving...")
            async with AsyncSessionLocal() as session:
                from models import Match
                from datetime import datetime
                
                # ideally check for duplicates
                for m in matches:
                    try:
                        dt = datetime.strptime(m["date_str"], "%m/%d/%Y").date()
                    except:
                        dt = None
                    
                    # Dedup check (simple)
                    # For now just insert if not exists (complex due to no unique ID on match)
                    # We will append for this demo.
                    match = Match(
                        date=dt,
                        opponent_name=m["opponent_name"],
                        opponent_rating=m["opponent_rating"],
                        score_summary=m["score_summary"],
                        source="omnipong"
                    )
                    session.add(match)
                await session.commit()
                print("Matches saved.")
        else:
            print("No matches found on history page.")
        
        return matches


    async def scrape_rating_history(self):
        """
        Scrapes tournament history to get the user's rating progression (USATT Rating).
        Targeting 'My Tournaments' page (s=2) which usually lists 'Ending Rating'.
        """
        page = await self.browser_manager.get_page()
        print("Scraping USATT Rating History...")
        await page.goto("https://www.omnipong.com/Members.asp?s=2") # s=2 is typically My Tournaments
        await page.wait_for_load_state("domcontentloaded")
        
        ratings = await page.evaluate("""
            () => {
                const results = [];
                const tables = Array.from(document.querySelectorAll('table'));
                for (const table of tables) {
                    const rows = Array.from(table.rows);
                    if (rows.length < 2) continue;
                    
                    let headerIndex = -1;
                    let colMap = {};
                    
                    for (let i = 0; i < Math.min(rows.length, 5); i++) {
                        const text = rows[i].innerText.toLowerCase();
                        if (text.includes('date') && (text.includes('name') || text.includes('tournament'))) {
                            headerIndex = i;
                            const cells = rows[i].cells;
                            for (let j = 0; j < cells.length; j++) {
                                const cText = cells[j].innerText.toLowerCase();
                                if (cText.includes('date')) colMap['date'] = j;
                                else if (cText.includes('rating') && (cText.includes('end') || cText.includes('new'))) colMap['rating'] = j;
                            }
                            break;
                        }
                    }
                    
                    if (headerIndex === -1) continue;
                    
                    for (let i = headerIndex + 1; i < rows.length; i++) {
                        const row = rows[i];
                        const cells = row.cells;
                        if (cells.length < 3) continue;
                        
                        let dateStr = colMap['date'] !== undefined ? cells[colMap['date']].innerText.trim() : "";
                        let ratingStr = colMap['rating'] !== undefined ? cells[colMap['rating']].innerText.trim() : "";
                        
                        // Clean rating
                        let rating = parseInt(ratingStr.replace(/[^0-9]/g, ''));
                        
                        if (dateStr && rating > 0) {
                            results.push({
                                date_str: dateStr,
                                rating: rating
                            });
                        }
                    }
                }
                return results;
            }
        """)
        
        if ratings:
            print(f"Found {len(ratings)} historical rating points from tournaments.")
            async with AsyncSessionLocal() as session:
                from models import RatingHistory
                
                # Clear existing USATT history to avoid dupes/mess
                # await session.execute(delete(RatingHistory).where(RatingHistory.source == 'omnipong'))
                
                for r in ratings:
                    try:
                        dt = datetime.strptime(r["date_str"], "%m/%d/%Y").date()
                        # Check exist
                        from sqlalchemy import select
                        stmt = select(RatingHistory).where(RatingHistory.source == 'omnipong', RatingHistory.date == dt)
                        res = await session.execute(stmt)
                        if not res.scalar_one_or_none():
                            rh = RatingHistory(
                                date=dt,
                                rating=r["rating"],
                                source="omnipong",
                                notes="Tournament Result"
                            )
                            session.add(rh)
                    except Exception as e:
                        print(f"Error saving rating point: {e}")
                
                await session.commit()
                print("USATT Rating History saved.")
        else:
            print("No rating history found on Tournaments page.")

    async def scrape_tournament_entries(self, source_id: str):
        """
        Navigates to the tournament entries page and extracts player ratings.
        """
        page = await self.browser_manager.get_page()
        if source_id.startswith('http'):
            base_url = source_id
        else:
            base_url = f"https://www.omnipong.com/{source_id}"
            
        print(f"Scraping entries from {base_url}...")
        
        await page.goto(base_url)
        await page.wait_for_load_state("domcontentloaded")
        
        # 1. Find 'Entries', 'Players', 'Standings', 'Results' link
        entries_url = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a'));
                const valid = links.find(l => {
                    const t = l.innerText.toLowerCase();
                    return (t.includes('entries') || t.includes('players') || t.includes('standings') || t.includes('looking') || t.includes('result')) 
                           && !l.href.toLowerCase().endsWith('.pdf');
                });
                return valid ? valid.href : null;
            }
        """)
        
        if not entries_url:
            print(f"No specific 'Entries' link found for {base_url}. Checking if current page has a player table...")
            entries_url = base_url # Fallback to current page
        else:
            print(f"Found Entries link: {entries_url}")
            await page.goto(entries_url)
            await page.wait_for_load_state("domcontentloaded")
            
        # 2. Extract Players and Ratings
        players = await page.evaluate("""
            () => {
                const results = [];
                const tables = Array.from(document.querySelectorAll('table'));
                
                for (const table of tables) {
                    const rows = Array.from(table.rows);
                    if (rows.length < 2) continue;
                    
                    let headerIndex = -1;
                    let colMap = {};
                    
                    // Header heuristic
                    for (let i = 0; i < Math.min(rows.length, 5); i++) {
                        const text = rows[i].innerText.toLowerCase();
                        if (text.includes('name') && (text.includes('rating') || text.includes('seed'))) {
                            headerIndex = i;
                            const cells = rows[i].cells;
                            for (let j = 0; j < cells.length; j++) {
                                const cText = cells[j].innerText.toLowerCase();
                                if (cText.includes('name')) colMap['name'] = j;
                                else if (cText.includes('rating')) colMap['rating'] = j;
                                else if (cText.includes('city')) colMap['city'] = j; 
                                else if (cText.includes('state')) colMap['state'] = j;
                            }
                            break;
                        }
                    }
                    
                    if (headerIndex === -1) continue;
                    
                    for (let i = headerIndex + 1; i < rows.length; i++) {
                        const row = rows[i];
                        const cells = row.cells;
                        if (cells.length < 2) continue;
                        
                        let name = colMap['name'] !== undefined ? cells[colMap['name']].innerText.trim() : "";
                        let ratingStr = colMap['rating'] !== undefined ? cells[colMap['rating']].innerText.trim() : "0";
                        let city = colMap['city'] !== undefined ? cells[colMap['city']].innerText.trim() : "";
                        let state = colMap['state'] !== undefined ? cells[colMap['state']].innerText.trim() : "";
                        
                        // Clean rating
                        const rMatch = ratingStr.match(/\d+/);
                        let rating = rMatch ? parseInt(rMatch[0]) : 0;
                        
                        if (name && name.length > 2) {
                            results.push({
                                name: name,
                                rating: rating,
                                location: city + (state ? ", " + state : ""),
                                source_tournament: window.location.href
                            });
                        }
                    }
                }
                return results;
            }
        """)
        
        print(f"Found {len(players)} players with ratings.")
        return players

    async def scrape_tournament_results(self, source_id: str):
        """
        Navigates to results page and scrapes match results + ratings.
        """
        page = await self.browser_manager.get_page()
        # Parse t=ID
        import re
        t_match = re.search(r'[Tt]-tourney\.asp\?t=(\d+)', source_id)
        if not t_match: return []
        t_id = t_match.group(1)
        
        base_url = f"https://www.omnipong.com/T-tourney.asp?t={t_id}"
        print(f"Scraping results for tournament {t_id}...")
        
        await page.goto(base_url)
        await page.wait_for_load_state("domcontentloaded")
        
        # Find 'Results' link
        results_url = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a'));
                const valid = links.find(l => l.innerText.toLowerCase().includes('results') && !l.href.toLowerCase().endsWith('.pdf'));
                return valid ? valid.href : null;
            }
        """)
        
        if results_url:
            print(f"Found Results link: {results_url}")
            await page.goto(results_url)
            await page.wait_for_load_state("domcontentloaded")
            
            # TODO: Add specific result table scraping if needed
            # For now, we assume Entries list is the best source for 'Pre-Tournament Official Ratings'
            # Results pages often show rating CHANGE which is also good, but structure is complex (draws).
            return [] 
        
        return []

    async def save_tournament_players(self, players_data):
        print(f"Preparing to sync {len(players_data)} tournament players...")
        async with AsyncSessionLocal() as session:
            for data in players_data:
                from sqlalchemy import select
                # Check if player exists
                stmt = select(Player).where(Player.name == data["name"])
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update if source is tournament (assumed higher quality)
                    # OR if existing is just from 'family_search' (potentially league rating)
                    # We always update with latest tournament rating
                    existing.rating = data["rating"]
                    existing.state = data['location'].split(',')[-1].strip() if ',' in data['location'] else existing.state
                    existing.rating_source = 'tournament_entry'
                    existing.last_updated = datetime.utcnow()
                else:
                    player = Player(
                        name=data["name"],
                        rating=data["rating"],
                        state=data['location'].split(',')[-1].strip() if ',' in data['location'] else "",
                        rating_source='tournament_entry'
                    )
                    session.add(player)
            
            await session.commit()
            print("Tournament Players synced.")



    async def scrape_my_tournament_history(self):
        """
        Scrapes list of tournaments from Members.asp?s=2
        """
        page = await self.browser_manager.get_page()
        print("Scraping My Tournament History...")
        await page.goto("https://www.omnipong.com/Members.asp?s=2")
        await page.wait_for_load_state("domcontentloaded")
        
        activities = await self._extract_tournament_list_from_table(page)
        print(f"Found {len(activities)} tournaments in history.")
        return activities

    async def signup_for_tournament(self, tournament_title: str, recommended_events: list[str]):
        """
        Automated signup flow:
        1. Login and go to Tournaments list.
        2. Find Texas section and the specific tournament.
        3. Click 'Enter'.
        4. Click 'I Accept' on terms.
        5. Click 'Enter' for each recommended event.
        """
        page = await self.browser_manager.get_page()
        
        # 1. Login handled by browser manager
        print("Logging in to OmniPong...")
        await self.browser_manager.login_omnipong()
        
        # 2. Go to Tournaments page (e=0)
        print("Navigating to Tournament list...")
        await page.goto("https://www.omnipong.com/t-tourney.asp?e=0")
        await page.wait_for_load_state("networkidle")
        
        # 3. Find Tournament and click 'Enter'
        print(f"Searching for 'Enter' button for: {tournament_title}")
        
        # Use XPath to find the row with tournament title and the 'Enter' button in it.
        # Note: Tournament title in list might be truncated or slightly different, but contains title.
        enter_btn_found = await page.evaluate(f"""
            () => {{
                const targetTitle = "{tournament_title}".toLowerCase();
                const rows = Array.from(document.querySelectorAll('tr'));
                for (const row of rows) {{
                    const text = row.innerText.toLowerCase();
                    if (text.includes(targetTitle) && text.includes('texas')) {{
                        const enterBtn = row.querySelector('input[value="Enter"], button:has-text("Enter")');
                        if (enterBtn) {{
                            enterBtn.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}
        """)
        
        if not enter_btn_found:
            # Fallback: Scroll and try again? Or search for exact title match in links
            print(f"Could not find tournament '{tournament_title}' in Texas section via direct row search. Trying link search...")
            await page.evaluate(f"""
                () => {{
                    const links = Array.from(document.querySelectorAll('a'));
                    const targetTitle = "{tournament_title}".toLowerCase();
                    const tourneyLink = links.find(l => l.innerText.toLowerCase().includes(targetTitle));
                    if (tourneyLink) {{
                         const row = tourneyLink.closest('tr');
                         const enterBtn = row.querySelector('input[value="Enter"]');
                         if (enterBtn) enterBtn.click();
                    }}
                }}
            """)
        
        # 4. Wait for 'I Accept' page
        print("Waiting for 'I Accept' page...")
        try:
            accept_btn = await page.wait_for_selector('input[value="I Accept"]', timeout=10000)
            if accept_btn:
                print("Clicking 'I Accept'...")
                await accept_btn.click()
                await page.wait_for_load_state("networkidle")
        except Exception as e:
            print(f"Error finding 'I Accept' button (maybe already entered?): {e}")
            # Check if we are already on events page
            if not await page.query_selector('text="Please select the events you wish to play"'):
                return {"status": "error", "message": "Failed to reach signup confirmation page."}

        # 5. Select Events
        print(f"Selecting events: {recommended_events}")
        results = []
        for event_name in recommended_events:
            print(f"Attempting to enter event: {event_name}")
            entered = await page.evaluate(f"""
                () => {{
                    const targetEvent = "{event_name}".toLowerCase();
                    const rows = Array.from(document.querySelectorAll('tr'));
                    for (const row of rows) {{
                        if (row.innerText.toLowerCase().includes(targetEvent)) {{
                            const btn = row.querySelector('input[value="Enter"]');
                            if (btn) {{
                                btn.click();
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }}
            """)
            if entered:
                print(f"Successfully clicked 'Enter' for {event_name}")
                results.append(event_name)
                # Small wait for action to process if page reloads or updating state
                await asyncio.sleep(2)
            else:
                print(f"Could not find 'Enter' button for {event_name} (already full or ineligible?)")

        return {
            "status": "success",
            "tournament": tournament_title,
            "entered_events": results,
            "message": f"Signed up for {len(results)} events in {tournament_title}"
        }

    async def scrape_regional_tournaments(self):
        """
        Scrapes regional tournaments (Region 8).
        """
        page = await self.browser_manager.get_page()
        # URL provided by user for Region 8
        url = "https://www.omnipong.com/T-tourney.asp?t=8&Region=8&y=&k=&e=0"
        print(f"Scraping Regional Tournaments from {url}...")
        await page.goto(url)
        await page.wait_for_load_state("domcontentloaded")
        
        activities = await self._extract_tournament_list_from_table(page)
        print(f"Found {len(activities)} tournaments in region.")
        return activities

    async def _extract_tournament_list_from_table(self, page):
        """
        Helper to extract tournament links/dates from a standard list table.
        Modified to handle both <a> links and <input onclick=open_window(...)> buttons.
        """
        return await page.evaluate("""
            () => {
                const results = [];
                const rows = Array.from(document.querySelectorAll('table tr'));
                
                for (const row of rows) {
                    let sourceId = null;
                    let title = "Unknown Tournament";
                    
                    // 1. Try to find direct <a> link with t-tourney (Old style)
                    const links = Array.from(row.querySelectorAll('a'));
                    const tLink = links.find(l => l.href.includes('t-tourney.asp?t=') && !l.href.endsWith('.pdf'));
                    
                    if (tLink) {
                         sourceId = tLink.href;
                         title = tLink.innerText.trim();
                    }
                    
                    // 2. If no direct link, look for "Players" or "Results" button (onclick)
                    if (!sourceId) {
                        const inputs = Array.from(row.querySelectorAll('input[type="submit"]'));
                        // prioritized: Players (t=100) -> Results (t=103) -> Enter (?)
                        const playersBtn = inputs.find(i => i.value === 'Players');
                        const resultsBtn = inputs.find(i => i.value === 'Results');
                        
                        const targetBtn = playersBtn || resultsBtn;
                        
                        if (targetBtn) {
                            // extract url from onclick="open_window('URL',...)"
                            const onClick = targetBtn.getAttribute('onclick');
                            if (onClick) {
                                const match = onClick.match(/open_window\\('([^']+)'/);
                                if (match && match[1]) {
                                    sourceId = "https://www.omnipong.com/" + match[1];
                                }
                            }
                        }
                        
                        // Get title from the PDF link usually in the Name col
                        const nameLink = links.find(l => l.innerText.length > 5); // Simple heuristic
                        if (nameLink) {
                            title = nameLink.innerText.trim();
                        }
                    }

                    if (sourceId) {
                    // Try to find date in row (MM/DD/YY or MM/DD/YYYY)
                    const dateText = row.innerText.match(/\d{1,2}\/\d{1,2}\/\d{2,4}/);
                    const dateStr = dateText ? dateText[0] : null;
                        
                        // Location is usually in the 4th cell (index 3)
                        const cells = Array.from(row.cells);
                        const location = cells.length >= 4 ? cells[3].innerText.trim() : null;
                        
                        results.push({
                            title: title,
                            source_id: sourceId,
                            date_str: dateStr,
                            location: location
                        });
                    }
                }
                return results;
            }
        """)

    async def bulk_sync_tournaments(self, activities_list):
        """
        Orchestrator: Checks DB, decides whether to scrape, and saves.
        """
        print(f"Starting Bulk Sync for {len(activities_list)} tournaments...")
        
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            
            for act in activities_list:
                # Standardize source_id
                # Ensure we store relative or absolute consistently? 
                # Scraper uses full URL usually. Let's stick to full URL or whatever matches.
                # Only keep the t= part unique? No, source_id is better unique.
                
                # Check DB
                stmt = select(Activity).where(Activity.source_id == act['source_id'])
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                should_scrape = False
                
                if not existing:
                    print(f"[NEW] {act['title']} - Scraping...")
                    should_scrape = True
                    # Create placeholder activity
                    try:
                    # Try MM/DD/YYYY first, then MM/DD/YY
                        if act['date_str']:
                            try:
                                dt = datetime.strptime(act['date_str'], "%m/%d/%Y").date()
                            except ValueError:
                                # Try 2-digit year format
                                dt = datetime.strptime(act['date_str'], "%m/%d/%y").date()
                        else:
                            dt = None
                    except: 
                        dt = None
                    
                    new_act = Activity(
                        source="omnipong",
                        source_id=act['source_id'],
                        title=act['title'],
                        activity_type='tournament',
                        date=dt,
                        location=act.get('location'),
                        status='upcoming',
                        last_scraped=datetime.utcnow()
                    )
                    session.add(new_act)
                    await session.flush() # get ID
                    existing = new_act
                else:
                    # Smart Sync Check
                    if not existing.status:
                        existing.status = 'upcoming'
                    if not existing.location and act.get('location'):
                        existing.location = act['location']
                    
                    time_since_scrape = (datetime.utcnow() - existing.last_scraped).total_seconds() / 3600.0 if existing.last_scraped else 9999
                    
                    is_past = False
                    if existing.date and existing.date < datetime.utcnow().date():
                        # buffer of 7 days for late results
                        if (datetime.utcnow().date() - existing.date).days > 7:
                            is_past = True
                    
                    if is_past:
                        print(f"[SKIP] {act['title']} (Past & Scraped)")
                        should_scrape = False
                    elif time_since_scrape < 12:
                        print(f"[SKIP] {act['title']} (Functionally fresh, {time_since_scrape:.1f}h ago)")
                        should_scrape = False
                    else:
                        print(f"[UPDATE] {act['title']} (Refreshing...)")
                        should_scrape = True
                
                if should_scrape:
                    try:
                        # Standardize source_id for event scraping
                        clean_sid = act['source_id']
                        if 'omnipong.com/' in clean_sid:
                            clean_sid = clean_sid.split('omnipong.com/')[-1]
                        if clean_sid.startswith('/'):
                            clean_sid = clean_sid[1:]

                        # 1. Scrape Players
                        players = await self.scrape_tournament_entries(act['source_id'])
                        if players:
                            await self.save_tournament_players(players)
                        
                        # 2. Scrape Events [NEW]
                        events = await self.scrape_activity_events(clean_sid)
                        if events:
                            from models import Event
                            # Clear old events
                            await session.execute(delete(Event).where(Event.activity_id == existing.id))
                            for evt_data in events:
                                evt = Event(**evt_data)
                                evt.activity_id = existing.id
                                session.add(evt)

                        # Update last_scraped
                        existing.last_scraped = datetime.utcnow()
                        await session.commit()
                        
                        # Be nice to the server
                        await asyncio.sleep(2) 
                    except Exception as e:
                        print(f"Failed to scrape {act['title']}: {e}")
                        
        print("Bulk Sync Complete.")

async def test_scraper():
    print("Starting OmniPong Scraper Test...")
    await init_db()
    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    try:
        await manager.login_omnipong()
        print("Logged in.")
        
        # Run specific rating history scrape
        await scraper.scrape_rating_history()
        
        print("Scraping Matches to check for rating columns...")
        await scraper.scrape_my_matches()
        
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await manager.stop()
        print("Scraper test complete.")

if __name__ == "__main__":
    asyncio.run(test_scraper())
