"""
Seed script for Rubberr backend testing.
Inserts a test user, match records, tournament records, and rating history
into the same SQLite database used by main.py.

Usage:
    cd <repo>/rubberr/backend && python seed.py

The showcase player identity is configurable via environment variables:
    PLAYER_FULL_NAME (default "Alex Player")
    PLAYER_EMAIL     (default "player@example.com")
"""
import os
import sys
from datetime import date, datetime, timedelta

# Add project root to path so models.py is importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base, User, Match, Activity, RatingHistory

# ---- Database setup (mirrors main.py logic) ----
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(DATABASE_URL)
else:
    DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../omnipong.db"))
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Configurable showcase identity so anyone can seed their own demo (generic defaults).
PLAYER_FULL_NAME = os.getenv("PLAYER_FULL_NAME", "Alex Player")
PLAYER_EMAIL = os.getenv("PLAYER_EMAIL", "player@example.com")


def seed():
    session = SessionLocal()
    try:
        # ---- 1. Check / insert test user ----
        existing_user = session.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
        if existing_user:
            print(f"User already exists (id={existing_user[0]}), skipping user seed.")
            user_id = existing_user[0]
        else:
            user = User(
                name=PLAYER_FULL_NAME,
                email=PLAYER_EMAIL,
                dob=date(1990, 6, 15),
                usatt_id="UST-99001",
                stadium_id="STD-42",
                phone_number="+15125550100",
                current_rating=1500,
                official_rating=1487,
                last_updated=datetime.utcnow(),
            )
            session.add(user)
            session.flush()
            user_id = user.id
            print(f"Inserted test user: {user.name} (id={user_id}, rating={user.current_rating})")

        # ---- 2. Insert 10 realistic match records ----
        existing_matches = session.execute(text("SELECT COUNT(*) FROM matches")).scalar()
        if existing_matches and existing_matches > 0:
            print(f"Matches already exist ({existing_matches} rows), skipping match seed.")
        else:
            match_data = [
                # (days_ago, opponent, opp_rating, result, score_summary, set_scores, source)
                (5,  "Carlos Ortiz",   1540, "Win",  "3-1", "11-9, 9-11, 11-7, 11-6",   "stadium_league"),
                (12, "Brian Nguyen",   1480, "Win",  "3-0", "11-8, 11-5, 11-9",          "stadium_league"),
                (19, "Mark Peters",    1620, "Loss", "1-3", "11-8, 4-11, 8-11, 9-11",    "stadium_league"),
                (26, "Sam Kaur",       1390, "Win",  "3-0", "11-4, 11-6, 11-3",          "stadium_league"),
                (33, "Tony Rivera",    1510, "Win",  "3-2", "11-9, 9-11, 11-8, 8-11, 12-10", "stadium_league"),
                (45, "David Chen",     1550, "Loss", "2-3", "11-9, 11-7, 8-11, 9-11, 7-11", "omnipong"),
                (52, "Raj Patel",      1430, "Win",  "3-1", "11-6, 8-11, 11-5, 11-4",   "omnipong"),
                (60, "Mike Wilson",    1600, "Loss", "0-3", "6-11, 4-11, 7-11",          "omnipong"),
                (68, "Luis Gomez",     1470, "Win",  "3-0", "11-7, 11-9, 11-5",          "omnipong"),
                (75, "Steve Kim",      1520, "Win",  "3-2", "11-9, 10-12, 11-8, 9-11, 11-7", "omnipong"),
            ]

            today = datetime.utcnow()
            for days_ago, opp, opp_rating, result, score_summary, set_scores, source in match_data:
                match_date = today - timedelta(days=days_ago)
                winner_name = PLAYER_FULL_NAME if result == "Win" else opp
                loser_name = opp if result == "Win" else PLAYER_FULL_NAME
                m = Match(
                    date=match_date,
                    winner_name=winner_name,
                    loser_name=loser_name,
                    opponent_name=opp,
                    opponent_rating=opp_rating,
                    score_summary=score_summary,
                    set_scores=set_scores,
                    result=result,
                    source=source,
                    activity_id=None,
                )
                session.add(m)

            print(f"Inserted 10 match records.")

        # ---- 3. Insert 3 tournament records (as Activity rows) ----
        existing_activities = session.execute(
            text("SELECT COUNT(*) FROM activities WHERE activity_type='tournament'")
        ).scalar()
        if existing_activities and existing_activities > 0:
            print(f"Tournament activities already exist ({existing_activities} rows), skipping.")
        else:
            tournaments = [
                Activity(
                    source="omnipong",
                    source_id="omni-t-001",
                    title="Plano Open Spring 2026",
                    date=date(2026, 5, 10),
                    date_range="May 10–11, 2026",
                    location="Plano, TX",
                    city_state="Plano, TX",
                    activity_type="tournament",
                    status="upcoming",
                    url="https://omnipong.com/tournaments/plano-open-spring-2026",
                    contact_name="Alex Torres",
                    contact_email="atorres@planocc.org",
                    contact_phone="+19725550101",
                    flyer_url=None,
                    raw_details="Rating-limited events: U1600, U1800, Open",
                    last_scraped=datetime.utcnow(),
                ),
                Activity(
                    source="omnipong",
                    source_id="omni-t-002",
                    title="Dallas Regional Championship 2026",
                    date=date(2026, 6, 7),
                    date_range="June 7–8, 2026",
                    location="Dallas, TX",
                    city_state="Dallas, TX",
                    activity_type="tournament",
                    status="upcoming",
                    url="https://omnipong.com/tournaments/dallas-regional-2026",
                    contact_name="Susan Lee",
                    contact_email="slee@dallastt.com",
                    contact_phone="+12145550202",
                    flyer_url=None,
                    raw_details="USATT sanctioned. U1600, U2000, Open events.",
                    last_scraped=datetime.utcnow(),
                ),
                Activity(
                    source="stadium",
                    source_id="stad-t-001",
                    title="Richardson Club League Spring Season",
                    date=date(2026, 3, 1),
                    date_range="March–May 2026",
                    location="Richardson, TX",
                    city_state="Richardson, TX",
                    activity_type="tournament",
                    status="current",
                    url="https://stadiumtt.com/leagues/richardson-spring-2026",
                    contact_name="Derek Chan",
                    contact_email="dchan@stadiumtt.com",
                    contact_phone="+19725550303",
                    flyer_url=None,
                    raw_details="Weekly ladder matches. Open to all ratings.",
                    last_scraped=datetime.utcnow(),
                ),
            ]
            for t in tournaments:
                session.add(t)
            print(f"Inserted 3 tournament (activity) records.")

        # ---- 4. Insert rating history ----
        existing_history = session.execute(text("SELECT COUNT(*) FROM rating_history")).scalar()
        if existing_history and existing_history > 0:
            print(f"Rating history already exists ({existing_history} rows), skipping.")
        else:
            history_entries = [
                RatingHistory(date=date(2025, 10, 1),  rating=1450, source="omnipong",        notes="Start of tracking"),
                RatingHistory(date=date(2025, 11, 15), rating=1465, source="omnipong",        notes="After Fall Open"),
                RatingHistory(date=date(2026, 1, 10),  rating=1480, source="omnipong",        notes="January ladder"),
                RatingHistory(date=date(2026, 2, 20),  rating=1487, source="omnipong",        notes="Winter Invitational"),
                RatingHistory(date=date(2026, 3, 5),   rating=1490, source="stadium_league",  notes="Spring league start"),
                RatingHistory(date=date(2026, 3, 19),  rating=1495, source="stadium_league",  notes="Week 3"),
                RatingHistory(date=date(2026, 4, 2),   rating=1500, source="stadium_league",  notes="Week 5 – milestone"),
            ]
            for h in history_entries:
                session.add(h)
            print(f"Inserted 7 rating history records.")

        session.commit()
        print("\nSeed complete. Database is ready for testing.")

    except Exception as e:
        session.rollback()
        print(f"Seed failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
