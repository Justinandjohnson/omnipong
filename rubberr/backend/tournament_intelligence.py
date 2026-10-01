import os

try:
    # Imported as a package submodule (uvicorn: rubberr.backend.main).
    from .rating_engine import build_tournament_recommendation
except ImportError:
    # Imported as a top-level module via sys.path (daily_check, tests).
    from rating_engine import build_tournament_recommendation

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database connection (Sync)
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../omnipong.db"))
DB_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_tournament_intelligence(tournament_title: str | None = None, limit: int = 5):
    """
    Analyze tournaments to provide AI-enhanced insights:
    - Who typically wins events at tournaments
    - Which events to enter based on skill level
    - Tournament difficulty analysis
    - Players you know who attend
    - Doubles partner suggestions
    """
    session = SessionLocal()
    try:
        # 1. Get User Info
        user_query = text("SELECT current_rating, official_rating FROM users LIMIT 1")
        user_row = session.execute(user_query).fetchone()
        
        # Prefer official rating (USATT) for tournaments, fallback to league rating
        if user_row and user_row.official_rating:
            user_rating = user_row.official_rating
        else:
            user_rating = user_row.current_rating if user_row else 1500
        
        # 2. Get Match History for Opponent Analysis
        matches_query = text("""
            SELECT opponent_name, opponent_rating, result, date, activity_id
            FROM matches 
            WHERE opponent_name IS NOT NULL 
            ORDER BY date DESC
        """)
        matches = [dict(row._mapping) for row in session.execute(matches_query)]
        
        opponents = {}
        for m in matches:
            opp = m['opponent_name']
            if opp not in opponents:
                opponents[opp] = {'wins': 0, 'games': 0, 'rating': m['opponent_rating'], 'last_seen': m['date']}
            opponents[opp]['games'] += 1
            if m['result'] in ['W', 'Win']: 
                opponents[opp]['wins'] += 1

        # 3. Get Upcoming Tournaments
        tournaments_query = text("""
            SELECT id, title, location, date_range, url
            FROM activities 
            WHERE activity_type = 'tournament' 
            AND status = 'upcoming'
        """)
        tournaments = [dict(row._mapping) for row in session.execute(tournaments_query)]
        
        # 4. Get Events for these tournaments
        if not tournaments:
            return {"user_rating": user_rating, "tournaments_analyzed": 0, "recommendations": []}

        t_ids = tuple(t['id'] for t in tournaments)
        if t_ids:
            # Fix for single ID tuple: (1,)
            if len(t_ids) == 1:
                events_query = text(f"SELECT activity_id, name, rating_limit, fee FROM events WHERE activity_id = {t_ids[0]}")
            else:
                events_query = text(f"SELECT activity_id, name, rating_limit, fee FROM events WHERE activity_id IN {t_ids}")
            events = [dict(row._mapping) for row in session.execute(events_query)]
        else:
            events = []
            
        # Group events by tournament
        t_events = {}
        for e in events:
            if e['activity_id'] not in t_events: t_events[e['activity_id']] = []
            t_events[e['activity_id']].append(e)

        recommendations = []

        for t in tournaments:
            if tournament_title and tournament_title.lower() not in t['title'].lower():
                continue

            raw_events = t_events.get(t['id'], [])

            # A. Event Recommendations — score every event with the USATT
            # rating engine (expected rating points * win probability), biased
            # toward playing up modestly. See rating_engine.py.
            rec = build_tournament_recommendation(t, raw_events, user_rating, top_n=2)
            rec_events = rec["recommended_events"]

            if not rec_events:
                # No events scraped yet — show a generic entry so the UI still
                # has something to show.
                generic = "Open Singles" if "Open" in t['title'] else "Singles Entry"
                rec_events = [{
                    'name': generic,
                    'rating_limit': None,
                    'fee': None,
                    'competitiveness': 'Recommended',
                    'recommended': False,
                    'reason': 'Events not published yet.',
                }]

            # Difficulty: how far the recommended field sits above the player.
            if rec["recommended_events"]:
                fields = [e["estimated_field_rating"] for e in rec["recommended_events"]]
                avg_field = sum(fields) / len(fields)
                difficulty = max(1, min(10, round(5 + (avg_field - user_rating) / 200)))
            else:
                difficulty = 5

            # B. Known Opponents
            likely_players = []
            for name, data in opponents.items():
                if data['games'] >= 3:
                     likely_players.append({
                         'name': name, 
                         'your_record': f"{data['wins']}-{data['games'] - data['wins']}",
                         'rating': data['rating']
                     })
            likely_players = sorted(likely_players, key=lambda x: x['rating'] if x['rating'] else 0, reverse=True)[:3]

            # C. Doubles Partners
            doubles = []
            for name, data in opponents.items():
                if data['rating'] and abs(data['rating'] - user_rating) < 250:
                     doubles.append({'name': name, 'rating': data['rating']})
            doubles = doubles[:3]

            recommendations.append({
                "tournament": t['title'],
                "recommended_events": rec_events,
                "known_players_likely_attending": likely_players,
                "doubles_partner_suggestions": doubles,
                "difficulty_score": difficulty,
                "recommended": rec["recommended"],
                "expected_rating_change": rec["expected_rating_change"],
                "priority_score": rec["priority_score"],
                "reason": rec["reason"],
                "insights": [
                    rec["reason"],
                    f"Based on your rating of {user_rating}, we found "
                    f"{len(rec_events)} suitable events.",
                ],
            })

        return {
            "user_rating": user_rating,
            "tournaments_analyzed": len(tournaments),
            "recommendations": recommendations
        }
    except Exception as e:
        print(f"Error in tournament intelligence: {e}")
        return {"error": str(e)}
    finally:
        session.close()
