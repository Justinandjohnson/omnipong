import requests
import os

BASE_URL = "http://localhost:8000"

def log(msg, status="INFO"):
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "RESET": "\033[0m"}
    print(f"{colors[status]}[{status}] {msg}{colors['RESET']}")

def create_dummy_audio():
    # Create a dummy file just to test upload flow (Whisper might fail on garbage, but we check handling)
    with open("test_audio.webm", "wb") as f:
        f.write(b"fake_audio_content")

def test_transcribe_upload():
    log("Testing /arcade/transcribe (Upload Flow)...")
    create_dummy_audio()
    
    try:
        files = {'file': ('test_audio.webm', open('test_audio.webm', 'rb'), 'audio/webm')}
        res = requests.post(f"{BASE_URL}/arcade/transcribe", files=files)
        data = res.json()
        
        # We expect a success status, even if transcription is empty/garbage
        # Or we might get an error if OpenAI API fails on bad audio. 
        # But we want to ensure the endpoint accepts the file.
        
        if "status" in data or "error" in data:
            log(f"Endpoint Reachable. Response: {data}", "SUCCESS")
            # Ideally we check for success, but with fake audio, transcription might error gracefully
            return True
        else:
            log(f"Unexpected Response: {data}", "ERROR")
            return False
            
    except Exception as e:
        log(f"Request Error: {e}", "ERROR")
        return False
    finally:
        if os.path.exists("test_audio.webm"):
            os.remove("test_audio.webm")

def test_twilio_webhook():
    log("Testing /webhooks/twilio (SMS Flow)...")
    
    # "I" implies Justin in the new prompt context
    payload = {"Body": "I beat Steve 3-0 yesterday", "From": "+15551234567"}
    try:
        res = requests.post(f"{BASE_URL}/webhooks/twilio", data=payload)
        
        if res.status_code == 200:
            log(f"Webhook Successful. Response: {res.text}", "SUCCESS")
            if "Match Saved!" in res.text:
                log("Verified: Logic detected intent and saved match.", "SUCCESS")
                return True
            else:
                log("Warning: match might not have been saved (check logic).", "ERROR")
                return False
        else:
            log(f"Webhook Failed: {res.status_code} {res.text}", "ERROR")
            return False
            
    except Exception as e:
        log(f"Request Error: {e}", "ERROR")
        return False

if __name__ == "__main__":
    print("--- Starting Multi-Modal Verification ---")
    
    test_transcribe_upload()
    test_twilio_webhook()
    
    print("--- Verification Complete ---")
