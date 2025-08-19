import requests

url = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_0022400383.json"

headers = {
    "User-Agent": "Mozilla/5.0"
}

try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    data = response.json()

    home_players = data["game"]["homeTeam"]["players"]
    away_players = data["game"]["awayTeam"]["players"]
    players = home_players + away_players

    for player in players:
        if str(player["personId"]) == "201939":  # Stephen Curry's ID
            stats = player["statistics"]
            print(f"✅ {player['name']} scored {stats['points']} points, "
                  f"{stats['assists']} assists, {stats['reboundsTotal']} rebounds.")
            break
    else:
        print("❌ Curry not found.")

except requests.exceptions.RequestException as req_err:
    print("Request error:", req_err)
except ValueError as json_err:
    print("JSON parse error:", json_err)
