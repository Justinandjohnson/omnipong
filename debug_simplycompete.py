import asyncio
import os
from playwright.async_api import async_playwright

async def capture_debug():
    async with async_playwright() as p:
        user_data_dir = "./playwright_data"
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True
        )
        page = await context.new_page()
        print("Navigating to SimplyCompete login for debugging...")
        try:
            await page.goto("https://usatt.simplycompete.com/login/auth", timeout=60000)
            await page.wait_for_timeout(5000)
            print(f"URL: {page.url}")
            await page.screenshot(path="simplycompete_debug.png")
            print("Screenshot saved to simplycompete_debug.png")
            
            # Check for Cloudflare text
            content = await page.content()
            if "Cloudflare" in content:
                print("Cloudflare detected in HTML content.")
            
            # Check for login inputs
            if await page.query_selector('input[name="username"]'):
                print("Login inputs found.")
            else:
                print("Login inputs NOT found.")
                
        except Exception as e:
            print(f"Error: {e}")
            await page.screenshot(path="simplycompete_error.png")
        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(capture_debug())
