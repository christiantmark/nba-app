from flask import Flask, request, jsonify
import requests, logging
from threading import Lock

app = Flask(__name__)
client_states = {}
lock = Lock()
logging.basicConfig(level=logging.DEBUG)

API_BASE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"

@app.route("/select_game")
def select_game():
    game_id = request.args.get("gameId")
    cid = request.args.get("client_id")
    if not game_id or not cid:
        return "Missing gameId or client_id", 400

    url = f"{API_BASE}/events/{game_id}/competitions/{game_id}/plays?limit=500"
    logging.debug("Fetching plays from: %s", url)
    resp = requests.get(url)
    if resp.status_code != 200:
        return jsonify({"error": "Failed to fetch plays", "status": resp.status_code}), resp.status_code

    data = resp.json()
    plays = data.get("items") or data.get("plays") or []
    logging.debug("Plays fetched: %d", len(plays))

    if not plays:
        return jsonify({"error": "No plays found"}), 404

    simple = [{"text": p.get("text"), "period": p.get("period", {}).get("number"), "clock": p.get("clock", {}).get("displayValue")} for p in plays]

    with lock:
        client_states[cid] = {"plays": simple, "last_idx": -1}

    return jsonify({"message": f"Loaded {len(simple)} plays"}), 200

@app.route("/peek_shot")
def peek_shot():
    cid = request.args.get("client_id")
    if cid not in client_states:
        return jsonify({"error": "Invalid client_id"}), 400

    state = client_states[cid]
    state["last_idx"] += 1
    if state["last_idx"] >= len(state["plays"]):
        return jsonify({"message": "No new play"}), 204

    return jsonify(state["plays"][state["last_idx"]])

if __name__ == "__main__":
    app.run(debug=True)
