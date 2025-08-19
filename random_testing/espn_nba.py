from flask import Flask, Blueprint, jsonify, request, send_file
from datetime import datetime, timezone, timedelta
from threading import Thread, Lock, Event
import requests
import time
import logging
import re
from unidecode import unidecode
from flask_cors import CORS




nba_bp = Blueprint('nba', __name__)




client_states = {}
lock = Lock()
paused = False
pause_lock = Lock()
live_mode = False
live_start_time = None




@nba_bp.route('/')
def serve_index():
    return send_file('index.html')




@nba_bp.route("/test", methods=["GET"])
def test_connection():
    return "Arduino connection successful!"




@nba_bp.route("/connect", methods=["GET", "POST"])
def connect_device():
    if request.method == "POST":
        data = request.get_json() or request.form
        ssid = data.get("ssid")
        password = data.get("pass")
    else:  # GET fallback
        ssid = request.args.get("ssid")
        password = request.args.get("pass")




    if not ssid or not password:
        return "Missing SSID or password", 400




    logging.info(f"Received WiFi credentials: SSID={ssid}, PASS={password}")
    return "WiFi credentials received", 200




@nba_bp.route('/games', methods=['GET'])
def list_games_by_date():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Missing date"}), 400


    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400


    espn_date = target_date.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={espn_date}"


    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()


        games = []
        for event in data.get("events", []):
            competition = event.get("competitions", [{}])[0]
            home_team = next(
                (t["team"]["abbreviation"] for t in competition["competitors"] if t["homeAway"] == "home"), "Home"
            )
            away_team = next(
                (t["team"]["abbreviation"] for t in competition["competitors"] if t["homeAway"] == "away"), "Away"
            )


            game_time = event.get("date", "Unknown")
            games.append({
                "gameId": event["id"],
                "homeTeam": home_team,
                "awayTeam": away_team,
                "gameTimeET": game_time
            })


        return jsonify(games)


    except Exception as e:
        return jsonify({"error": f"Failed to fetch ESPN data: {e}"}), 500




@nba_bp.route('/select_game', methods=['GET'])
def select_game():
    game_id = request.args.get("gameId")
    client_id = request.args.get("client_id")




    if not game_id:
        return jsonify({"error": "Missing gameId"}), 400
    if not client_id:
        return jsonify({"error": "Missing client_id"}), 400




    print(f"🏀 Client {client_id} selected game: {game_id}")




    # Initialize state if new client
    if client_id not in client_states:
        client_states[client_id] = {
            "game_id": None,
            "last_index": -1,
            "shots_dict": {},
            "order_numbers_sorted": [],
            "fetch_thread": None,
            "home_team": "Home",
            "away_team": "Away",
            "delivered_orders": set(),
            "stop_event": Event()
        }




    # Stop old thread if running
    old_thread = client_states[client_id]["fetch_thread"]
    if old_thread and old_thread.is_alive():
        client_states[client_id]["stop_event"].set()
        old_thread.join()




    # Reset client state
    client_states[client_id].update({
        "game_id": game_id,
        "last_index": -1,
        "shots_dict": {},
        "order_numbers_sorted": [],
        "delivered_orders": set()
    })




    # Fetch and update team names
    # Fetch and update team names using ESPN
    try:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={today}"
        resp = requests.get(url, timeout=10)
        data = resp.json()


        for event in data.get("events", []):
            if event.get("id") == game_id:
                competitors = event["competitions"][0]["competitors"]
                for team in competitors:
                    if team["homeAway"] == "home":
                        client_states[client_id]["home_team"] = team["team"]["abbreviation"]
                    elif team["homeAway"] == "away":
                        client_states[client_id]["away_team"] = team["team"]["abbreviation"]
                print(f"🏠 Home Team: {client_states[client_id]['home_team']}, 🛫 Away Team: {client_states[client_id]['away_team']}")
                break
    except Exception as e:
        print(f"⚠️ Could not fetch team names from ESPN: {e}")






    # Start new fetch thread
    stop_event = client_states[client_id]["stop_event"]
    stop_event.clear()
    new_thread = Thread(target=fetch_shots_loop, args=(client_id, game_id, stop_event), daemon=True)
    client_states[client_id]["fetch_thread"] = new_thread
    new_thread.start()




    return jsonify({"status": "ok", "message": f"Started tracking game {game_id} for client {client_id}"})




