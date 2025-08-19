import requests
import json

url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_2.json"

response = requests.get(url)
data = response.json()

ist_games = []

for day in data['leagueSchedule']['gameDates']:
    for game in day['games']:
        subtype = game.get("gameSubtype")
        game_type = game.get("gameType")
        labels = game.get("labels", [])
        is_ist = (
            subtype == "IST" or 
            game_type == "2" or 
            any("In-Season Tournament" in label for label in labels)
        )
        if is_ist:
            ist_games.append({
                "date": day['gameDate'],
                "game_id": game['gameId'],
                "home": game['homeTeam']['teamTricode'],
                "away": game['awayTeam']['teamTricode'],
                "subtype": subtype,
                "labels": labels
            })

print(f"✅ Found {len(ist_games)} IST games:")
print(json.dumps(ist_games, indent=2))
