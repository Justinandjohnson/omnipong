import sqlite3

DATABASE_PATH = "omnipong.db"

def migrate():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(players)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "rating_source" not in columns:
            print("Adding rating_source column to players table...")
            cursor.execute("ALTER TABLE players ADD COLUMN rating_source TEXT DEFAULT 'unknown'")
            conn.commit()
        else:
            print("rating_source column already exists.")
            
    except Exception as e:
        print(f"Migration error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
