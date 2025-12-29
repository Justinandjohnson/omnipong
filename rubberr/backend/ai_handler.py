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

class MatchIntent(BaseModel):
    opponent_name: Optional[str] = Field(None, description="Name of the opponent played against")
    user_score: Optional[int] = Field(None, description="Score of the user (games won)")
    opponent_score: Optional[int] = Field(None, description="Score of the opponent (games won)")
    set_scores: Optional[str] = Field(None, description="Detailed set scores, e.g., '11-9, 5-11'")
    match_date: Optional[str] = Field(None, description="Date of match if mentioned, else None")
    
class AIResponse(BaseModel):
    intent: MatchIntent
    confirmation_message: str = Field(..., description="A natural language response confirming what was understood or asking for missing info.")
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
    Parses natural language text to extract match details using GPT-4o.
    """
    try:
        client = get_client()
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a Table Tennis match assistant for a user named 'Justin'. Extract match details from the input. \n- If the user says 'I', 'me', or 'Justin', that is the user_score.\n- Extract 'opponent_name', 'user_score', 'opponent_score', and 'set_scores' (e.g. '11-9, 5-11').\n- Provide JSON output.\n- Be consistent: If user won, user_score > opponent_score."},
                {"role": "user", "content": text}
            ],
            response_format={ "type": "json_object" }, # Using generic JSON mode if strict schema issues arise, but let's try strict schema via function calling or just structured output helper if available in this lib version.
            # Simplified for wide compatibility:
            functions=[{
                "name": "extract_match_info",
                "description": "Extracts match data from text",
                "parameters": MatchIntent.model_json_schema()
            }],
            function_call={"name": "extract_match_info"} 
        )
        
        # Parse arguments
        function_args = json.loads(completion.choices[0].message.function_call.arguments)
        
        # Generate confirmation logic (simple rule based for now, or could ask LLM again)
        missing = []
        if not function_args.get('opponent_name'): missing.append("opponent_name")
        if function_args.get('user_score') is None: missing.append("scores")
        
        if not missing:
            msg = f"Got it. You played {function_args['opponent_name']} and the score was {function_args.get('user_score')}-{function_args.get('opponent_score')}."
        else:
            msg = f"I understood you played, but I'm missing details: {', '.join(missing)}."

        return {
            "intent": function_args,
            "confirmation_message": msg,
            "missing_info": missing
        }

    except Exception as e:
        print(f"Intent Parsing Error: {e}")
        raise e

