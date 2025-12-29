import asyncio
import os
from browser_manager import BrowserManager
from omnipong_scraper import OmniPongScraper
from dotenv import load_dotenv

load_dotenv()

async def test_signup_dry_run():
    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    try:
        # 1. Login
        print("Logging in...")
        await manager.login_omnipong()
        
        # 2. Test tournament (Using one from the screenshots)
        tournament_title = "SATTC Butterfly New Year Tournament"
        recommended_events = ["Under 2300 RR"]
        
        print(f"Testing signup flow for: {tournament_title}")
        page = await manager.get_page()
        
        # Navigate to tournament list
        await page.goto("https://www.omnipong.com/t-tourney.asp?e=0")
        await page.wait_for_load_state("networkidle")
        
        # Find Enter button
        print(f"Searching for 'Enter' for {tournament_title}...")
        enter_btn_found = await page.evaluate(f"""
            () => {{
                const targetTitle = "{tournament_title}".toLowerCase();
                const rows = Array.from(document.querySelectorAll('tr'));
                for (const row of rows) {{
                    const text = row.innerText.toLowerCase();
                    if (text.includes(targetTitle) && text.includes('texas')) {{
                        const enterBtn = row.querySelector('input[value="Enter"]');
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
            print("Tournament 'Enter' button not found. Checking if already entered...")
            if await page.query_selector('text="Summary of Tournament Entries"'):
                 print("Already on tournament summary page.")
            else:
                 await page.screenshot(path="signup_verification_failure_list.png")
                 print("Tournament not found. Captured screenshot.")
            return

        # Wait for 'I Accept' or 'Summary'
        print("Waiting for next page...")
        try:
            # Replaced single selector with choice
            await page.wait_for_function("""
                () => document.querySelector('input[value="I Accept"]') || 
                      document.body.innerText.includes('Please select the events you wish to play') ||
                      document.body.innerText.includes('Summary of Tournament Entries')
            """, timeout=15000)
            
            if await page.query_selector('input[value="I Accept"]'):
                print("Reached 'I Accept' page successfully.")
                await page.click('input[value="I Accept"]')
                await page.wait_for_load_state("networkidle")
            else:
                print("Skipped 'I Accept' page (already accepted or entered).")
                
        except Exception as e:
            print(f"Error finding next page: {e}")
            await page.screenshot(path="signup_verification_failure_after_click.png")
            return
        
        # Verify Events page
        print("Verifying Events page...")
        if await page.query_selector('text="Please select the events you wish to play"'):
            print("Successfully reached Events page.")
            
            # Check for event button
            for event in recommended_events:
                btn_found = await page.evaluate(f"""
                    () => {{
                        const targetEvent = "{event}".toLowerCase();
                        const rows = Array.from(document.querySelectorAll('tr'));
                        for (const row of rows) {{
                            if (row.innerText.toLowerCase().includes(targetEvent)) {{
                                const btn = row.querySelector('input[value="Enter"]');
                                return !!btn;
                            }}
                        }}
                        return false;
                    }}
                """)
                if btn_found:
                    print(f"Verified 'Enter' button for event: {event}")
                else:
                    print(f"Could NOT find 'Enter' button for event: {event}")
        else:
            print("Failed to reach Events page.")

        print("Dry-run verification complete.")

    except Exception as e:
        print(f"Verification Failed: {e}")
    finally:
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(test_signup_dry_run())
