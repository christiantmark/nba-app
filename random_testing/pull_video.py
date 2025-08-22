# generate_event_urls.py

import urllib.parse

# Example shot log
shot_log = [
    {
        "player_name": "Trayce Jackson-Davis",
        "shot_description": "3' Driving Hook Shot",
        "points": 2,
        "assist_player": "Wiggins",
        "game_event_id": 7,
        "game_id": "0022400383",
        "season": "2024-25"
    },
    # Add more shots here...
]

for shot in shot_log:
    title = f"{shot['player_name']} {shot['shot_description']} ({shot['points']} PTS) ({shot['assist_player']} 1 AST)"
    
    # URL-encode the title
    encoded_title = urllib.parse.quote(title)
    
    # Construct the event-specific URL
    event_url = (
        f"https://www.nba.com/stats/events?"
        f"CFID=&CFPARAMS=&"
        f"GameEventID={shot['game_event_id']}&"
        f"GameID={shot['game_id']}&"
        f"Season={shot['season']}&"
        f"flag=1&"
        f"title={encoded_title}"
    )
    
    print(f"Shot: {title}")
    print(f"Event URL: {event_url}")
    print("-" * 80)
