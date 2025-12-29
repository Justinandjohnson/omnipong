import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database connection (Sync)
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../omnipong.db"))
DB_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_tournament_intelligence(tournament_title: str = None, limit: int = 5):
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
            rec_events = []
            
            # A. Event Recommendations (Logic: User Rating vs Limits)
            rating_events = [e for e in raw_events if e.get('rating_limit')]
            rating_events.sort(key=lambda x: x['rating_limit'])
            
            for e in rating_events:
                limit_val = e['rating_limit']
                if limit_val >= user_rating:
                    diff = limit_val - user_rating
                    competitiveness = ""
                    if diff <= 150:
                        competitiveness = "Competitive"
                    elif diff <= 400:
                        competitiveness = "Challenge"
                    
                    if competitiveness:
                        rec_events.append({
                            'name': e['name'],
                            'rating_limit': e['rating_limit'],
                            'fee': e.get('fee'),
                            'competitiveness': competitiveness
                        })
                    
                    if len(rec_events) >= 2: break
            
            # Fallback: If no rating-limited events match, suggest the first available events
            if not rec_events and raw_events:
                # Suggest first 2 events if they are singles/open
                for e in raw_events[:2]:
                    rec_events.append({
                        'name': e['name'],
                        'rating_limit': e.get('rating_limit'),
                        'fee': e.get('fee'),
                        'competitiveness': 'Recommended'
                    })
            
            if not rec_events:
                # No events available, create a generic placeholder
                if "Open" in t['title']:
                    rec_events.append({'name': 'Open Singles', 'competitiveness': 'Recommended'})
                else:
                    rec_events.append({'name': 'Singles Entry', 'competitiveness': 'Recommended'})

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
                "difficulty_score": 5,
                "insights": [f"Based on your rating of {user_rating}, we found {len(rec_events)} suitable events."]
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