@nba_bp.route('/select_live_game', methods=['GET'])
def select_live_game():
    client_id = request.args.get("client_id")
    if not client_id:
        return jsonify({"error": "Missing client_id"}), 400




    game_id = get_active_game_id()
    if not game_id:
        print("❌ No live game found.")
        return jsonify({"error": "No active NBA game is in progress"}), 400




    print(f"🔴 Live mode activated for client {client_id}, game: {game_id}")




    # Initialize client if new
    if client_id not in client_states:
        client_states[client_id] = {
            "game_id": None,
            "last_index": -1,
            "shots_dict": {},
            "order_numbers_sorted": [],
            "fetch_thread": None,
            "home_team": "Home",
            "away_team": "Away",
            "delivered_orders": set(),
            "stop_event": Event()
        }




    # Stop old thread if running
    old_thread = client_states[client_id]["fetch_thread"]
    if old_thread and old_thread.is_alive():
        client_states[client_id]["stop_event"].set()
        old_thread.join()




    # Fetch team names for live game
    # Fetch team names for live game using ESPN
    try:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={today}"
        resp = requests.get(url, timeout=10)
        data = resp.json()


        for event in data.get("events", []):
            if event.get("id") == game_id:
                competitors = event["competitions"][0]["competitors"]
                for team in competitors:
                    if team["homeAway"] == "home":
                        client_states[client_id]["home_team"] = team["team"]["abbreviation"]
                    elif team["homeAway"] == "away":
                        client_states[client_id]["away_team"] = team["team"]["abbreviation"]
                break
    except Exception as e:
        print(f"⚠️ Could not fetch team names from ESPN: {e}")






    # Reset state
    client_states[client_id].update({
        "game_id": game_id,
        "last_index": -1,
        "shots_dict": {},
        "order_numbers_sorted": [],
        "delivered_orders": set()
    })




    stop_event = client_states[client_id]["stop_event"]
    stop_event.clear()
    new_thread = Thread(target=fetch_shots_loop, args=(client_id, game_id, stop_event), daemon=True)
    client_states[client_id]["fetch_thread"] = new_thread
    new_thread.start()




    return jsonify({
        "status": "ok",
        "message": f"Started tracking live game {game_id} for client {client_id}",
        "homeTeam": client_states[client_id]["home_team"],
        "awayTeam": client_states[client_id]["away_team"]
    })




@nba_bp.route('/next_shot', methods=['GET'])
def next_shot():
    client_id = request.args.get("client_id")
    if not client_id or client_id not in client_states:
        return jsonify({"error": "Missing or invalid client_id"}), 400


    with pause_lock:
        if paused:
            return '', 204


    with lock:
        client_data = client_states[client_id]
        delivered = client_data.setdefault("delivered_orders", set())
        order_numbers = client_data.get("order_numbers_sorted", [])
        shots_dict = client_data.get("shots_dict", {})


        if len(order_numbers) == 0:
            return '', 204


        # Find the next undelivered shot in order
        next_order = None
        for order in order_numbers:
            if order not in delivered:
                next_order = order
                break


        if next_order is None:
            # All shots delivered
            return '', 204


        shot = shots_dict.get(next_order)
        if not shot:
            return '', 204


        delivered.add(next_order)


        return jsonify({
            "index": next_order,
            "team": shot["team"],
            "description": shot["description"],
            "period": shot["period"],
            "clock": shot["clock"],
            "x": shot["x"],
            "y": shot["y"],
            "scoreHome": shot["scoreHome"],
            "scoreAway": shot["scoreAway"],
        })




@nba_bp.route('/current_game', methods=['GET'])
def current_game():
    client_id = request.args.get("client_id")
    if not client_id:
        return jsonify({"error": "Missing client_id"}), 400


    print(f"[DEBUG] current_game called with client_id: {client_id}")
    print(f"[DEBUG] current client_states keys: {list(client_states.keys())}")


    client_data = client_states.get(client_id)
    if not client_data:
        return jsonify({"error": "Invalid client_id"}), 400


    return jsonify({"game_id": client_data.get("game_id", "")})




@nba_bp.route('/is_paused', methods=['GET'])
def is_paused():
    with pause_lock:
        return jsonify({"paused": paused})




@nba_bp.route('/pause', methods=['POST'])
def pause():
    global paused
    with pause_lock:
        paused = True
    print("⏸️ System paused.")
    return jsonify({"status": "paused"})




@nba_bp.route('/resume', methods=['POST'])
def resume():
    global paused
    with pause_lock:
        paused = False
    print("▶️ System resumed.")
    return jsonify({"status": "running"})




def parse_iso8601_clock(clock_str):
    """Convert ISO 8601 PT#M#S format to MM:SS string."""
    match = re.match(r'PT(\d+)M([\d.]+)S', clock_str)
    if match:
        minutes = int(match.group(1))
        seconds = float(match.group(2))
        return f"{minutes:02}:{int(seconds):02}"
    return "00:00"




def normalize_player_name(name: str) -> str:
    return unidecode(name)




