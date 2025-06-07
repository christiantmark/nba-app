import requests
import serial
import time

FLASK_SERVER = "http://localhost:5000"
SERIAL_PORT = "COM5"                    # Update to match your Arduino port
BAUD_RATE = 9600
USE_REAL_TIME = False                   # Leave False to use fixed delay
DELAY_BETWEEN_SHOTS = 2.0               # 2-second delay between shots

def prompt_for_game():
    date_input = input("Enter the game date (YYYY-MM-DD): ").strip()
    try:
        response = requests.get(f"{FLASK_SERVER}/games/{date_input}")
        response.raise_for_status()
        games = response.json()

        if not games:
            print("No games found on that date.")
            return None

        print(f"\nNBA games on {date_input}:")
        for i, game in enumerate(games):
            print(f"[{i}] {game['away_team']} @ {game['home_team']} | Game ID: {game['game_id']} | Time (ET): {game['game_time_et']}")

        choice = int(input("\nSelect a game number to replay: "))
        return games[choice]["game_id"]

    except (ValueError, IndexError):
        print("Invalid selection.")
    except Exception as e:
        print(f"Error fetching games: {e}")
    
    return None

def main():
    game_id = prompt_for_game()
    if not game_id:
        return

    try:
        response = requests.get(f"{FLASK_SERVER}/shots/{game_id}")
        response.raise_for_status()
        shots = response.json()
    except Exception as e:
        print(f"Failed to get shots: {e}")
        return

    if not shots:
        print("No shots available for this game.")
        return

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"Connected to {SERIAL_PORT}")
    except Exception as e:
        print(f"Failed to connect to serial port: {e}")
        return

    print(f"Sending {len(shots)} shots...\n")

    start_time = time.time()
    if USE_REAL_TIME:
        first_shot_time = time.strptime(shots[0]["timeActual"], "%Y-%m-%dT%H:%M:%S.%fZ")

    for shot in shots:
        if USE_REAL_TIME:
            shot_time = time.strptime(shot["timeActual"], "%Y-%m-%dT%H:%M:%S.%fZ")
            elapsed_shot = time.mktime(shot_time) - time.mktime(first_shot_time)
            now_elapsed = time.time() - start_time

            wait_time = elapsed_shot - now_elapsed
            if wait_time > 0:
                time.sleep(wait_time)
        else:
            time.sleep(DELAY_BETWEEN_SHOTS)

        x = shot["x"]
        y = shot["y"]
        color = 'G' if shot["result"] == "Made" else 'R'
        shooter = shot.get("player", "Unknown")
        serial_msg = f"{x},{y},{color}\n"

        print(f"Shot by {shooter}: {x},{y},{color}")

        try:
            ser.write(serial_msg.encode())
        except Exception as e:
            print(f"Serial write error: {e}")
            break

    print("All shots sent.")

if __name__ == "__main__":
    main()
