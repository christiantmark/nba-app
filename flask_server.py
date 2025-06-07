from flask import Flask, jsonify, request
import requests
from datetime import datetime
from threading import Thread, Lock, Event
import time
import logging

app = Flask(__name__)

NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"

shots_cache = []
last_sent_index = -1
lock = Lock()

fetch_thread = None
stop_event = Event()

def parse_time_actual(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00"))

@app.route('/games/<date_str>', methods=['GET'])
def get_games(date_str):
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format, expected YYYY-MM-DD"}), 400

    try:
        resp = requests.get(NBA_SCHEDULE_URL)
        resp.raise_for_status()
        schedule_data = resp.json()
    except Exception as e:
        return jsonify({"error": f"Failed to fetch schedule: {e}"}), 500

    schedule = schedule_data.get("leagueSchedule", {}).get("gameDates", [])
    target_date_str = target_date.strftime("%m/%d/%Y 00:00:00")

    for day in schedule:
        if day.get("gameDate") == target_date_str:
            games = day.get("games", [])
            game_list = [{
                "game_id": g["gameId"],
                "home_team": g["homeTeam"]["teamTricode"],
                "away_team": g["awayTeam"]["teamTricode"],
                "game_time_et": g.get("gameEt", "Unknown")
            } for g in games]
            return jsonify(game_list)

    return jsonify([])

def fetch_shots_loop(game_id):
    global shots_cache, last_sent_index
    last_known_shot_times = set()

    while not stop_event.is_set():
        try:
            url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            actions = data.get("game", {}).get("actions", [])

            new_shots = []
            for a in actions:
                if (
                    a.get("actionType") in ["2pt", "3pt"]
                    and "x" in a and "y" in a
                    and a.get("shotResult") in ["Made", "Missed"]
                    and a.get("timeActual")
                ):
                    t_actual = a["timeActual"]
                    if t_actual in last_known_shot_times:
                        continue  # skip shots we already know about

                    player_name = a.get("playerNameI") or a.get("playerName") or "Unknown"
                    team = a.get("teamTricode", "UNK")
                    x = int(round((a["x"] / 100.0) * 31))
                    y = int(round((a["y"] / 100.0) * 15))
                    new_shots.append({
                        "x": x,
                        "y": y,
                        "result": a.get("shotResult"),
                        "timeActual": t_actual,
                        "player": player_name,
                        "team": team
                    })
                    last_known_shot_times.add(t_actual)

            if new_shots:
                with lock:
                    shots_cache.extend(new_shots)
                    shots_cache.sort(key=lambda s: parse_time_actual(s["timeActual"]))
                # Don't reset last_sent_index here — Arduino client will track which shot to ask next

        except Exception as e:
            print(f"Error fetching shots: {e}")

        time.sleep(5)  # wait before polling again

@app.route('/next_shot', methods=['GET'])
def next_shot():
    global last_sent_index
    with lock:
        if not shots_cache:
            return jsonify({"error": "No shot data cached"}), 404
        if last_sent_index + 1 >= len(shots_cache):
            return jsonify({"message": "No more shots"}), 204
        last_sent_index += 1
        return jsonify(shots_cache[last_sent_index])

def main_interactive():
    global fetch_thread, stop_event, shots_cache, last_sent_index

    print("🏀 NBA Shot Tracker - Select game to watch")

    while True:
        date_str = input("Enter date (YYYY-MM-DD): ").strip()
        if not date_str:
            print("Please enter a valid date.")
            continue

        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print("Invalid date format. Use YYYY-MM-DD.")
            continue

        try:
            resp = requests.get(f"http://127.0.0.1:5000/games/{date_str}")
            resp.raise_for_status()
            games = resp.json()
        except Exception as e:
            print(f"Failed to fetch games: {e}")
            continue

        if not games:
            print(f"No games found for {date_str}. Try another date.")
            continue

        print(f"\nGames on {date_str}:")
        for i, g in enumerate(games):
            print(f" {i+1}. {g['away_team']} at {g['home_team']} - Tipoff: {g['game_time_et']} ET")

        while True:
            choice = input("Select game number to watch (or 'q' to enter another date): ").strip()
            if choice.lower() == 'q':
                break
            if not choice.isdigit() or not (1 <= int(choice) <= len(games)):
                print("Invalid choice. Please enter a valid game number.")
                continue

            selected_game = games[int(choice) - 1]

            print(f"Selected game: {selected_game['away_team']} at {selected_game['home_team']}")
            print("Starting shot fetch loop...")

            # Stop previous fetch thread if running
            if fetch_thread and fetch_thread.is_alive():
                stop_event.set()
                fetch_thread.join()

            stop_event.clear()
            shots_cache = []
            last_sent_index = -1

            fetch_thread = Thread(target=fetch_shots_loop, args=(selected_game["game_id"],), daemon=True)
            fetch_thread.start()

            print("Shots fetching started. You can now run your Arduino client to get shots.")

            print("\nYou can keep selecting games or press Ctrl+C to exit.\n")
            break

def run_flask():
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Suppress Flask info logs

    app.run(debug=False, use_reloader=False, host="0.0.0.0")

if __name__ == "__main__":
    from threading import Thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    time.sleep(1)

    main_interactive()
