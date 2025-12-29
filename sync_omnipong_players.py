import asyncio
import os
import sqlite3
from browser_manager import BrowserManager

DATABASE_PATH = "omnipong.db"

async def sync_players():
    # 1. Connect to DB and get unique players from league matches
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Create players table if not exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        usatt_id TEXT,
        rating INTEGER,
        state TEXT,
        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    
    # Get unique opponent names from stadium_league matches
    cursor.execute("SELECT DISTINCT opponent_name FROM matches WHERE source = 'stadium_league' AND opponent_name IS NOT NULL")
    opponents = [row[0] for row in cursor.fetchall()]
    
    # Also add the user Justin Johnson if he's not there
    if "Justin Johnson" not in opponents:
        opponents.append("Justin Johnson")
    
    print(f"Found {len(opponents)} players to sync.")
    
    manager = BrowserManager()
    try:
        for player in opponents:
            print(f"Syncing {player}...")
            # OmniPong usually expects "Last, First" but sometimes "First Last" works.
            # Most entries in matches are "Last, First"
            try:
                result = await manager.search_omnipong_player(player)
                if result.get("success"):
                    print(f"  Found: USATT# {result['usatt_id']}, Rating: {result['rating']}, State: {result['state']}")
                    # Update players table
                    cursor.execute("""
                    INSERT INTO players (name, usatt_id, rating, state, last_updated)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(name) DO UPDATE SET
                        usatt_id=excluded.usatt_id,
                        rating=excluded.rating,
                        state=excluded.state,
                        last_updated=CURRENT_TIMESTAMP
                    """, (player, result['usatt_id'], result['rating'], result['state']))
                    
                    # Update matches table if opponent_name matches
                    cursor.execute("""
                    UPDATE matches SET opponent_usatt_id = ? 
                    WHERE opponent_name = ? AND source = 'stadium_league'
                    """, (result['usatt_id'], player))
                    
                    conn.commit()
                else:
                    print(f"  Could not find player: {result.get('error')}")
            except Exception as e:
                print(f"  Error syncing {player}: {e}")
                
            # Random delay to avoid being too aggressive
            await asyncio.sleep(2)
            
    finally:
        await manager.stop()
        conn.close()

if __name__ == "__main__":
    asyncio.run(sync_players())
