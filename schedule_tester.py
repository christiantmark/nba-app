import json

with open('schedule_map.json') as f:
    schedule_map = json.load(f)

date = "2024-12-21"
games = schedule_map.get(date)
print("Raw games data for date:", games)

for g in games:
    print("game_id:", g.get("game_id"))
    print("home_team:", g.get("home_team"))
    print("away_team:", g.get("away_team"))
