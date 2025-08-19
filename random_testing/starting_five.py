# import requests

# def get_opening_five_traditional(game_id):
#     url = (
#         "https://stats.nba.com/stats/boxscoretraditionalv2"
#         f"?GameID={game_id}&StartPeriod=1&EndPeriod=1"
#     )
#     headers = {
#         "User-Agent":         "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
#         "Referer":            "https://www.nba.com/",
#         "x-nba-stats-origin": "stats",
#         "x-nba-stats-token":  "true",
#     }

#     resp = requests.get(url, headers=headers, timeout=10)
#     resp.raise_for_status()
#     data = resp.json()

#     player_headers = data["resultSets"][0]["headers"]
#     player_rows = data["resultSets"][0]["rowSet"]

#     team_headers = data["resultSets"][1]["headers"]
#     team_rows = data["resultSets"][1]["rowSet"]

#     idx_player_id = player_headers.index("PLAYER_ID")
#     idx_team_id = player_headers.index("TEAM_ID")
#     idx_start_pos = player_headers.index("START_POSITION")
#     idx_player_name = player_headers.index("PLAYER_NAME")

#     # Determine home and away team IDs from team rows
#     home_team_id = team_rows[0][team_headers.index("TEAM_ID")]
#     away_team_id = team_rows[1][team_headers.index("TEAM_ID")]

#     print(f"[DEBUG] Home team ID: {home_team_id}")
#     print(f"[DEBUG] Away team ID: {away_team_id}")

#     starters = {"HOME": [], "AWAY": []}
#     for row in player_rows:
#         player_id = row[idx_player_id]
#         player_name = row[idx_player_name]
#         team_id = row[idx_team_id]
#         start_pos = row[idx_start_pos]
#         if start_pos:
#             starter_info = {"id": player_id, "name": player_name}
#             if team_id == home_team_id:
#                 starters["HOME"].append(starter_info)
#             elif team_id == away_team_id:
#                 starters["AWAY"].append(starter_info)

#     return starters

# if __name__ == "__main__":
#     game_id = "0022400383"
#     starters = get_opening_five_traditional(game_id)
#     print("Home starters:", starters["HOME"])
#     print("Away starters:", starters["AWAY"])

import requests

def fetch_nba_cdn_boxscore(game_id):
    url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    game = data.get('game', {})
    home = game.get('homeTeam', {})
    away = game.get('awayTeam', {})

    def extract_starters(team):
        starters = []
        players = team.get('players', [])
        for p in players:
            if p.get('starter') == '1':  # Starter flag is string "1"
                stats = p.get('statistics', {})
                starters.append({
                    "name": p.get('name'),
                    "position": p.get('position'),
                    "points": stats.get('points', 0),
                    "rebounds": stats.get('reboundsTotal', 0),
                    "assists": stats.get('assists', 0)
                })
        return starters

    home_starters = extract_starters(home)
    away_starters = extract_starters(away)

    print(f"Home team ({home.get('teamTricode')}):")
    for s in home_starters:
        print(f"  {s['name']} ({s['position']}) - PTS: {s['points']}, REB: {s['rebounds']}, AST: {s['assists']}")

    print(f"\nAway team ({away.get('teamTricode')}):")
    for s in away_starters:
        print(f"  {s['name']} ({s['position']}) - PTS: {s['points']}, REB: {s['rebounds']}, AST: {s['assists']}")

if __name__ == "__main__":
    game_id = "0022400383"  # Example: GSW vs MIN
    fetch_nba_cdn_boxscore(game_id)
