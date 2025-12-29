# OmniPong Agent: Comprehensive Research & Implementation Plan

This master document contains every detail discovered during the site mapping of `omnipong.com` and `stadiumcompete.com`.

## 1. User & Identity Context
- **Name**: Justin Johnson
- **Email**: justinandjohnson@gmail.com
- **Date of Birth**: 06/03/1993
- **USATT ID**: 1184417
- **Stadium-TT ID**: 10487

---

## 2. USATT Official Player Lookup API

### Data Source for Official Player Statistics
- **URL**: `https://usatt.simplycompete.com/userAccount/s2`
- **Purpose**: Primary resource for retrieving official USATT player baseline information, statistics, and rankings
- **Use Cases**:
    - Retrieve user's USATT# for dashboard display and sync
    - Get official player profile information (name, rating, ranking, tournament history)
    - Manage ranking differences between players
    - Look up opponents' official stats for match preparation
    - Verify player information for tournaments and leagues the user is registered for

### Integration Points
- **Dashboard Sync**: USATT# and profile information should be displayed in the app dashboard
- **Real-time Updates**: Sync official stats to provide accurate ranking comparisons
- **Player Discovery**: Look up any player the user has played against or will play against
- **Tournament Context**: Cross-reference with tournament/league registrations to get opponent data

