"""
Quick script to scrape set scores from the currently open Stadium browser page
"""
import asyncio
from playwright.async_api import async_playwright
import json
import os

# Write debug artifacts next to this script, not to a hardcoded absolute path.
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

async def scrape_current_page():
    async with async_playwright() as p:
        # Connect to existing browser (CDP endpoint)
        # This will connect to the browser that's already open
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            if not contexts:
                print("No browser contexts found")
                return
            
            context = contexts[0]
            pages = context.pages
            
            # Find the Stadium page
            stadium_page = None
            for page in pages:
                if "stadiumcompete.com" in page.url:
                    stadium_page = page
                    break
            
            if not stadium_page:
                print("No Stadium page found")
                return
            
            print(f"Found Stadium page: {stadium_page.url}")
            
            # Take screenshot
            await stadium_page.screenshot(path=os.path.join(DEBUG_DIR, "current_page.png"), full_page=True)
            print("Screenshot saved")
            
            # Get all match cards
            matches_data = await stadium_page.evaluate("""
                () => {
                    const cards = document.querySelectorAll('.MatchCard');
                    console.log(`Found ${cards.length} match cards`);
                    
                    const matches = [];
                    cards.forEach((card, idx) => {
                        // Get date
                        const dateEl = card.querySelector('.TournamentMatchDescription');
                        const date = dateEl ? dateEl.innerText : 'No date';
                        
                        // Get players and scores
                        const sides = card.querySelectorAll('.MatchCard-score-and-side');
                        let player1 = '', player2 = '', score1 = '', score2 = '';
                        
                        if (sides.length >= 2) {
                            const name1 = sides[0].querySelector('.Entry-name');
                            const score1El = sides[0].querySelector('.MatchCard-score');
                            const name2 = sides[1].querySelector('.Entry-name');
                            const score2El = sides[1].querySelector('.MatchCard-score');
                            
                            player1 = name1 ? name1.innerText.trim() : '';
                            score1 = score1El ? score1El.innerText.trim() : '';
                            player2 = name2 ? name2.innerText.trim() : '';
                            score2 = score2El ? score2El.innerText.trim() : '';
                        }
                        
                        matches.push({
                            index: idx,
                            date: date,
                            player1: player1,
                            player2: player2,
                            score1: score1,
                            score2: score2
                        });
                    });
                    
                    return matches;
                }
            """)
            
            print(f"\\nFound {len(matches_data)} matches:")
            for m in matches_data[:5]:  # Show first 5
                print(f"  {m['date']}: {m['player1']} ({m['score1']}) vs {m['player2']} ({m['score2']})")
            
            # Now click each match to get set scores
            print(f"\\nClicking matches to get set scores...")
            for i, match in enumerate(matches_data[:10]):  # Process first 10 matches
                try:
                    print(f"\\nMatch {i+1}: {match['player1']} vs {match['player2']}")
                    
                    # Click the match card
                    await stadium_page.evaluate(f"""
                        (idx) => {{
                            const cards = document.querySelectorAll('.MatchCard');
                            const card = cards[idx];
                            if (card) {{
                                // Try clicking the score area
                                const scoreBtn = card.querySelector('.MatchCard-inner, .MatchCard-score');
                                if (scoreBtn) {{
                                    scoreBtn.click();
                                }} else {{
                                    card.click();
                                }}
                            }}
                        }}
                    """, i)
                    
                    # Wait for modal/expansion
                    await asyncio.sleep(2)
                    
                    # Extract set scores
                    set_scores_data = await stadium_page.evaluate("""
                        () => {
                            // Look for modal or expanded content
                            const modal = document.querySelector('.MuiDialog-content, .MatchDetails');
                            const container = modal || document.body;
                            
                            const allText = container.innerText;
                            
                            // Find score patterns
                            const scorePattern = /\\b([0-9]{1,2})-([0-9]{1,2})\\b/g;
                            const matches = [...allText.matchAll(scorePattern)];
                            
                            let validScores = [];
                            matches.forEach(m => {
                                const p1 = parseInt(m[1]);
                                const p2 = parseInt(m[2]);
                                
                                // Filter out dates and invalid scores
                                if (p1 === 0 && p2 < 11) return;
                                if (p1 > 50 || p2 > 50) return;
                                
                                validScores.push(m[0]);
                            });
                            
                            return {
                                scores: validScores,
                                sample: allText.substring(0, 300)
                            };
                        }
                    """)
                    
                    if set_scores_data['scores']:
                        print(f"  Set scores: {', '.join(set_scores_data['scores'])}")
                        match['set_scores'] = ', '.join(set_scores_data['scores'])
                    else:
                        print(f"  No set scores found")
                        print(f"  Sample text: {set_scores_data['sample'][:100]}")
                    
                    # Close modal
                    await stadium_page.keyboard.press('Escape')
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    print(f"  Error: {e}")
            
            # Save results
            with open(os.path.join(DEBUG_DIR, "scraped_matches.json"), 'w') as f:
                json.dump(matches_data, f, indent=2)
            
            print(f"\\n✅ Saved results to scraped_matches.json")
            
        except Exception as e:
            print(f"Error connecting to browser: {e}")
            print("\\nMake sure Chrome is running with remote debugging enabled:")
            print("  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222")

if __name__ == "__main__":
    asyncio.run(scrape_current_page())
