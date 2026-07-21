import os
import json
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Optional, List

# Helper to get client
def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment")
    return OpenAI(api_key=api_key)

import anthropic

# Configurable player identity so anyone can run this — default is generic.
PLAYER_NAME = os.getenv("PLAYER_NAME", "the player")

def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment")
    return anthropic.Anthropic(api_key=api_key)

class MatchIntent(BaseModel):
    message_type: str = Field(..., description="Type of message: 'match_report' if user is reporting a score, 'query' if asking a question/other.")
    player1_name: Optional[str] = Field(None, description="Name of player 1 (usually the user/player)")
    player2_name: Optional[str] = Field(None, description="Name of player 2 (opponent)")
    player1_score: Optional[int] = Field(None, description="Score of player 1 (the user/player)")
    player2_score: Optional[int] = Field(None, description="Score of player 2 (opponent)")
    set_scores: Optional[str] = Field(None, description="Detailed set scores, e.g., '11-9, 5-11'")
    match_date: Optional[str] = Field(None, description="Date of match if mentioned, else None")
    action: Optional[str] = Field(None, description="Action to perform: 'reset_game', 'finish_set', 'send_message', 'save_match', or null")
    
class AIResponse(BaseModel):
    intent: MatchIntent
    confirmation_message: str = Field(..., description="A natural language response confirming match details OR answering the query if simple.")
    missing_info: List[str] = Field(..., description="List of fields that are missing to complete the record (e.g. ['opponent_name'])")

async def transcribe_audio(file_path: str) -> str:
    """
    Transcribes audio file using OpenAI Whisper.
    """
    try:
        client = get_client()
        with open(file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        return transcription.text
    except Exception as e:
        print(f"Transcription Error: {e}")
        raise e

async def parse_match_intent(text: str) -> dict:
    """
    Parses natural language text to extract match details using Claude.
    """
    try:
        client = get_anthropic_client()
        
        system_prompt = """You are an expert Table Tennis match assistant with deep knowledge of scoring rules.

IDENTITY: The user of this app is Justin.

TABLE TENNIS RULES:
- A SET (individual game) is won by first to 11 points, must win by 2+ (e.g., 11-7, 12-10, 15-13)
- DEUCE: At 10-10, play continues until one player leads by 2 (e.g., 11-10 is INVALID, 12-10 is valid, 15-13 is valid)
- A MATCH is best-of-5 sets: first player to win 3 sets wins the match (3-0, 3-1, or 3-2)
- SET SCORES are typically 11-9, 11-7, 12-10, etc. (individual game points)
- MATCH SCORES are like 3-0, 3-1, 3-2 (number of sets won)
- Maximum possible match score is 3-2 (five sets played, one player wins 3)

VALID SET EXAMPLES:
- ✅ 11-9, 11-7, 11-0, 12-10, 13-11, 15-13, 21-19 (all valid: ≥11 and win by 2+)
- ❌ 11-10, 10-9, 13-12 (invalid: not winning by 2+)
- ❌ 10-8, 9-7 (invalid: winner has <11 points)

SCORING INTELLIGENCE:
- "11-9" or "Justin 11, Alex 9" = SET score (one game just finished)
- "3-1" or "I won 3-1" = MATCH score (sets won: player won 3 sets, opponent won 1 set)
- "I beat Steve 11-9, 11-8, 9-11, 11-7" = Multiple sets with final match result (player won 3-1)
- "Justin vs Alex" or "Justin 3, Alex 1" = Player names with match/set scores
- "12-10" = Deuce set (went beyond 11, still valid if win by 2)
- "Fifteen thirteen" or "15-13" = Long deuce set (still valid)

USER IDENTIFICATION:
- If the user says "I", "me", "my", or doesn't mention their own name while reporting a score (e.g., "Beat Alex 11-7"), assume player1_name is "Justin".
- Always prioritize "Justin" as player1_name unless they are explicitly reporting a match between two other people.

TASK:
1. CLASSIFY the user's message as 'match_report', 'action', or 'query'.
   - 'match_report': User is reporting a score (set or match result)
   - 'action': User gives a command ('reset game', 'finish set', 'save match')
   - 'query': User asks a question

2. EXTRACT for 'match_report':
   - player1_name: Name of the first player (often "Justin")
   - player2_name: Name of the second player/opponent
   - player1_score: Player 1's score (points in a SET, or sets won in MATCH)
   - player2_score: Player 2's score (points in a SET, or sets won in MATCH)
   - set_scores: Detailed set-by-set scores if mentioned (e.g., "11-9, 11-8, 9-11")

3. EXTRACT for 'action':
   - action: 'reset_game', 'finish_set', 'send_message', or 'save_match'

4. FORMAT: Return VALID JSON ONLY.
{
  "message_type": "match_report" | "action" | "query",
  "player1_name": string | null,
  "player2_name": string | null,
  "player1_score": integer | null,
  "player2_score": integer | null,
  "set_scores": string | null,
  "action": string | null
}

EXAMPLES:
- "11-7" → {"message_type": "match_report", "player1_name": "Justin", "player1_score": 11, "player2_score": 7, ...}
- "Justin beat Alex 3-1" → {"message_type": "match_report", "player1_name": "Justin", "player2_name": "Alex", "player1_score": 3, "player2_score": 1, ...}
- "I won 11-9" → {"message_type": "match_report", "player1_name": "Justin", "player1_score": 11, "player2_score": 9, ...}"""

        # Use the configured player name instead of the hardcoded default.
        system_prompt = system_prompt.replace("Justin", PLAYER_NAME)

        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": text}
            ]
        )
        
        # Extract JSON from Claude's response
        import re
        content = response.content[0].text
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            function_args = json.loads(json_match.group(0))
        else:
            raise ValueError("Cloud did not return valid JSON")
        
        # Generate confirmation logic
        msg = ""
        missing = []
        message_type = function_args.get('message_type')

        if message_type == 'match_report':
            if not function_args.get('player1_name'): missing.append("player1_name")
            if not function_args.get('player2_name'): missing.append("player2_name")
            if function_args.get('player1_score') is None: missing.append("scores")

            if not missing:
                p1 = function_args.get('player1_name')
                p2 = function_args.get('player2_name')
                s1 = function_args.get('player1_score')
                s2 = function_args.get('player2_score')
                msg = f"Got it. {p1} vs {p2}, score {s1}-{s2}."
            else:
                msg = f"I understood you're reporting a match, but I'm missing: {', '.join(missing)}."
        else:
            # For queries, we don't need missing info checks for match data
            msg = "Processing query..."

        return {
            "intent": function_args,
            "confirmation_message": msg,
            "missing_info": missing
        }

    except Exception as e:
        print(f"Intent Parsing Error: {e}")
        raise e

