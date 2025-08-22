import requests
import json
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+
import pytz

utc = pytz.utc
eastern = pytz.timezone("America/New_York")

def check_game_exists(game_id):
    url = f"https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
    try:
        response = requests.head(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

def get_game_info(game_id):
    url = f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            game = data['game']
            home = game['homeTeam']['teamTricode']
            away = game['awayTeam']['teamTricode']
            
            # Parse UTC time and convert to US Eastern
            utc_dt = datetime.strptime(game['gameTimeUTC'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=ZoneInfo("UTC"))
            eastern_dt = utc_dt.astimezone(ZoneInfo("America/New_York"))
            date = eastern_dt.date().isoformat()

            return {
                "game_id": game_id,
                "home_team": home,
                "away_team": away,
                "date": date
            }
    except requests.RequestException:
        pass
    return None

def format_game_id(season_prefix, game_num):
    return f"{season_prefix}{game_num:05d}"

# ... [other functions unchanged] ...

def find_games_by_date_range_forward(start_game_id, start_date_str, end_date_str, max_missing=25, scan_limit=500):
    from datetime import date

    start_date = date.fromisoformat(start_date_str)
    end_date = date.fromisoformat(end_date_str)

    season_prefix = start_game_id[:-5]
    start_num = int(start_game_id[-5:])
    current_num = start_num
    missing_count = 0
    games_by_date = defaultdict(list)

    scanned = 0
    while missing_count < max_missing and scanned < scan_limit:
        game_id = format_game_id(season_prefix, current_num)
        scanned += 1

        if check_game_exists(game_id):
            info = get_game_info(game_id)
            if info:
                game_date = datetime.fromisoformat(info["date"]).date()

                # Only accept games inside the date range
                if start_date <= game_date <= end_date:
                    print(f"✅ {game_id}: {info['away_team']} @ {info['home_team']} ({info['date']})")
                    games_by_date[info["date"]].append({
                        "game_id": info["game_id"],
                        "home_team": info["home_team"],
                        "away_team": info["away_team"]
                    })
                    missing_count = 0  # Reset missing count on success
                else:
                    print(f"Skipping {game_id} (outside date range: {info['date']})")
                    missing_count += 1  # Count as a miss, but don't stop immediately
            else:
                print(f"⚠️ Metadata fetch failed for {game_id}")
                missing_count += 1
        else:
            print(f"❌ {game_id} does not exist.")
            missing_count += 1

        current_num += 1  # Scan forward

    return dict(games_by_date)


if __name__ == "__main__":
    start_game_id = "0022400859"  # Adjust as needed to start near Jan 1, 2025
    start_date = "2025-02-28"
    end_date = "2025-03-07"  # Change if you want a smaller/larger window

    upcoming_games = find_games_by_date_range_forward(start_game_id, start_date, end_date)

    print("\n🎯 Formatted JSON Output:")
    print(json.dumps(upcoming_games, indent=2))
