import asyncio
from browser_manager import BrowserManager

async def debug_regional():
    manager = BrowserManager()
    try:
        page = await manager.get_page()
        url = "https://www.omnipong.com/T-tourney.asp?t=8&Region=8&y=&k=&e=0"
        print(f"Navigating to {url}...")
        await page.goto(url)
        await page.wait_for_load_state("domcontentloaded")
        
        # Capture raw HTML
        content = await page.content()
        with open("regional_dump.html", "w") as f:
            f.write(content)
            
        print("Raw HTML dumped to regional_dump.html")
        
        # Check links
        links = await page.evaluate("""() => Array.from(document.querySelectorAll('a')).map(a => ({t: a.innerText, h: a.href}))""")
        print(f"Found {len(links)} links. First 10:")
        for l in links[:10]:
            print(f" - {l['t']} -> {l['h']}")
            
    finally:
        await manager.stop()

if __name__ == "__main__":
    asyncio.run(debug_regional())
