import requests
import time
import json
import serial
from datetime import datetime, timezone, timedelta
from dateutil import parser
from nba_api.live.nba.endpoints import scoreboard
from nba_api.stats.static import players

# Constants
JSON_FILE = "all_shots.json"
SERIAL_PORT = 'COM5'  # Update to your ESP32/Arduino COM port
BAUD_RATE = 9600

# Initialize Serial Connection
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE)
    print(f"Connected to {SERIAL_PORT}")
except Exception as e:
    print(f"Error connecting to serial port: {e}")
    ser = None

# Load player data
def get_player_name(player_id):
    try:
        player_data = players.get_players()
        for player in player_data:
            if str(player_id) == str(player["id"]):
                return player["full_name"]
        return "Unknown Player"
    except Exception as e:
        print(f"Error fetching player name: {e}")
        return "Unknown Player"

def get_active_game_id():
    board = scoreboard.ScoreBoard()
    games = board.games.get_dict()
    now = datetime.now(timezone.utc)
    
    for game in games:
        game_start_time = parser.parse(game["gameTimeUTC"]).replace(tzinfo=timezone.utc)
        game_end_time = game_start_time + timedelta(hours=3)
        
        if game_start_time <= now <= game_end_time and game['gameStatus'] == 2:
            game_info = f"{game['awayTeam']['teamName']} vs. {game['homeTeam']['teamName']}"
            print(f"Active game found: {game_info}")
            return game['gameId']

    return None

# Fetch the current active game ID
GAME_ID = get_active_game_id()
if not GAME_ID:
    raise ValueError("No active NBA game is in progress right now.")

API_URL = f'https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{GAME_ID}.json'

try:
    with open(JSON_FILE, "r") as file:
        all_shots = json.load(file)
except FileNotFoundError:
    all_shots = []

def fetch_all_shots():
    try:
        data = requests.get(API_URL).json()
        new_shots = [
            {
                "playerId": action.get("personId"),
                "playerName": get_player_name(action.get("personId")),
                "clock": action["clock"],
                "x": action["x"],
                "y": action["y"],
                "shotResult": action.get("shotResult"),
                "pointsTotal": action.get("pointsTotal"),
            }
            for action in data["game"]["actions"]
            if action.get("isFieldGoal") == 1
        ]
        return new_shots
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

def send_shot_data(shot):
    if ser:
        try:
            message = f"{shot['x']},{shot['y']},{shot['shotResult']}\n"
            ser.write(message.encode())
            print(f"Sent to ESP32/Arduino: {message}")
        except Exception as e:
            print(f"Error sending data: {e}")

def listen_for_shots():
    global all_shots
    print(f"Listening for shot attempts in game ID {GAME_ID}...")
    while True:
        new_shots = fetch_all_shots()
        for shot in new_shots:
            if shot not in all_shots:
                all_shots.append(shot)
                print(f"New shot detected: {shot}")
                send_shot_data(shot)
        time.sleep(2)

listen_for_shots()
