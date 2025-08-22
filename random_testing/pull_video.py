import requests
import urllib.parse

GAME_ID = "0022400383"
SEASON = "2024-25"

url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{GAME_ID}.json"
resp = requests.get(url)
pbp = resp.json()

# Keep only made/missed shots
shot_events = [
    play for play in pbp["game"]["actions"]
    if play.get("shotResult") in ["Made", "Missed"]
]

for shot in shot_events:
    player_name = shot.get("playerNameI", "Unknown")
    description = shot.get("description", "")
    game_event_id = shot.get("actionNumber")
    shot_result = shot.get("shotResult")
    points = shot.get("pointsTotal", 0)

    # Build a title similar to NBA.com
    title = f"{player_name} {description}"
    if points:
        title += f" ({points} PTS)"

    encoded_title = urllib.parse.quote(title)
    event_url = (
        f"https://www.nba.com/stats/events?"
        f"CFID=&CFPARAMS=&"
        f"GameEventID={game_event_id}&"
        f"GameID={GAME_ID}&"
        f"Season={SEASON}&"
        f"flag=1&"
        f"title={encoded_title}"
    )

    print(f"Shot: {title}")
    print(f"URL: {event_url}")
    print("-" * 80)
