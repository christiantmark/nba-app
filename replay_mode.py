import time
import requests
import serial
from datetime import datetime

# ---- CONFIG ----
PORT = "COM5"           # Adjust to your Arduino port
BAUD = 9600
MAX_REALISTIC_DELAY = 10  # seconds

# ---- Step 1: Select Game Date ----
def get_nba_games_by_date(date_str):
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
        target_date_str = target_date.strftime("%m/%d/%Y 00:00:00")

        response = requests.get("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json")
        response.raise_for_status()
        data = response.json()

        schedule = data.get("leagueSchedule", {}).get("gameDates", [])
        available_dates = [d["gameDate"] for d in schedule]
        print(f"First few dates in schedule: {available_dates[:5]} ...")

        if target_date_str not in available_dates:
            print(f"No games found for {date_str}. Try one of the above dates.")
            return []

        games_on_date = []
        for day in schedule:
            if day["gameDate"] == target_date_str:
                for game in day.get("games", []):
                    games_on_date.append({
                        "game_id": game["gameId"],
                        "home_team": game["homeTeam"]["teamTricode"],
                        "away_team": game["awayTeam"]["teamTricode"],
                        "game_time_et": game.get("gameEt", "Unknown")
                    })

        return games_on_date

    except Exception as e:
        print(f"Error: {e}")
        return []

# ---- Step 2: Parse ISO Timestamp ----
def parse_time_actual(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00"))

# ---- Step 3: Replay Game ----
def replay_game(game_id):
    # Setup serial
    try:
        arduino = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(2)
    except Exception as e:
        print(f"Error opening serial port: {e}")
        return

    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
    print(f"\nFetching play-by-play from: {url}")
    try:
        resp = requests.get(url)
        data = resp.json()
    except Exception as e:
        print(f"Error fetching or parsing JSON: {e}")
        return

    actions = data.get("game", {}).get("actions", [])
    shots = [
        a for a in actions
        if a.get("actionType") in ["2pt", "3pt"]
        and "x" in a and "y" in a
        and a.get("shotResult") in ["Made", "Missed"]
        and a.get("timeActual")
    ]

    if not shots:
        print("No shot data found in this game.")
        return

    print(f"Found {len(shots)} shot attempts")
    shots.sort(key=lambda a: parse_time_actual(a["timeActual"]))

    prev_time = None
    for shot in shots:
        x = shot["x"]
        y = shot["y"]
        result = shot["shotResult"]
        t_actual_str = shot["timeActual"]
        t_actual = parse_time_actual(t_actual_str)
        player = shot.get("playerName", "Unknown")

        # Delay between shots
        if prev_time is not None:
            delay = (t_actual - prev_time).total_seconds()
            delay = max(0, min(delay, MAX_REALISTIC_DELAY))
            time.sleep(delay)
        prev_time = t_actual

        # Map 0–100 to 32x16 LED grid
        led_x = int((x / 100.0) * 31)
        led_y = int((y / 100.0) * 15)
        color = "G" if result == "Made" else "R"

        message = f"{led_x},{led_y},{color}\n"
        print(f"[{t_actual_str}] x: {x:.2f}, y: {y:.2f}, Result: {result}, Player: {player} -> Sending: {message.strip()}")
        arduino.write(message.encode())

# ---- MAIN ----
if __name__ == "__main__":
    date_input = input("Enter the date (YYYY-MM-DD): ").strip()
    games = get_nba_games_by_date(date_input)

    if not games:
        print("No games found or error occurred.")
        exit(0)

    print(f"\nNBA games on {date_input}:")
    for i, game in enumerate(games):
        print(f"[{i}] Game ID: {game['game_id']} | {game['away_team']} @ {game['home_team']} | Time (ET): {game['game_time_et']}")

    # Prompt for selection
    try:
        choice = int(input("\nSelect a game number to replay (e.g. 0): "))
        selected_game = games[choice]["game_id"]
        print(f"Replaying Game ID: {selected_game} ...")
        replay_game(selected_game)
    except (ValueError, IndexError):
        print("Invalid selection. Exiting.")
