# player_id_name_map.py

from nba_api.stats.static import players
import json

def get_all_player_id_name_map(active_only=False, save_to_file=False):
    """
    Returns a dictionary mapping player_id to player_name.
    :param active_only: If True, only includes currently active players.
    :param save_to_file: If True, saves the output to player_id_name_map.json.
    :return: Dictionary {player_id: player_name}
    """
    all_players = players.get_players()
    
    if active_only:
        all_players = [p for p in all_players if p['is_active']]

    id_name_map = {p['id']: p['full_name'] for p in all_players}

    if save_to_file:
        with open("player_id_name_map.json", "w") as f:
            json.dump(id_name_map, f, indent=2)
        print("Saved to player_id_name_map.json")

    return id_name_map

if __name__ == "__main__":
    player_map = get_all_player_id_name_map(active_only=False, save_to_file=True)
    print(f"Loaded {len(player_map)} players.")
