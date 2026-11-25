"""Authoritative TCP server for the online Battleship game.

Run: python server.py
The server listens on 0.0.0.0:5000 by default.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import ssl
import sqlite3
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

HOST = "0.0.0.0"
PORT = 5000
DB_FILE = os.path.join(os.path.dirname(__file__), "battleship.db")
BOARD_SIZE = 6
SHIP_COUNT = 5
PASSWORD_ITERATIONS = 310_000

# Optional TLS. Set BATTLESHIP_TLS_CERT and BATTLESHIP_TLS_KEY environment
# variables to certificate/key paths (for example, from Let's Encrypt).
TLS_CERT = os.environ.get("BATTLESHIP_TLS_CERT")
TLS_KEY = os.environ.get("BATTLESHIP_TLS_KEY")


def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_FILE, timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with db_connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY COLLATE NOCASE,
                salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                wins INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


def hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )


def get_user(username: str):
    with db_connect() as connection:
        return connection.execute(
            "SELECT username, salt, password_hash, wins FROM users WHERE username = ?",
            (username,),
        ).fetchone()


def create_user(username: str, password: str) -> tuple[bool, str]:
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
        return False, "Username mora imati 3–20 karaktera (slova, brojevi ili _)."
    if len(password) < 8:
        return False, "Lozinka mora imati najmanje 8 karaktera."

    salt = secrets.token_bytes(16)
    password_hash = hash_password(password, salt)
    try:
        with db_connect() as connection:
            connection.execute(
                "INSERT INTO users (username, salt, password_hash) VALUES (?, ?, ?)",
                (username, salt, password_hash),
            )
        return True, "Nalog je uspešno kreiran."
    except sqlite3.IntegrityError:
        return False, "Taj username je već zauzet."


def authenticate(username: str, password: str):
    user = get_user(username)
    if user is None:
        return None
    candidate = hash_password(password, user["salt"])
    if not hmac.compare_digest(candidate, user["password_hash"]):
        return None
    return {"username": user["username"], "wins": user["wins"]}


def increment_wins(username: str) -> int:
    with db_connect() as connection:
        connection.execute(
            "UPDATE users SET wins = wins + 1 WHERE username = ?", (username,)
        )
        row = connection.execute(
            "SELECT wins FROM users WHERE username = ?", (username,)
        ).fetchone()
    return int(row["wins"]) if row else 0


def leaderboard(limit: int = 10) -> list[dict]:
    with db_connect() as connection:
        rows = connection.execute(
            "SELECT username, wins FROM users ORDER BY wins DESC, username COLLATE NOCASE ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"username": row["username"], "wins": row["wins"]} for row in rows]


@dataclass(eq=False)
class Client:
    conn: socket.socket
    address: tuple
    send_lock: threading.Lock = field(default_factory=threading.Lock)
    username: Optional[str] = None
    game: Optional[dict] = None
    player_index: Optional[int] = None
    alive: bool = True

    def send(self, message: dict) -> bool:
        payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with self.send_lock:
                self.conn.sendall(payload)
            return True
        except OSError:
            self.alive = False
            return False


class BattleshipServer:
    def __init__(self):
        self.lock = threading.RLock()
        self.waiting: deque[Client] = deque()
        self.active_users: dict[str, Client] = {}
        self.context = None
        if TLS_CERT and TLS_KEY:
            self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.context.load_cert_chain(TLS_CERT, TLS_KEY)
            print("TLS je uključen.")

    def run(self) -> None:
        initialize_database()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((HOST, PORT))
            server_socket.listen(100)
            print(f"Battleship server sluša na {HOST}:{PORT}")
            while True:
                connection, address = server_socket.accept()
                if self.context:
                    try:
                        connection = self.context.wrap_socket(connection, server_side=True)
                    except ssl.SSLError:
                        connection.close()
                        continue
                client = Client(connection, address)
                threading.Thread(
                    target=self.handle_client, args=(client,), daemon=True
                ).start()

    def handle_client(self, client: Client) -> None:
        print(f"Povezan klijent: {client.address}")
        buffer = b""
        try:
            while client.alive:
                data = client.conn.recv(4096)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        message = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        client.send({"type": "error", "message": "Neispravna poruka."})
                        continue
                    if not isinstance(message, dict):
                        client.send({"type": "error", "message": "Neispravna poruka."})
                        continue
                    self.handle_message(client, message)
        except OSError:
            pass
        finally:
            self.disconnect(client)
            try:
                client.conn.close()
            except OSError:
                pass
            print(f"Prekinuta veza: {client.address}")

    def handle_message(self, client: Client, message: dict) -> None:
        message_type = message.get("type")
        if message_type in ("register", "login") and client.username is None:
            username = str(message.get("username", "")).strip()
            password = str(message.get("password", ""))
            if message_type == "register":
                ok, info = create_user(username, password)
                if not ok:
                    client.send({"type": "auth_result", "ok": False, "message": info})
                    return
                user = authenticate(username, password)
            else:
                user = authenticate(username, password)
                if user is None:
                    client.send({
                        "type": "auth_result", "ok": False,
                        "message": "Pogrešan username ili lozinka."
                    })
                    return

            with self.lock:
                existing = self.active_users.get(user["username"].lower())
                if existing and existing.alive:
                    client.send({
                        "type": "auth_result", "ok": False,
                        "message": "Ovaj nalog je već prijavljen."
                    })
                    return
                client.username = user["username"]
                self.active_users[user["username"].lower()] = client
            client.send({
                "type": "auth_result", "ok": True,
                "username": user["username"], "wins": user["wins"],
                "leaderboard": leaderboard()
            })
            return

        if client.username is None:
            client.send({"type": "error", "message": "Prvo se prijavite."})
            return

        if message_type == "leaderboard":
            client.send({"type": "leaderboard", "items": leaderboard()})
        elif message_type == "find_game":
            self.find_game(client)
        elif message_type == "place_ships":
            self.place_ships(client, message.get("positions"))
        elif message_type == "attack":
            self.attack(client, message.get("row"), message.get("col"))
        elif message_type == "leave_queue":
            with self.lock:
                self.waiting = deque(c for c in self.waiting if c is not client)
            client.send({"type": "queue_left"})
        else:
            client.send({"type": "error", "message": "Nepoznata komanda."})

    def find_game(self, client: Client) -> None:
        with self.lock:
            if client.game is not None:
                client.send({"type": "error", "message": "Već ste u igri."})
                return
            if any(waiting is client for waiting in self.waiting):
                client.send({"type": "queue_status", "message": "Tražimo protivnika..."})
                return
            opponent = None
            while self.waiting:
                candidate = self.waiting.popleft()
                if candidate.alive and candidate.username and candidate is not client:
                    opponent = candidate
                    break
            if opponent is None:
                self.waiting.append(client)
                client.send({"type": "queue_status", "message": "Čekamo drugog igrača..."})
                return

            game = {
                "players": [opponent, client],
                "ships": [set(), set()],
                "ready": [False, False],
                "shots": [{}, {}],
                "turn": 0,
                "finished": False,
            }
            opponent.game = game
            opponent.player_index = 0
            client.game = game
            client.player_index = 1
            opponent.send({
                "type": "match_found", "opponent": client.username,
                "player_index": 0
            })
            client.send({
                "type": "match_found", "opponent": opponent.username,
                "player_index": 1
            })

    def place_ships(self, client: Client, raw_positions) -> None:
        with self.lock:
            game = client.game
            if not game or game["finished"]:
                client.send({"type": "error", "message": "Niste u aktivnoj partiji."})
                return
            index = client.player_index
            if game["ready"][index]:
                client.send({"type": "error", "message": "Brodovi su već postavljeni."})
                return
            try:
                positions = [tuple(position) for position in raw_positions]
                valid = (
                    len(positions) == SHIP_COUNT
                    and len(set(positions)) == SHIP_COUNT
                    and all(
                        len(position) == 2
                        and all(isinstance(value, int) and not isinstance(value, bool) for value in position)
                        and 0 <= position[0] < BOARD_SIZE
                        and 0 <= position[1] < BOARD_SIZE
                        for position in positions
                    )
                )
            except (TypeError, ValueError):
                valid = False
                positions = []
            if not valid:
                client.send({
                    "type": "error",
                    "message": f"Izaberite tačno {SHIP_COUNT} različitih polja na tabli."
                })
                return

            game["ships"][index] = set(positions)
            game["ready"][index] = True
            for player_index, player in enumerate(game["players"]):
                player.send({
                    "type": "placement_status",
                    "your_ready": game["ready"][player_index],
                    "opponent_ready": game["ready"][1 - player_index],
                })

            if all(game["ready"]):
                for player in game["players"]:
                    player.send({"type": "game_started"})
                self.send_turn(game)

    def attack(self, client: Client, row, col) -> None:
        with self.lock:
            game = client.game
            if not game or game["finished"]:
                client.send({"type": "error", "message": "Niste u aktivnoj partiji."})
                return
            index = client.player_index
            if not all(game["ready"]):
                client.send({"type": "error", "message": "Sačekajte da oba igrača postave brodove."})
                return
            if game["turn"] != index:
                client.send({"type": "error", "message": "Nije vaš potez."})
                return
            if not isinstance(row, int) or isinstance(row, bool) or not isinstance(col, int) or isinstance(col, bool) or not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
                client.send({"type": "error", "message": "Neispravna pozicija."})
                return
            position = (row, col)
            if position in game["shots"][index]:
                client.send({"type": "error", "message": "To polje ste već napali."})
                return

            opponent_index = 1 - index
            hit = position in game["ships"][opponent_index]
            game["shots"][index][position] = hit
            attacker = game["players"][index]
            defender = game["players"][opponent_index]
            attacker.send({"type": "attack_result", "row": row, "col": col, "hit": hit})
            defender.send({"type": "incoming_attack", "row": row, "col": col, "hit": hit})

            hits = sum(1 for result in game["shots"][index].values() if result)
            if hits == SHIP_COUNT:
                game["finished"] = True
                new_wins = increment_wins(attacker.username)
                attacker.send({
                    "type": "game_over", "winner": attacker.username,
                    "you_won": True, "wins": new_wins,
                    "leaderboard": leaderboard()
                })
                defender.send({
                    "type": "game_over", "winner": attacker.username,
                    "you_won": False, "wins": None,
                    "leaderboard": leaderboard()
                })
                self.clear_game(game)
                return

            game["turn"] = opponent_index
            self.send_turn(game)

    @staticmethod
    def send_turn(game: dict) -> None:
        for index, player in enumerate(game["players"]):
            player.send({"type": "turn_update", "your_turn": index == game["turn"]})

    @staticmethod
    def clear_game(game: dict) -> None:
        for player in game["players"]:
            player.game = None
            player.player_index = None

    def disconnect(self, client: Client) -> None:
        with self.lock:
            client.alive = False
            self.waiting = deque(c for c in self.waiting if c is not client)
            if client.username:
                key = client.username.lower()
                if self.active_users.get(key) is client:
                    del self.active_users[key]
            game = client.game
            if game and not game["finished"]:
                game["finished"] = True
                opponent = game["players"][1 - client.player_index]
                if opponent.alive:
                    opponent.send({
                        "type": "opponent_disconnected",
                        "message": f"{client.username or 'Protivnik'} je prekinuo vezu. Partija je završena bez pobede."
                    })
                self.clear_game(game)


if __name__ == "__main__":
    try:
        BattleshipServer().run()
    except KeyboardInterrupt:
        print("\nServer je zaustavljen.")
