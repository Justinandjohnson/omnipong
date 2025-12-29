import requests
import json
import time

BASE_URL = "http://localhost:8001"

def log(msg, status="INFO"):
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "RESET": "\033[0m"}
    print(f"{colors[status]}[{status}] {msg}{colors['RESET']}")

def test_arcade_submit():
    log("Testing /arcade/submit_score...")
    
    payload = {
        "opponent_name": "Test Rival",
        "manual_score": "I won 3-1 (11-9, 9-11, 11-5, 12-10)",
        "date": "2025-05-20"
    }
    
    try:
        res = requests.post(f"{BASE_URL}/arcade/submit_score", json=payload)
        data = res.json()
        
        if data.get("status") == "success":
            log(f"Submission Successful: {data['summary']}", "SUCCESS")
            return True
        else:
            log(f"Submission Failed: {data}", "ERROR")
            return False
            
    except Exception as e:
        log(f"Request Error: {e}", "ERROR")
        return False

def test_stats_update():
    log("Testing /stats?source=arcade...")
    
    try:
        res = requests.get(f"{BASE_URL}/stats?source=arcade")
        data = res.json()
        
        if "win_rate" in data:
            log(f"Stats Retrieved: {data['wins']}W - {data['losses']}L", "SUCCESS")
            if data['wins'] > 0:
                log("Arcade stats correctly reflect recent win", "SUCCESS")
                return True
            else:
                log("Arcade stats do NOT show win. Is result 'Win'?", "ERROR")
        else:
            log(f"Stats Error: {data}", "ERROR")
            return False
            
    except Exception as e:
        log(f"Request Error: {e}", "ERROR")
        return False

def test_player_lookup():
    log("Testing /arcade/lookup_player...")
    
    # User we just played
    payload = {"name": "Test Rival"}
    
    try:
        res = requests.post(f"{BASE_URL}/arcade/lookup_player", json=payload)
        data = res.json()
        
        if data.get("status") in ["found", "new"]:
            p = data['player']
            log(f"Player Lookup Successful: {p['name']} (Rating: {p['rating']})", "SUCCESS")
            return True
        else:
            log(f"Player Lookup Failed: {data}", "ERROR")
            return False
            
    except Exception as e:
        log(f"Request Error: {e}", "ERROR")
        return False

if __name__ == "__main__":
    print("--- Starting Arcade Backend Verification ---")
    
    if test_arcade_submit():
        time.sleep(1) # Let DB commit if async (though it's sync in main.py)
        test_stats_update()
        test_player_lookup()
    
    print("--- Verification Complete ---")
