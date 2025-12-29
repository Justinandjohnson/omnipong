import os
import asyncio
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

class BrowserManager:
    def __init__(self, user_data_dir="./playwright_data"):
        self.user_data_dir = user_data_dir
        self.browser = None
        self.context = None
        self.pw = None

    async def start(self, headless=True):
        self.pw = await async_playwright().start()
        self.context = await self.pw.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=headless,
            viewport={'width': 1280, 'height': 720}
        )
        return self.context

    async def get_page(self):
        if not self.context:
            await self.start()
        return self.context.pages[0] if self.context.pages else await self.context.new_page()

    async def login_omnipong(self):
        page = await self.get_page()
        await page.goto("https://www.omnipong.com/members.asp?m=21")
        
        # Check if already logged in
        if await page.query_selector('a[title="Log Out"]'):
            print("Already logged in to OmniPong")
            return True

        username = os.getenv("OMNIPONG_USER")
        password = os.getenv("OMNIPONG_PASS")
        
        if not username or not password:
            raise ValueError("OmniPong credentials missing in .env")

        await page.fill('input[name="Login_Id"]', username)
        await page.fill('input[name="Password"]', password)
        await page.click('input[name="Action"][value="Log In"]')
        
        # Verify login
        await page.wait_for_selector('a[title="Log Out"]', timeout=10000)
        print("Successfully logged in to OmniPong")
        return True

    async def login_stadium(self):
        page = await self.get_page()
        print("Navigating to StadiumCompete login...")
        await page.goto("https://stadiumcompete.com/log-in")
        
        # Check if already logged in
        if "dashboard" in page.url or await page.query_selector('button:has-text("Log Out")'):
             print("Already logged in to StadiumCompete")
             return True

        username = os.getenv("STADIUM_USER")
        password = os.getenv("STADIUM_PASS")
        
        if not username or not password:
            raise ValueError("StadiumCompete credentials missing in .env")

        print(f"Filling credentials for {username}...")
        await page.fill('input[type="email"]', username)
        await page.fill('input[type="password"]', password)
        await page.click('button:has-text("Log In")')
        
        print("Waiting for dashboard redirect...")
        try:
            await page.wait_for_url("**/dashboard", timeout=20000)
            await page.wait_for_load_state("networkidle")
            print("Successfully logged in to StadiumCompete")
            return True
        except Exception as e:
            print(f"Login timeout or redirect failed: {e}")
            # Take a screenshot for debugging
            await page.screenshot(path="stadium_login_error.png")
            return False

    async def sync_user_rating(self):
        page = await self.get_page()
        print("Syncing user rating from StadiumCompete...")
        await page.goto("https://stadiumcompete.com/dashboard")
        await page.wait_for_load_state("domcontentloaded")
        
        rating_text = await page.evaluate("""
            () => {
                const sidebar = document.querySelector('aside') || document.body;
                const text = sidebar.innerText;
                const match = text.match(/STADIUM Rating:\\s*(\\d+)/i);
                return match ? match[1] : null;
            }
        """)
        
        if rating_text:
            print(f"Captured STADIUM Rating: {rating_text}")
            from models import User
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            from sqlalchemy.orm import sessionmaker
            from sqlalchemy import select
            
            DATABASE_URL = "sqlite+aiosqlite:///./omnipong.db"
            engine = create_async_engine(DATABASE_URL)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session() as session:
                username = os.getenv("STADIUM_USER")
                stmt = select(User).where(User.username == username)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    user = User(username=username)
                    session.add(user)
                
                user.rating = int(rating_text)
                user.last_rating_sync = datetime.utcnow()
                await session.commit()
                print("Rating saved to database.")
            return int(rating_text)
        else:
            print("Failed to capture rating from dashboard.")
            return None

    async def search_omnipong_player(self, player_name: str):
        """Search for a player on OmniPong and return their rating/USATT ID."""
        page = await self.get_page()
        await self.login_omnipong()
        
        print(f"Navigating to Family search on OmniPong...")
        # Go to Home first
        await page.goto("https://www.omnipong.com/members.asp?m=21")
        
        # Click 'Family' in sidebar
        await page.wait_for_selector('input[value="Family"]', timeout=10000)
        await page.click('input[value="Family"]')
        await page.wait_for_load_state("networkidle")
        
        # Click 'Add Family'
        await page.wait_for_selector('input[value="Add Family"]', timeout=10000)
        await page.click('input[value="Add Family"]')
        await page.wait_for_load_state("networkidle")
        
        print(f"Searching for player: {player_name}")
        search_input = 'input:not([type="hidden"]):not([class])'
        await page.wait_for_selector(search_input, timeout=10000)
        await page.fill(search_input, player_name)
        await page.click('input.omnipong4[value="Search"]')
        
        await page.wait_for_timeout(3000)
        
        data = await page.evaluate("""
            () => {
                const rows = Array.from(document.querySelectorAll('tr'));
                for (let i = 0; i < rows.length; i++) {
                    const cells = Array.from(rows[i].cells).map(c => c.innerText.trim());
                    if (cells.length >= 5) {
                        const name = cells[0];
                        const usatt_id = cells[2];
                        const rating = cells[3];
                        const state = cells[4];
                        
                        // Check if USATT ID and Rating are mostly numeric
                        const isNumeric = (str) => /^\d+$/.test(str);
                        
                        if (isNumeric(usatt_id) || isNumeric(rating)) {
                            return {
                                name: name,
                                usatt_id: usatt_id,
                                rating: rating,
                                state: state,
                                success: true
                            };
                        }
                    }
                }
                return { success: false, error: "No player found with valid data" };
            }
        """)
        return data

    async def stop(self):
        if self.context:
            await self.context.close()
        if self.pw:
            await self.pw.stop()

async def test_manager():
    manager = BrowserManager()
    try:
        await manager.login_omnipong()
        await manager.login_stadium()
    finally:
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(test_manager())
