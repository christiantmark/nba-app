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


NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
NBA_GAME_BASE_URL = "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{}.json"


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

    try:
        resp = requests.get(NBA_SCHEDULE_URL, timeout=10)
        resp.raise_for_status()
        schedule_data = resp.json()
        print(f"Schedule data keys: {list(schedule_data.keys())}")
        schedule = schedule_data.get("leagueSchedule", {}).get("gameDates", [])
        print(f"Sample gameDate entries: {[day.get('gameDate') for day in schedule[:3]]}")
    except Exception as e:
        print(f"Failed to fetch or parse schedule: {e}")
        return jsonify({"error": f"Failed to fetch schedule: {e}"}), 500

    target_date_str = target_date.strftime("%m/%d/%Y 00:00:00")
    for day in schedule:
        if day.get("gameDate") == target_date_str:
            games = day.get("games", [])
            return jsonify([
                {
                    "gameId": g["gameId"],
                    "homeTeam": g["homeTeam"]["teamTricode"],
                    "awayTeam": g["awayTeam"]["teamTricode"],
                    "gameTimeET": g.get("gameEt", "Unknown")
                }
                for g in games
            ])
    return jsonify([])

@nba_bp.route('/schedule_range', methods=['GET'])
def schedule_range():
    try:
        resp = requests.get(NBA_SCHEDULE_URL, timeout=10)
        resp.raise_for_status()
        schedule_data = resp.json()
        game_dates = schedule_data.get("leagueSchedule", {}).get("gameDates", [])
        if not game_dates:
            return jsonify({"error": "No schedule data"}), 500
        dates = [datetime.strptime(day["gameDate"], "%m/%d/%Y %H:%M:%S") for day in game_dates]
        min_date = min(dates).strftime("%Y-%m-%d")
        max_date = max(dates).strftime("%Y-%m-%d")
        return jsonify({"min_date": min_date, "max_date": max_date})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    try:
        resp = requests.get(NBA_SCHEDULE_URL, timeout=10)
        resp.raise_for_status()
        schedule_data = resp.json()
        all_games = [
            g
            for day in schedule_data.get("leagueSchedule", {}).get("gameDates", [])
            for g in day.get("games", [])
        ]
        for g in all_games:
            if g.get("gameId") == game_id:
                client_states[client_id]["home_team"] = g.get("homeTeam", {}).get("teamTricode", "Home")
                client_states[client_id]["away_team"] = g.get("awayTeam", {}).get("teamTricode", "Away")
                print(f"🏠 Home Team: {client_states[client_id]['home_team']}, 🛫 Away Team: {client_states[client_id]['away_team']}")
                break
    except Exception as e:
        print(f"⚠️ Could not fetch team names: {e}")


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
    try:
        scoreboard = requests.get("https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json", timeout=10).json()
        for g in scoreboard.get("scoreboard", {}).get("games", []):
            if g.get("gameId") == game_id:
                client_states[client_id]["home_team"] = g.get("homeTeam", {}).get("teamTricode", "Home")
                client_states[client_id]["away_team"] = g.get("awayTeam", {}).get("teamTricode", "Away")
                break
    except Exception as e:
        print(f"⚠️ Could not fetch team names: {e}")


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
    if not client_id:
        return jsonify({"error": "Missing client_id"}), 400


    with pause_lock:
        if paused:
            return '', 204


    with lock:
        client_data = client_states.get(client_id)
        if not client_data:
            return jsonify({"error": "Invalid client_id"}), 400


        delivered = client_data.get("delivered_orders", set())
        order_numbers = client_data.get("order_numbers_sorted", [])
        shots_dict = client_data.get("shots_dict", {})
        game_id = client_data.get("game_id")


        if len(order_numbers) < 5:
            return '', 204


        # ✅ Only require prior orderNumber to be delivered
        next_order = None
        for i, o in enumerate(order_numbers):
            if o not in delivered:
                if i == 0 or order_numbers[i - 1] in delivered:
                    next_order = o
                    break
        else:
            return '', 204


        shot = shots_dict.get(next_order)
        if not shot:
            return '', 204


        # Mark as delivered
        delivered.add(next_order)
        client_data["last_index"] = max(client_data["last_index"], next_order)
        client_data["delivered_orders"] = delivered


        clock_raw = shot.get("clock", "")
        readable_clock = parse_iso8601_clock(clock_raw) if clock_raw else ""
        period = shot.get('period', 1)


        player_name = unidecode(shot.get("player", ""))
        desc_text = unidecode(shot.get("description", ""))


        return jsonify({
            "index": next_order,
            "player": player_name,
            "description": desc_text,
            "team": shot.get("team", ""),
            "result": shot.get("result", ""),
            "color": shot.get("color", ""),
            "x": transform_x(shot.get("x", -1)) if shot.get("x") is not None else -1,
            "y": transform_y(shot.get("y", -1)) if shot.get("y") is not None else -1,
            "timeActual": shot.get("timeActual", ""),
            "scoreHome": shot.get("scoreHome", "N/A"),
            "scoreAway": shot.get("scoreAway", "N/A"),
            "teamHomeAbbrev": client_data.get("home_team", "Home"),
            "teamAwayAbbrev": client_data.get("away_team", "Away"),
            "clock": readable_clock,
            "period": period
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


@nba_bp.route('/peek_shot', methods=['GET'])
def peek_shot():
    client_id = request.args.get("client_id")
    if not client_id:
        return jsonify({"error": "Missing client_id"}), 400




    with pause_lock:
        if paused:
            return '', 204




    with lock:
        client_data = client_states.get(client_id)
        if not client_data:
            return jsonify({"error": "Invalid client_id"}), 400




        delivered = client_data.get("delivered_orders", set())
        order_numbers = client_data.get("order_numbers_sorted", [])
        shots_dict = client_data.get("shots_dict", {})




        if len(order_numbers) < 1:
            return '', 204




        # Find next shot NOT marked delivered yet, or last delivered shot
        next_order = None
        for o in order_numbers:
            if o not in delivered:
                next_order = o
                break
        if next_order is None:
            # All shots delivered, show last shot
            next_order = order_numbers[-1]




        shot = shots_dict.get(next_order)
        if not shot:
            return '', 204




        clock_raw = shot.get("clock", "")
        readable_clock = parse_iso8601_clock(clock_raw) if clock_raw else ""
        period = shot.get('period', 1)




        player_name = unidecode(shot.get("player", ""))
        desc_text = unidecode(shot.get("description", ""))




        return jsonify({
            "index": next_order,
            "player": player_name,
            "description": desc_text,
            "team": shot.get("team", ""),
            "result": shot.get("result", ""),
            "color": shot.get("color", ""),
            "x": transform_x(shot.get("x", -1)) if shot.get("x") is not None else -1,
            "y": transform_y(shot.get("y", -1)) if shot.get("y") is not None else -1,
            "timeActual": shot.get("timeActual", ""),
            "scoreHome": shot.get("scoreHome", "N/A"),
            "scoreAway": shot.get("scoreAway", "N/A"),
            "teamHomeAbbrev": client_data.get("home_team", "Home"),
            "teamAwayAbbrev": client_data.get("away_team", "Away"),
            "clock": readable_clock,
            "period": period
        })


@nba_bp.route('/pop_shot', methods=['POST'])
def pop_shot():
    data = request.get_json()
    client_id = data.get("client_id")
    shot_index = data.get("shot_index")


    if not client_id or client_id not in client_states:
        return jsonify({"error": "Missing or invalid client_id"}), 400
    if shot_index is None:
        return jsonify({"error": "Missing shot_index"}), 400


    with lock:
        current_last = client_states[client_id].get("last_index", -1)
        if shot_index > current_last:
            client_states[client_id]["last_index"] = shot_index


    return jsonify({"status": "ok", "last_index": client_states[client_id]["last_index"]})


def fetch_shots_loop(client_id, game_id, stop_event):
    team_basket_side = {}
    left_basket = (10, 15)
    right_basket = (38, 15)


    while not stop_event.is_set():
        home_team = client_states[client_id]["home_team"].upper()
        away_team = client_states[client_id]["away_team"].upper()


        try:
            url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            actions = resp.json().get("game", {}).get("actions", [])


            added = 0
            for a in actions:
                action_type = a.get("actionType")
                result = a.get("shotResult")
                has_player = a.get("playerNameI") or a.get("playerName")
                team = a.get("teamTricode")
                period = a.get("period", 1)


                if not result or not a.get("timeActual") or not has_player or not team:
                    continue


                time_actual = datetime.strptime(a["timeActual"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


                order_number = a.get("orderNumber", 0)
                with lock:
                    if order_number in client_states[client_id]["shots_dict"]:
                        continue


                team_upper = team.strip().upper()


                if action_type in ["2pt", "3pt"] and "x" in a and "y" in a:
                    raw_x = int(round((a["x"] / 100.0) * 47))
                    raw_y = 31 - int(round((a["y"] / 100.0) * 31))
                    led_x, led_y = transform_coordinates(raw_x, raw_y)


                    if result == "Made":
                        if period <= 2:
                            team_basket_side[team_upper] = right_basket if team_upper == home_team else left_basket
                        else:
                            team_basket_side[team_upper] = left_basket if team_upper == home_team else right_basket


                    shot_data = {
                        "x": led_x,
                        "y": led_y,
                        "result": result,
                        "timeActual": a["timeActual"],
                        "player": has_player,
                        "team": team,
                        "orderNumber": order_number,
                        "scoreHome": a.get("scoreHome", "N/A"),
                        "scoreAway": a.get("scoreAway", "N/A"),
                        "description": a.get("description", ""),
                        "clock": a.get("clock", ""),
                        "period": period,
                        "color": "green" if result == "Made" else "red"
                    }


                elif action_type == "freethrow" and result in ["Made", "Missed"]:
                    if team_upper in team_basket_side:
                        ft_x, ft_y = team_basket_side[team_upper]
                    else:
                        if (period <= 2 and team_upper == home_team) or (period >= 3 and team_upper == away_team):
                            ft_x, ft_y = left_basket
                        else:
                            ft_x, ft_y = right_basket


                    color = "green" if result == "Made" else "red"


                    shot_data = {
                        "x": ft_x,
                        "y": ft_y,
                        "result": result,
                        "timeActual": a["timeActual"],
                        "player": has_player,
                        "team": team,
                        "orderNumber": order_number,
                        "scoreHome": a.get("scoreHome", "N/A"),
                        "scoreAway": a.get("scoreAway", "N/A"),
                        "description": a.get("description", ""),
                        "clock": a.get("clock", ""),
                        "period": period,
                        "color": color
                    }


                else:
                    continue


                with lock:
                    client_states[client_id]["shots_dict"][order_number] = shot_data
                    added += 1


            if added:
                with lock:
                    client_states[client_id]["order_numbers_sorted"] = sorted(client_states[client_id]["shots_dict"])
                    print(f"📅 Client {client_id}: Cached {added} new shots. Total: {len(client_states[client_id]['order_numbers_sorted'])}")


        except Exception as e:
            print(f"❌ Client {client_id} - Error fetching shots: {e}")


        time.sleep(5)


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
        scoreboard=requests.get("https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json",timeout=10).json()
        games=scoreboard.get("scoreboard",{}).get("games",[])
        if not games:
            print("⚠️ No games found in scoreboard.")
            return None
        live_status_keywords=["1st Qtr","2nd Qtr","3rd Qtr","4th Qtr","OT","In Progress"]
        for g in games:
            game_id=g.get("gameId")
            status=g.get("gameStatusText","").strip()
            away=g.get("awayTeam",{}).get("teamTricode","???")
            home=g.get("homeTeam",{}).get("teamTricode","???")
            print(f"📝 Game {game_id} | {away} @ {home} | Status: {status}")
            if any(keyword in status for keyword in live_status_keywords):
                print(f"✅ Found live game: {game_id} ({away} @ {home})")
                return game_id
        print("❌ No live game found.")
    except Exception as e:
        print(f"⚠️ Error getting active game id: {e}")
    return None


app = Flask(__name__)
app.register_blueprint(nba_bp)
CORS(app)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