### Data Fields Available
Based on the USATT player profile, the following information can be retrieved:
- USATT Membership Number (USATT#)
- Player Name
- Current Rating
- National Ranking
- Regional Ranking
- Tournament History
- Match Results
- Membership Status and Expiration

### Implementation Notes
- This URL provides official, authoritative data that should be prioritized over club/league data when available
- Can be used to validate and enhance data from OmniPong and StadiumCompete
- Should be integrated into the Daily Sync Script (see Section 4) for automatic updates

---

## 3. OmniPong Deep Dive Findings

### Authentication & Dashboard
- **URL**: `https://www.omnipong.com/members.asp?m=21`
- **Selectors**:
    - User: `input[name="Login_Id"]`
    - Pass: `input[name="Password"]`
    - Logic: Check if `a[title="Log Out"]` exists to verify session.
- **Member Dashboard**: Displays "Member Home" with summary of USATT expiry and "Upcoming Tournaments for All Regions".

### Global Menu & Sidebar (The Navigation Map)
#### Left Sidebar (Categories):
1. **Activities**:
    - `Entered`: Shows tournaments the user is currently registered for.
    - `Upcoming`: Navigation to site-wide event search.
    - `Finished`: Historical match results and ratings.
2. **Account**:
    - `Profile`: Edit address, contact info, and "Main Club".
    - `Password`: Change credentials.
    - `Family`: Link sub-accounts (manage relatives).
    - `Clubs`: Directory of USATT clubs.
3. **USATT Info**:
    - Status: Current/Expired.
    - Expiration Date.

#### Horizontal Main Menu:
- `Home`: Returns to `members.asp`.
- `Member Access`: Toggle between user views.
- `Director Access`: Link to event management (if authorized).
- `Activities`: Dropdown for `Tournaments`, `Leagues`, `Camps/Classes`, `International`.
- `Other`: Links to USATT, StadiumCompete, etc.

### User Flow Mapping & Selectors
#### A. Activity Search & Filtering
- **URL**: `t-tourney.asp?e=[0|1|2]` (0=Tourney, 1=League, 2=Camps).
- **Time Frame Selector**: `select.date` (Values: `Future`, `Current`, `Past`).
- **Region Search**: Interactive map UI. Selectors use `area` tags or regional links.
- **Action Buttons**:
    - **Enter (Green)**: `input.omnipong_green[value="Enter"]` or link with `Enter` text.
    - **Info (Blue)**: Opens PDF Flyer or details page.
    - **Results**: `input.omnipong_blue[value="See Results"]`.

#### B. Registration Flow (The "Happy Path")
1.  **Entry Click**: Click "Enter" for specific `activity_id`.
2.  **Waiver Page**: Click `input[value="I Accept"]`.
3.  **Event Matrix**: Displays a table of available events (e.g., "Over 40", "U-2000").
    - Selectors: `input[type="checkbox"]` corresponding to labels.
4.  **Acceptance**: Click `input[value="Accept"]`.
5.  **Player Summary**: Final breakdown of fees. Logic: Check for payment buttons/PayPal links.

#### C. Match History & Results Scraper
- **Path**: `members.asp` -> `Finished` -> `View` -> `Results`.
- **Data Table**:
    - Columns: Date, Opponent, USATT #, Score 1, Score 2, Score 3, Score 4, Score 5, Result (W/L).
    - Score Parsing: Scores are integers. Absolute value is points, sign or position denotes winner.

#### D. Global Member Search (Discovery)
- **URL**: `https://www.omnipong.com/Members.asp?M=FE...` (Found via Family -> Add Family).
- **Selectors**:
    - **Name Input**: `input[name="NName"]`
    - **Search Button**: `input.omnipong4`
- **Results Table**: Contains Name, USATT #, Rating, State, and Membership Expiry.

#### E. Coach & Club Scraper (Contacts)
- **Camps/Classes**: `t-tourney.asp?e=2`. Directly lists **Coach Name**, **Email**, and **Phone**.
- **Clubs Directory**: `members.asp` -> `Clubs`.
    - **Club Selector**: `select.club`
    - **Member List**: Once a club is selected, a second `select.club` contains all registered members.
    - **Action**: The agent can iterate through these lists to find tournament directors or update local club rosters.

---

## 4. StadiumCompete Deep Dive Findings

### Authentication
- **URL**: `https://stadiumcompete.com/log-in`
- **Email Selector**: `input[type="email"]`
- **Password Selector**: `input[type="password"]`
- **Action**: `button:has-text("Log In")`

### Navigation Map
- **Dashboard**: `stadiumcompete.com/dashboard`
    - Sections: "My Player Profiles", "Ongoing Tournaments & Leagues".
- **Player Profile**: `/players/tt/{user_id}` (e.g., `/players/tt/10487`).
    - Contains Sparkline of rating history.
    - "Match Search" section for granular history.
- **Global Secondary Nav**: Options for `Events`, `Players`, `Matches`, `Clubs`.

### Action Flows & Visual Logic (StadiumCompete)

#### A. Registration / Entry Flow
1. **Trigger**: Click `button:has-text("Entry Form")`.
2. **Modal Interaction**:
   - **Search**: In "Manage an existing entry", search for "Johnson, Justin".
   - **Verification**: Enter DOB `06/03/1993` in `input[placeholder="MM/DD/YYYY"]`.
   - **Verify**: Click `button:has-text("Verify")`.
3. **Event Selection**:
   - In the "Select Events" section, find the specific date/event (e.g., "December 31, 2025").
   - Click the checkbox `input[type="checkbox"]`.
4. **Final Submission**: Click the blue `button:has-text("Submit Entry")` in the "Review & Submit Entry" panel.

#### B. Score Reporting ("Computer Use")
*This flow is critical for real-time updates.*
1. **Trigger**: Click `button:has-text("Report scores as...")`.
2. **Navigation Fix**: If matches are not immediately visible:
   - Click the **"MATCHES"** tab in the league/tournament sub-navigation.
3. **Filtering**:
   - Use the "FILTER BY EVENT" dropdown if necessary.
   - **Status Filter**: Click the "Status" dropdown and select **"Upcoming"** to find matches needing scores, or **"Completed"** to verify results.
   - **Date Filter**: Ensure the date is set to **Today**. Click the calendar/date picker and select the current date to refresh the list.
4. **Match Identification**:
   - Look for the row containing "Justin Johnson" vs "Opponent Name".
   - Note the opponent's rank (provided in the list).
5. **Action**: Click the specific **"Report scores"** button for that match row.
6. **Input (Update Match Modal)**: 
   - **Identify Rows**: The modal shows two rows. Look for the "YOU" badge or the name "Justin Johnson" to identify the user's row (usually the bottom row). The other row is the opponent.
   - **Enter Scores**: Input the set scores into the respective boxes for each set.
7. **Opponent Verification**: 
   - **Proactive Extraction**: If the user provided the digits in their initial message (e.g., "Won 11-3 against Bob, born in 90"), the agent identifies this and skips the question.
   - **Fallback**: If missing, the agent MUST ask: *"What are the last two digits of [Opponent's Name]'s birth year?"*
   - Enter those two digits into the verification input field (next to the Submit button).
8. **Final Submit**: Click the blue `button:has-text("Submit")`.

---

## 5. Implementation Logic (MCP Tools)

### Shared `BrowserManager`
- Will use a persistent Playwright `BrowserContext` to store cookies for OmniPong and StadiumCompete.
- **Self-Healing**: If a selector fails, it will attempt to find elements by text or relative position.

### Data Model (SQLite)
- `Activities`: Stores both OmniPong (id-based) and StadiumCompete (slug-based) events.
- `Matches`: Unified match history cached locally.
- `Coaches`: Scraped from "Clubs" and "Camps" contact sections.

### Daily Sync Script
1. **Sync USATT Official Data** (via `https://usatt.simplycompete.com/userAccount/s2`):
   - Retrieve user's official USATT# (1184417).
   - Update official rating, national ranking, and regional ranking.
   - Sync tournament history and recent match results.
   - Update membership status and expiration date.
2. Login to OmniPong.
3. Search `Current` and `Future` activities for region 4 (or user-defined).
4. If new entries found that don't match `Activity.id` in DB -> Write to DB and flag as "New".
5. Login to StadiumCompete.
6. Update `User.rating` and `User.matches`.
7. **Cross-reference USATT data** with local league data to identify ranking differences and display both official and club ratings in dashboard.

---

## 9. Data Siloing & Architecture

### Data Source Definitions

The application integrates multiple data sources, each serving a distinct purpose:

1. **Official USATT Data** (`source='omnipong'`):
   - **Source**: OmniPong.com (official USATT partner site)
   - **Scraper**: `omnipong_scraper.py`
   - **Contains**: Official tournament matches, USATT ratings, official match results
   - **Purpose**: Track official USATT career statistics and rating progression
   
2. **Club League Data** (`source='stadium_league'`):
   - **Source**: StadiumCompete.com league pages
   - **Scraper**: `stadium_league_scraper.py`
   - **Contains**: Local club/league matches, league ratings
   - **Purpose**: Track club-level performance and league standings

3. **USATT Player Lookup** (`https://usatt.simplycompete.com/userAccount/s2`):
   - **Purpose**: Official player profile, membership status, current official rating
   - **Integration**: Sync user's USATT# and official stats to dashboard

### Database Schema

- `matches` table: All match records with `source` field to distinguish origin
- `activities` table: Tournaments and leagues with `source` field
- `rating_history` table: Track rating changes over time per source

---

## 6. Master Checklist for Agent Prompting
To instruct the AI, we will use these "Primitive Commands":
- `GOTO omnipong.activities.leagues`
- `FILTER omnipong.timeframe = 'Future'`
- `CLICK omnipong.button.enter WHERE label matches {LEAGUE_NAME}`
- `FILL stadium.report_score WHERE match matches {OPPONENT}`

---

## 7. UX Vision & Interaction Strategy
The agent acts as a proactive "Ping Pong Concierge" with the following behaviors:
- **Proactive Scheduling**: A daily script checks for new activities. If a match is found in the user's region, the agent notifies the user: *"New tournament at ATTC on March 15. Should I sign you up?"*
- **Intelligence**: "What's my record against Bob?" -> Agent queries the local SQLite DB containing scraped match history.
- **Efficient Action**: If the user provides scores and birth year digits in a single text (e.g., "Won 3-0 against Bob (90)"), the agent skips confirmation and executes the registration/reporting immediately.

---

## 8. Implementation Roadmap

### Phase 1: Infrastructure & Data Modeling
- [ ] Initialize Python MCP server and `requirements.txt`.
- [ ] Setup `BrowserManager` with cookies/persistent context.
- [ ] Initialize SQLite schema for `Activities`, `Matches`, and `Contacts`.

### Phase 2: Scrapers & Sync Engine
- [ ] Build USATT Official Player scraper (`usatt.simplycompete.com/userAccount/s2`).
- [ ] Build OmniPong scraper (Regional search + Member Search).
- [ ] Build StadiumCompete scraper (Dashboard + Match History).
- [ ] Implement the "Daily Sync" background process (including USATT data sync).

### Phase 3: Action Tools (Computer Use)
- [ ] Implement `omnipong_register` (Waiver + Event selection).
- [ ] Implement `stadium_report_score` (Matches tab + Update Match modal flow).

### Phase 4: Integration & UX
- [ ] Connect to Google Calendar for event auto-scheduling.
- [ ] Deploy and verify the final MCP server as a Gemini extension.
