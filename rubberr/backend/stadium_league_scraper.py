print("SCRIPT STARTING...")
"""
Stadium Compete League Match Scraper
Scrapes match history from league pages using the MATCHES tab filter
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from playwright.async_api import async_playwright
from datetime import datetime
import sqlite3
import re

async def scrape_league_matches(league_url, player_name="Johnson, Justin"):
    """
    Scrapes completed matches from a Stadium Compete league page.
    """
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = os.path.join(root_dir, 'omnipong.db')
    env_path = os.path.join(root_dir, '.env')
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug')
    
    async with async_playwright() as p:
        print("Launching System Chrome...")
        browser = await p.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=False,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()
        
        try:
            stadium_email = None
            stadium_password = None
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    for line in f:
                        if line.startswith('STADIUM_USER='): stadium_email = line.split('=')[1].strip()
                        elif line.startswith('STADIUM_PASS='): stadium_password = line.split('=')[1].strip()
            
            if not stadium_email or not stadium_password:
                print("❌ Credentials missing in .env")
                return

            print(">>> Logging in...")
            await page.goto("https://stadiumcompete.com/log-in", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            
            # Accept cookies if modal exists
            try:
                accept_btn = await page.query_selector('button:has-text("Accept"), button:has-text("ACCEPT")')
                if accept_btn:
                    await accept_btn.click()
                    print("  Accepted cookies modal")
                    await page.wait_for_timeout(1000)
            except: pass

            email_field = await page.wait_for_selector('input[type="email"]', timeout=30000)
            await email_field.fill(stadium_email)
            await page.fill('input[type="password"]', stadium_password)
            await page.click('button[type="submit"]')
            await page.wait_for_url("**/dashboard", timeout=30000)
            print("✅ Login successful")
            
            print(">>> Step: Navigating to league matches...")
            try:
                # Use domcontentloaded to avoid hanging on analytics/ads, then wait for specific element
                await page.goto(league_url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)
            except Exception as e:
                print(f"  Note: Navigation warning: {e}")

            print(">>> Step: Ensuring MATCHES tab...")
            try:
                # Try multiple possible selectors for the MATCHES tab
                matches_tab = await page.wait_for_selector('button:has-text("MATCHES"), .TabbedView-tab:has-text("MATCHES")', timeout=20000)
                if matches_tab:
                    await matches_tab.click()
                    await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"  Note: MATCHES tab already active or error: {e}")

            print(f">>> Step: Filtering by player: {player_name}...")
            try:
                # Clear existing filters if any (often helps reliability)
                try:
                    clear_btn = await page.query_selector('button:has-text("Show All")')
                    if clear_btn:
                        await clear_btn.click()
                        await page.wait_for_timeout(2000)
                except: pass

                player_input = await page.wait_for_selector('input[placeholder*="Player"]', timeout=20000)
                await player_input.click()
                await player_input.fill(player_name)
                await page.wait_for_timeout(3000)
                
                # Click the option matching the player name exactly
                try:
                    option = await page.wait_for_selector(f'ul[role="listbox"] li:has-text("{player_name}"), .MuiAutocomplete-option:has-text("{player_name}")', timeout=10000)
                    if option:
                        await option.click()
                        print("  Selected player from dropdown")
                        await page.wait_for_timeout(3000)
                except:
                    print("  Note: Specific player option not found, pressing Enter")
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(5000)
            except Exception as e:
                print(f"  Note: Filtering error: {e}")

            # Take screenshot to verify filters are set
            print(">>> Taking screenshot of matches page...")
            await page.screenshot(path=os.path.join(debug_dir, "matches_page_before_scrape.png"), full_page=True)
            print(f"  Screenshot saved to: {os.path.join(debug_dir, 'matches_page_before_scrape.png')}")
            
            print(">>> Step: Verifying Filters...")
            try:
                # 1. Player Filter Check
                player_input = page.locator('input[placeholder*="Player"]')
                if await player_input.count() > 0:
                    current_val = await player_input.input_value()
                    if "Johnson" not in current_val:
                        print("  Setting Player Filter...")
                        await player_input.click()
                        await page.keyboard.type("Johnson, Justin")
                        await page.wait_for_timeout(1000)
                        await page.keyboard.press("ArrowDown")
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(2000)
                    else:
                        print("  ✅ Player filter correct.")

                # 2. Status Filter Check
                # We try to ensure 'Completed' is set. 
                print("  Setting 'Completed' status...")
                # Try clicking any element that looks like the Status dropdown
                status_clicked = False
                for sel in ['div[role="combobox"]:has-text("Status")', 'input[placeholder="Status"]', 'div.MuiSelect-root:has-text("Status")']:
                    if await page.locator(sel).count() > 0:
                        await page.click(sel)
                        status_clicked = True
                        break
                
                if not status_clicked:
                    # Fallback generic click
                    await page.click('text="Status"', timeout=2000)

                await page.wait_for_timeout(500)
                # Click Completed
                await page.click('li:has-text("Completed")', timeout=2000)
                # Close dropdown 
                await page.keyboard.press("Escape")
                
            except Exception as e:
                print(f"  Note: Filter adjustment (continuing): {e}")
            
            print(">>> Step: Final scroll and extraction...")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)

            print(">>> Scraping matches and user rating history...")
            results = await page.evaluate("""
                (userName) => {
                    const matches = [];
                    const ratingPoints = [];
                    const logs = [];
                    const userRegex = new RegExp(userName, 'i');
                    
                    const cards = document.querySelectorAll('.MatchCard');
                    logs.push(`Found ${cards.length} cards currently visible`);
                    
                    for (const card of cards) {
                        try {
                            const info = card.querySelector('.MatchCard-info');
                            const inner = card.querySelector('.MatchCard-inner');
                            if (!info || !inner) continue;

                            // 1. Get Date
                            let dateStr = null;
                            const descEl = info.querySelector('.TournamentMatchDescription');
                            const datePattern = /([A-Z]+ \\d{1,2}, \\d{4})/i;
                            
                            if (descEl) {
                                const m = descEl.innerText.match(datePattern);
                                if (m) dateStr = m[1];
                            }
                            
                            if (!dateStr) {
                                const m = card.innerText.match(datePattern);
                                if (m) dateStr = m[1];
                            }

                            // 2. Process sides
                            const sides = Array.from(inner.querySelectorAll('.MatchCard-score-and-side'));
                            if (sides.length !== 2) continue;

                            let userData = null;
                            let opponentData = null;

                            for (const side of sides) {
                                const nameEl = side.querySelector('.Entry-name');
                                const scoreEl = side.querySelector('.MatchCard-score');
                                const ratingEl = side.querySelector('.Entry-affiliation');
                                
                                if (!nameEl || !scoreEl) continue;

                                const name = nameEl.innerText.trim();
                                const score = scoreEl.innerText.trim();
                                let rating = null;
                                if (ratingEl) {
                                    const rm = ratingEl.innerText.match(/(\\d{3,4})/);
                                    if (rm) rating = parseInt(rm[1]);
                                }

                                const data = { name, score, rating };
                                if (userRegex.test(name)) userData = data;
                                else opponentData = data;
                            }

                            if (userData && opponentData && dateStr) {
                                if (userData.rating) {
                                    ratingPoints.push({ date: dateStr, rating: userData.rating });
                                }

                                matches.push({
                                    date: dateStr,
                                    opponent: opponentData.name,
                                    opponent_rating: opponentData.rating,
                                    result: parseInt(userData.score) > parseInt(opponentData.score) ? 'W' : 'L',
                                    score_summary: `${userData.score}-${opponentData.score}`,
                                    set_scores: null,
                                    card_index: Array.from(cards).indexOf(card)
                                });
                            }
                        } catch (e) {
                            logs.push(`Error parsing card: ${e.message}`);
                        }
                    }
                    return { matches, ratingPoints, logs };
                }
            """, player_name)
            
            matches = results['matches']
            ratingPoints = results['ratingPoints']
            logs = results.get('logs', [])
            
            for log in logs[:20]:
                print(f"  JS Log: {log}")
            
            print(f"Found {len(matches)} matches to process.")
            
            # Now click on each match to get set scores
            # The user specifically requested to "click the match score" to get set scores
            for i, match in enumerate(matches):
                try:
                    card_index = match.get('card_index')
                    print(f"  Processing match {i+1}/{len(matches)}: vs {match['opponent']}")
                    
                    # Click the score element specifically (often the center part) to open the modal/details
                    await page.evaluate(f"""
                        (idx) => {{
                            const cards = document.querySelectorAll('.MatchCard');
                            const card = cards[idx];
                            if (card) {{
                                // VERIFIED: Use MatchCard-toggle if present, otherwise score wrapper
                                const toggleBtn = card.querySelector('.MatchCard-toggle');
                                const scoreBtn = card.querySelector('.MatchCard-score-wrapper');
                                
                                if (toggleBtn) toggleBtn.click();
                                else if (scoreBtn) scoreBtn.click();
                                else card.click();
                            }}
                        }}
                    """, card_index)
                    
                    # Wait for expansion - increased specific wait
                    await page.wait_for_timeout(2500)
                    
                    # Extract Data using DOM parsing
                    details = await page.evaluate(f"""
                        (idx) => {{
                            const cards = document.querySelectorAll('.MatchCard');
                            const card = cards[idx];
                            if (!card) return {{ scores: null, match_score: null }};
                            let validSets = [];
                            let mainScore = null;
                            
                            // Strategy: Parse specific Score elements first (Most reliable)
                            const scoreRows = card.querySelectorAll('.MatchScoresV2-game-scores');
                            if (scoreRows.length > 0) {{
                                scoreRows.forEach(row => {{
                                    // multiple scores in a row? No, usually a column pair
                                    const scoreDivs = row.querySelectorAll('.MatchScoresV2-score');
                                    if (scoreDivs.length >= 2) {{
                                        const s1 = scoreDivs[0].innerText.trim();
                                        const s2 = scoreDivs[1].innerText.trim();
                                        if (s1 && s2) {{
                                            validSets.push(`${{s1}}-${{s2}}`);
                                        }}
                                    }}
                                }});
                            }} 
                            else {{
                                // Capture text from the card AND any expanded rows/modals nearby
                                let textContent = card.innerText;
                            }}
                            
                            // Get Match Result
                            const scoreMain = card.querySelectorAll('.MatchCard-score');
                            let p1Score = '0'; 
                            let p2Score = '0';
                            if(scoreMain.length >= 2) {{
                                p1Score = scoreMain[0].innerText.trim();
                                p2Score = scoreMain[1].innerText.trim();
                                mainScore = `${{p1Score}}-${{p2Score}}`;
                            }}

                            // Return result object
                            return {{
                                set_scores: validSets.join(', '),
                                match_score: mainScore,
                                raw_text: "Parsed DOM directly",
                                html_debug: card.outerHTML
                            }};
                        }}
                    """, card_index)

                    if details['set_scores']:
                        match['set_scores'] = details['set_scores']
                        print(f"    ✅ Set Scores: {details['set_scores']}")

                    if details['match_score']:
                        match['result'] = details['match_score']
                        # print(f"    Updated Match Score: {details['match_score']}")

                    # Close expansion
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)

                    
                    # Extract set scores from the Match Details Modal or expanded view

                    
                except Exception as e:
                    print(f"    Error on match {i+1}: {e}")

            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Save rating history
            saved_rp = 0
            for rp in ratingPoints:
                try:
                    dt = datetime.strptime(rp['date'], "%B %d, %Y").date()
                    cursor.execute("SELECT id FROM rating_history WHERE date=? AND rating=? AND source='stadium_league'", (dt, rp['rating']))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO rating_history (date, rating, source, notes) VALUES (?, ?, 'stadium_league', 'League Match Scrape')",
                                       (dt, rp['rating']))
                        saved_rp += 1
                except: continue
            
            # Save matches
            saved_m = 0
            updated_m = 0
            for m in matches:
                try:
                    dt = datetime.strptime(m['date'], "%B %d, %Y").date()
                    # Check if match already exists with same date and opponent
                    cursor.execute("SELECT id, set_scores FROM matches WHERE date=? AND opponent_name=? AND source='stadium_league'", (dt, m['opponent']))
                    row = cursor.fetchone()
                    
                    if not row:
                        cursor.execute(
                            "INSERT INTO matches (date, opponent_name, opponent_rating, result, score_summary, set_scores, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (dt, m['opponent'], m['opponent_rating'], m['result'], m['score_summary'], m.get('set_scores'), 'stadium_league')
                        )
                        saved_m += 1
                    else:
                        # Update if set_scores is new and not null
                        if m.get('set_scores') and (not row[1] or row[1] != m.get('set_scores')):
                            cursor.execute(
                                "UPDATE matches SET set_scores=? WHERE id=?",
                                (m.get('set_scores'), row[0])
                            )
                            updated_m += 1
                            print(f"    Updated match {row[0]} with scores: {m.get('set_scores')}")
                except Exception as e: 
                    print(f"    Error saving match: {e}")
                    continue
            
            print(f"✅ Saved {saved_rp} new rating points, {saved_m} new matches, {updated_m} updated matches.")
                
            conn.commit()
            conn.close()
            print(f"✅ Saved {saved_rp} new rating points and {saved_m} new matches.")
            
        finally:
            await browser.close()

async def scrape_rating_history():
    """
    Scrapes the user's rating history from the dashboard.
    """
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = os.path.join(root_dir, 'omnipong.db')
    env_path = os.path.join(root_dir, '.env')
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            stadium_email = None
            stadium_password = None
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    for line in f:
                        if line.startswith('STADIUM_USER='): stadium_email = line.split('=')[1].strip()
                        elif line.startswith('STADIUM_PASS='): stadium_password = line.split('=')[1].strip()
            
            print(">>> Logging in for rating history...")
            await page.goto("https://stadiumcompete.com/log-in", wait_until="domcontentloaded")
            await page.fill('input[type="email"]', stadium_email)
            await page.fill('input[type="password"]', stadium_password)
            await page.click('button[type="submit"]')
            await page.wait_for_url("**/dashboard", timeout=30000)
            
            # Extract historical rating points from the dashboard or profile
            # Based on user context, we want "Rating Trajectory"
            # We'll scrape the current rating and look for any history data in the page source
            
            await page.wait_for_timeout(3000) # Wait for charts
            
            rating_history = await page.evaluate("""
                () => {
                    const results = [];
                    // Typical NEXT_DATA or global state check
                    const nextData = window.__NEXT_DATA__;
                    if (nextData && nextData.props && nextData.props.pageProps) {
                        // Check for ratings array
                        const props = nextData.props.pageProps;
                        // This is speculative, mapping known MUI/Next.js dashboard structures
                    }
                    
                    // Fallback: Scrape the current sidebar rating
                    const sidebar = document.body.innerText;
                    const ratingMatch = sidebar.match(/STADIUM Rating:\\s*(\\d+)/i);
                    if (ratingMatch) {
                        results.push({
                            date: new Date().toISOString().split('T')[0],
                            rating: parseInt(ratingMatch[1])
                        });
                    }
                    return results;
                }
            """)
            
            if rating_history:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                for rh in rating_history:
                    # Check if already exists
                    cursor.execute("SELECT id FROM rating_history WHERE date=? AND source='stadium_league'", (rh['date'],))
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO rating_history (date, rating, source, notes) 
                            VALUES (?, ?, ?, ?)
                        """, (rh['date'], rh['rating'], 'stadium_league', 'Dashboard Scrape'))
                conn.commit()
                conn.close()
                print("✅ Rating history updated from dashboard")

            # NEW: Try to get history from the Matches page - sometimes shows "New Rating"
            print(">>> Navigating to main matches page for historical points...")
            await page.goto("https://stadiumcompete.com/matches", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            
            history_points = await page.evaluate("""
                () => {
                    const points = [];
                    // Look for table rows that might have date and rating
                    const rows = Array.from(document.querySelectorAll('tr'));
                    for (const row of rows) {
                        const text = row.innerText;
                        // Heuristic: row has a date and a rating-like number
                        const dateMatch = text.match(/([A-Z]+\\s+\\d{1,2},\\s+\\d{4})/);
                        // If there's a specific 'Rating' column, we'd grab it. 
                        // For now, let's just log if we see potential data.
                    }
                    return points;
                }
            """)
            print(f"Scanned matches page, found {len(history_points)} potential history points.")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    print("Entered __main__")
    LEAGUE_URL = "https://stadiumcompete.com/tournament/a12a04fd-c1e1-4e7d-b698-0f2bb91120e8#matches"
    try:
        asyncio.run(scrape_league_matches(LEAGUE_URL))
        # asyncio.run(scrape_rating_history())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