def replace_special_chars(s):
    replacements = {
        'ö': 'o',
        'Ö': 'O',
        'ä': 'a',
        'Ä': 'A',
        'ü': 'u',
        'Ü': 'U',
        'ß': 'ss'
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    return s




@nba_bp.route("/peek_shot", methods=["GET"])
def peek_shot():
    client_id = request.args.get("client_id")
    if not client_id or client_id not in client_states:
        return jsonify({"error": "Invalid client ID"}), 400


    with lock:
        state = client_states[client_id]
        if not state["order_numbers_sorted"]:
            return jsonify({"shot": None})  # No new shots


        next_id = state["order_numbers_sorted"].pop(0)
        team = state["shots_dict"].get(next_id)


        if not team:
            return jsonify({"shot": None})


        # Optionally clean up
        del state["shots_dict"][next_id]


        return jsonify({"shot": team})






@nba_bp.route('/pop_shot', methods=['POST'])
def pop_shot():
    data = request.get_json()
    client_id = data.get("client_id")
    shot_index = data.get("shot_index")  # This is now the ESPN play_id (string)


    if not client_id or client_id not in client_states:
        return jsonify({"error": "Missing or invalid client_id"}), 400
    if shot_index is None:
        return jsonify({"error": "Missing shot_index"}), 400


    with lock:
        delivered = client_states[client_id].setdefault("delivered_orders", set())
        delivered.add(shot_index)


    return jsonify({"status": "ok", "delivered_count": len(delivered)})


def fetch_shots_loop(client_id, game_id, stop_event):
    print(f"📡 Starting fetch thread for {client_id} | gameId: {game_id}")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={game_id}"


    while not stop_event.is_set():
        if client_id not in client_states:
            print(f"❌ Client {client_id} no longer registered.")
            break


        with pause_lock:
            if paused:
                time.sleep(0.5)
                continue


        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            plays = data.get("plays", [])
            with lock:
                # Get persistent client shot state
                shots_dict = client_states[client_id].setdefault("shots_dict", {})
                order_numbers_sorted = client_states[client_id].setdefault("order_numbers_sorted", [])


                for play in plays:
                    play_type = play.get("type", {}).get("text", "").lower()
                    if "shot" not in play_type:
                        continue


                    team_id = play.get("team", {}).get("id")
                    team = ESPN_TEAM_ID_TO_ABBR.get(team_id)
                    if not team:
                        continue


                    play_id = play.get("id")
                    if not play_id or play_id in shots_dict:
                        continue  # Already have this shot


                    x_raw = play.get("coordinate", {}).get("x")
                    y_raw = play.get("coordinate", {}).get("y")


                    # Add new shot to persistent dict and order list
                    shots_dict[play_id] = {
                        "team": team,
                        "description": play.get("text", ""),
                        "period": play.get("period", {}).get("number"),
                        "clock": play.get("clock", {}).get("displayValue"),
                        "x": x_raw,
                        "y": y_raw,
                        "scoreHome": play.get("homeScore"),
                        "scoreAway": play.get("awayScore"),
                    }
                    order_numbers_sorted.append(play_id)
                    print(f"🏀 New shot for client {client_id} | {team} | {play.get('text', '')}")


        except Exception as e:
            print(f"⚠️ Error in fetch loop for {client_id}: {e}")


        time.sleep(1)




# Helper to map ESPN team id to abbreviation
# You can fetch this once from scoreboard or hardcode for testing
ESPN_TEAM_ID_TO_ABBR = {
    "1": "ATL", "2": "BOS", "3": "BKN", "4": "CHA", "5": "CHI",
    "6": "CLE", "7": "DAL", "8": "DEN", "9": "DET", "10": "GSW",
    "11": "HOU", "12": "IND", "13": "LAC", "14": "LAL", "15": "MEM",
    "16": "MIN", "17": "NOP", "18": "NYK", "19": "OKC", "20": "ORL",
    "21": "PHI", "22": "PHX", "23": "POR", "24": "SAC", "25": "SAS",
    "26": "TOR", "27": "UTA", "28": "WAS"
}

def get_team_abbr_from_id(team_id):
    return ESPN_TEAM_ID_TO_ABBR.get(str(team_id), None)

# Dummy transform_coordinates, transform_x, transform_y functions
# Replace these with your actual implementations
def transform_coordinates(x, y):
    return x, y

def transform_x(x):
    return x


def transform_y(y):
    return y


def check_if_game_over(game_id):
    return False


def get_active_game_id():
    try:
        now = datetime.now(timezone.utc)
        espn_date = now.strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={espn_date}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        games = data.get("events", [])


        if not games:
            print("⚠️ No games found in ESPN scoreboard.")
            return None


        for event in games:
            status_info = event.get("status", {}).get("type", {})
            status_text = status_info.get("description", "")
            game_id = event.get("id", "UNKNOWN")


            competition = event.get("competitions", [{}])[0]
            competitors = competition.get("competitors", [])
            away = next((t["team"]["abbreviation"] for t in competitors if t["homeAway"] == "away"), "???")
            home = next((t["team"]["abbreviation"] for t in competitors if t["homeAway"] == "home"), "???")


            print(f"📝 Game {game_id} | {away} @ {home} | Status: {status_text}")


            if status_info.get("name") == "STATUS_IN_PROGRESS":
                print(f"✅ Found live game: {game_id} ({away} @ {home})")
                return game_id


        print("❌ No live game found.")
    except Exception as e:
        print(f"⚠️ Error getting active ESPN game ID: {e}")


    return None


app = Flask(__name__)
app.register_blueprint(nba_bp)
CORS(app)



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)



