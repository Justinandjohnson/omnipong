import os
import sys
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Ensure we can import models
sys.path.append(os.getcwd())
try:
    from models import Base, User, Activity, Event, Match, Contact, RatingHistory, Player, Notification
except ImportError:
    print("Error: Could not import models. Make sure you are running this from the project root.")
    sys.path.append(os.path.join(os.getcwd(), 'rubberr', 'backend'))
    from models import Base, User, Activity, Event, Match, Contact, RatingHistory, Player, Notification

# Load Environment Variables
load_dotenv()

# Configuration
LOCAL_DB_URL = "sqlite:///omnipong.db"
CLOUD_DB_URL = os.getenv("DATABASE_URL")

if not CLOUD_DB_URL:
    print("Error: DATABASE_URL not found in .env files")
    sys.exit(1)

# Fix Render URL for SQLAlchemy
if CLOUD_DB_URL.startswith("postgres://"):
    CLOUD_DB_URL = CLOUD_DB_URL.replace("postgres://", "postgresql://", 1)

print(f"--- Migration Tool ---")
print(f"Source: {LOCAL_DB_URL}")
print(f"Target: Cloud DB (Postgres)")

def migrate():
    # 1. Connect to Local DB
    local_engine = create_engine(LOCAL_DB_URL)
    LocalSession = sessionmaker(bind=local_engine)
    local_session = LocalSession()

    # 2. Connect to Cloud DB
    cloud_engine = create_engine(CLOUD_DB_URL)
    CloudSession = sessionmaker(bind=cloud_engine)
    cloud_session = CloudSession()

    # Ensure Tables Exist in Cloud
    print("Ensuring cloud schema references...")
    Base.metadata.create_all(cloud_engine)

    # Tables to Migrate (Order matters for Foreign Keys)
    # Users -> Activities -> Events -> Matches -> RatingHistory, Players, Notifications
    
    # 3. Migrate Users
    print("\nMigrating Users...")
    users = local_session.query(User).all()
    for row in users:
        exists = cloud_session.query(User).filter_by(email=row.email).first()
        if not exists:
            # Create new instance to detach from local session
            new_row = User(
                name=row.name, email=row.email, dob=row.dob, 
                usatt_id=row.usatt_id, stadium_id=row.stadium_id,
                current_rating=row.current_rating, official_rating=row.official_rating,
                last_updated=row.last_updated
            )
            cloud_session.add(new_row)
            print(f"  + Added User: {row.name}")
        else:
            print(f"  . User exists: {row.name}")
    
    # 4. Migrate Activities & Events (Complex dependencies, skipping for now if mostly scraped?)
    # Users might want them. Let's do it.
    print("\nMigrating Activities...")
    activities = local_session.query(Activity).all()
    activity_map = {} # Old ID -> New ID
    
    for row in activities:
        exists = cloud_session.query(Activity).filter_by(title=row.title, date=row.date).first()
        if not exists:
            new_row = Activity(
                source=row.source, source_id=row.source_id, title=row.title, date=row.date,
                date_range=row.date_range, location=row.location, city_state=row.city_state,
                activity_type=row.activity_type, status=row.status, url=row.url,
                contact_name=row.contact_name, contact_email=row.contact_email, contact_phone=row.contact_phone,
                flyer_url=row.flyer_url, raw_details=row.raw_details, last_scraped=row.last_scraped
            )
            cloud_session.add(new_row)
            cloud_session.flush() # Get new ID
            activity_map[row.id] = new_row.id
            print(f"  + Added Activity: {row.title}")
        else:
            activity_map[row.id] = exists.id
            # print(f"  . Activity exists: {row.title}")

    # 5. Migrate Matches (Crucial for Arcade)
    print("\nMigrating Matches...")
    matches = local_session.query(Match).all()
    for row in matches:
        # Check uniqueness carefully. For arcade, source + date + score + opponent might be unique enough?
        # Or just blindly copy if source='arcade'
        
        # Simple check: same date, same opponent, same result
        exists = cloud_session.query(Match).filter_by(
            date=row.date, opponent_name=row.opponent_name, score_summary=row.score_summary, source=row.source
        ).first()
        
        if not exists:
             # Fix Activity ID mapping if present
            new_act_id = None
            if row.activity_id and row.activity_id in activity_map:
                new_act_id = activity_map[row.activity_id]

            new_row = Match(
                activity_id=new_act_id,
                date=row.date, winner_name=row.winner_name, loser_name=row.loser_name,
                opponent_name=row.opponent_name, opponent_usatt_id=row.opponent_usatt_id,
                opponent_rating=row.opponent_rating, score_summary=row.score_summary,
                set_scores=row.set_scores, result=row.result, source=row.source
            )
            cloud_session.add(new_row)
            print(f"  + Added Match: vs {row.opponent_name} ({row.source})")

    # 6. Migrate Players
    print("\nMigrating Players...")
    players = local_session.query(Player).all()
    for row in players:
        exists = cloud_session.query(Player).filter_by(name=row.name).first()
        if not exists:
            new_row = Player(
                name=row.name, usatt_id=row.usatt_id, rating=row.rating,
                state=row.state, rating_source=row.rating_source, last_updated=row.last_updated
            )
            cloud_session.add(new_row)
            print(f"  + Added Player: {row.name}")

    # 7. Migrate RatingHistory
    print("\nMigrating Rating History...")
    history = local_session.query(RatingHistory).all()
    for row in history:
        exists = cloud_session.query(RatingHistory).filter_by(date=row.date, source=row.source, rating=row.rating).first()
        if not exists:
             new_row = RatingHistory(
                date=row.date, rating=row.rating, source=row.source,
                notes=row.notes
                # match_id currently ignored as it's hard to map back without complexity, usually fine for history graph
            )
             cloud_session.add(new_row)
             print(f"  + Added History: {row.rating} ({row.date})")

    print("\nCommitting changes to Cloud DB...")
    try:
        cloud_session.commit()
        print("SUCCESS! Migration complete.")
    except Exception as e:
        cloud_session.rollback()
        print(f"ERROR: Commit failed: {e}")
    finally:
        local_session.close()
        cloud_session.close()

if __name__ == "__main__":
    confirm = input("Are you sure you want to migrate local data to the production database defined in .env? (y/n): ")
    if confirm.lower() == 'y':
        migrate()
    else:
        print("Migration cancelled.")
