import os
import json
import asyncio
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

# ponytail: check local credentials file, fall back to env vars
def _get_cred(env_key):
    creds_file = os.path.join(os.path.dirname(__file__), ".credentials.json")
    try:
        with open(creds_file) as f:
            creds = json.load(f)
        key_map = {"OMNIPONG_USER": ("omnipong", "username"), "OMNIPONG_PASS": ("omnipong", "password"),
                    "STADIUM_USER": ("stadium", "username"), "STADIUM_PASS": ("stadium", "password")}
        if env_key in key_map:
            svc, field = key_map[env_key]
            val = creds.get(svc, {}).get(field)
            if val:
                return val
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return os.getenv(env_key)

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
        
        # Block heavy resources for speed
        await self.context.route("**/*", self._route_handler)
        
        return self.context

    async def _route_handler(self, route):
        if route.request.resource_type in ["image", "media", "font"]:
            await route.abort()
        else:
            await route.continue_()

    async def get_page(self):
        if not self.context:
            await self.start()
        return self.context.pages[0] if self.context.pages else await self.context.new_page()

    async def login_omnipong(self):
        page = await self.get_page()
        print("Navigating to OmniPong Member page...")
        await page.goto("https://www.omnipong.com/members.asp?m=21")
        
        # Check if already logged in by looking for Logout link
        if await page.query_selector('a[title="Log Out"]'):
            print("Already logged in to OmniPong")
            return True

        # Check if we are on the login form
        login_btn = await page.query_selector('input[name="Action"][value="Log In"]')
        if not login_btn:
            print("Login button not found - checking if we were redirected to landing page")
            # Sometimes OmniPong redirects if already session is active but slightly different
            if await page.query_selector('a[title="Log Out"]'):
                return True
            # Try to go to login directly
            await page.goto("https://www.omnipong.com/members.asp?m=21")
            login_btn = await page.wait_for_selector('input[name="Action"][value="Log In"]', timeout=5000)

        username = _get_cred("OMNIPONG_USER")
        password = _get_cred("OMNIPONG_PASS")
        
        if not username or not password:
            raise ValueError("OmniPong credentials missing in .env")

        # Smart prefill check as suggested by user
        current_user = await page.input_value('input[name="Login_Id"]')
        current_pass = await page.input_value('input[name="Password"]')

        if not current_user or current_user != username:
            print(f"Filling username: {username}")
            await page.fill('input[name="Login_Id"]', username)
        
        if not current_pass:
            print("Filling password...")
            await page.fill('input[name="Password"]', password)

        print("Clicking Log In...")
        await page.click('input[name="Action"][value="Log In"]')
        
        # Verify login
        try:
            await page.wait_for_selector('a[title="Log Out"]', timeout=10000)
            print("Successfully logged in to OmniPong")
            return True
        except Exception as e:
            print(f"Login verification failed: {e}")
            await page.screenshot(path="omnipong_login_error.png")
            return False

    async def login_stadium(self):
        page = await self.get_page()
        print("Navigating to StadiumCompete login...")
        await page.goto("https://stadiumcompete.com/log-in")
        
        # Check if already logged in
        if "dashboard" in page.url or await page.query_selector('button:has-text("Log Out")'):
             print("Already logged in to StadiumCompete")
             return True

        username = _get_cred("STADIUM_USER")
        password = _get_cred("STADIUM_PASS")
        
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
