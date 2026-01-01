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
def get_anthropic_client():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        # Also check common local path as a courtesy
        key_path = os.path.expanduser("~/.anthropic/api_key")
        if os.path.exists(key_path):
            with open(key_path, "r") as f:
                api_key = f.read().strip()
    if not api_key:
         raise ValueError("ANTHROPIC_API_KEY not found in environment or ~/.anthropic/api_key")
    return anthropic.Anthropic(api_key=api_key)

class MatchIntent(BaseModel):
    message_type: str = Field(..., description="Type of message: 'match_report' if user is reporting a score, 'query' if asking a question/other.")
    user_name: Optional[str] = Field(None, description="Name of the user/player 1 if mentioned")
    opponent_name: Optional[str] = Field(None, description="Name of the opponent/player 2 played against")
    user_score: Optional[int] = Field(None, description="Score of the user (games won)")
    opponent_score: Optional[int] = Field(None, description="Score of the opponent (games won)")
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
        
        system_prompt = """You are a Table Tennis match assistant.

TASK:
1. CLASSIFY the user's message as 'match_report', 'action', or 'query'.
   - 'match_report': User is explicitly stating a result or score update (e.g., 'Justin vs Alex 3-0', 'I beat Steve 11-9, 11-8', 'Justin 3, Alex 1').
   - 'action': User is giving a command (e.g., 'reset the game', 'finish set', 'send score message', 'save this match', 'log it').
   - 'query': User is asking a question or chatting.

2. EXTRACT:
   - For 'match_report': Extract BOTH player names ('player1_name', 'player2_name'), their scores ('player1_score', 'player2_score'), and optional set scores.
   - For 'action': Set 'action' to 'reset_game', 'finish_set', 'send_message', or 'save_match'.

3. FORMAT: Return VALID JSON ONLY.
{
  "message_type": "match_report" | "action" | "query",
  "player1_name": string | null,
  "player2_name": string | null,
  "player1_score": integer | null,
  "player2_score": integer | null,
  "set_scores": string | null,
  "action": string | null
}"""

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

