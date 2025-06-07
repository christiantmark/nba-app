import requests
import serial
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:5000"
SERIAL_PORT = "COM5"  # Update to your Arduino's port
BAUD_RATE = 115200

LED_WIDTH = 32
LED_HEIGHT = 16
COURT_WIDTH = 94.0
COURT_HEIGHT = 50.0

def map_shot_coordinates(shot, is_home_team):
    period = shot.get('period', 1)
    raw_x = shot['x']
    raw_y = shot['y']

    # Flip x-axis based on which side they're shooting on
    if (is_home_team and period >= 3) or (not is_home_team and period <= 2):
        raw_x = COURT_WIDTH - raw_x

    # Scale to LED grid
    x = int((raw_x / COURT_WIDTH) * (LED_WIDTH - 1))
    y = int((raw_y / COURT_HEIGHT) * (LED_HEIGHT - 1))

    return x, y

def send_shot_to_arduino(ser, shot, is_home_team):
    x, y = map_shot_coordinates(shot, is_home_team)
    result = shot['result']
    msg = f"{x},{y},{result}\n"
    print("Sending:", msg.strip())
    ser.write(msg.encode())

def main():
    date = input("Enter date (YYYY-MM-DD): ").strip()
    response = requests.get(f"{BASE_URL}/games/{date}")
    if response.status_code != 200:
        print("Error fetching games:", response.text)
        return

    games = response.json()
    if not games:
        print("No games found on this date.")
        return

    print(f"\nGames on {date}:")
    for i, g in enumerate(games, 1):
        print(f"{i}: {g['away_team']} @ {g['home_team']} (game ID: {g['game_id']})")

    while True:
        choice = input(f"Select game number (1-{len(games)}): ").strip()
        if choice.isdigit():
            choice_num = int(choice)
            if 1 <= choice_num <= len(games):
                break
        print("Invalid choice, try again.")

    game = games[choice_num - 1]
    game_id = game["game_id"]
    home_team = game["home_team"]
    away_team = game["away_team"]

    shots_resp = requests.get(f"{BASE_URL}/shots/{game_id}")
    if shots_resp.status_code != 200:
        print("Error fetching shots:", shots_resp.text)
        return

    shots = shots_resp.json()
    print(f"\nLoaded {len(shots)} shots for game {game_id}")
    print("Opening serial...")

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Allow Arduino to reset
    except Exception as e:
        print(f"Failed to open serial port: {e}")
        return

    print("Sending shots to Arduino...")

    for shot in shots:
        # TEMP FIX: Team info not in shot dict, so skip home/away logic
        is_home = False  # <- Change this later when 'team' is available

        send_shot_to_arduino(ser, shot, is_home)
        print(f"{shot['timeActual']} - {shot['player']} - {shot['result']} at ({shot['x']:.1f}, {shot['y']:.1f})")
        time.sleep(1.0)
        ser.write(b"clear\n")
        time.sleep(1.0)

    ser.close()
    print("Done.")

if __name__ == "__main__":
    main()
