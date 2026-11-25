"""Tkinter client for the online Battleship game.

Run: python client.py
"""

from __future__ import annotations

import json
import queue
import socket
import ssl
import threading
import tkinter as tk
from tkinter import messagebox

BOARD_SIZE = 6
SHIP_COUNT = 5
DEFAULT_PORT = 5000


class BattleshipClient:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Battleship Online")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.sock = None
        self.send_lock = threading.Lock()
        self.incoming = queue.Queue()
        self.username = None
        self.wins = 0
        self.player_index = None
        self.opponent = None
        self.selected_ships = set()
        self.own_shots = {}
        self.enemy_shots = {}
        self.phase = "auth"
        self.your_turn = False
        self.tls_var = tk.BooleanVar(value=False)

        self.container = tk.Frame(root, padx=18, pady=18)
        self.container.pack()
        self.show_auth()
        self.root.after(100, self.process_messages)

    def clear(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def show_auth(self):
        self.phase = "auth"
        self.clear()
        tk.Label(self.container, text="BATTLESHIP ONLINE", font=("Arial", 21, "bold")).pack(pady=(0, 16))

        tk.Label(self.container, text="Adresa servera (IP ili domen):").pack(anchor="w")
        self.host_entry = tk.Entry(self.container, width=34)
        self.host_entry.insert(0, "127.0.0.1")
        self.host_entry.pack(pady=(2, 8))

        tk.Label(self.container, text="Port:").pack(anchor="w")
        self.port_entry = tk.Entry(self.container, width=34)
        self.port_entry.insert(0, str(DEFAULT_PORT))
        self.port_entry.pack(pady=(2, 8))

        tk.Checkbutton(
            self.container,
            text="Koristi TLS enkripciju (za server sa validnim SSL sertifikatom)",
            variable=self.tls_var,
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(self.container, text="Username:").pack(anchor="w")
        self.username_entry = tk.Entry(self.container, width=34)
        self.username_entry.pack(pady=(2, 8))

        tk.Label(self.container, text="Lozinka:").pack(anchor="w")
        self.password_entry = tk.Entry(self.container, width=34, show="*")
        self.password_entry.pack(pady=(2, 12))
        self.password_entry.bind("<Return>", lambda _event: self.login())

        buttons = tk.Frame(self.container)
        buttons.pack()
        tk.Button(buttons, text="Prijavi se", width=14, command=self.login).grid(row=0, column=0, padx=5)
        tk.Button(buttons, text="Registruj se", width=14, command=self.register).grid(row=0, column=1, padx=5)

        tk.Label(
            self.container,
            text="Username: 3–20 karaktera. Lozinka: najmanje 8 karaktera.",
            font=("Arial", 9), fg="gray"
        ).pack(pady=(12, 0))
        self.auth_status = tk.Label(self.container, text="", fg="firebrick", wraplength=340)
        self.auth_status.pack(pady=(8, 0))

    def connect(self) -> bool:
        if self.sock is not None:
            return True
        host = self.host_entry.get().strip()
        try:
            port = int(self.port_entry.get().strip())
            if not host or not 1 <= port <= 65535:
                raise ValueError
            connection = socket.create_connection((host, port), timeout=8)
            connection.settimeout(None)
            if self.tls_var.get():
                context = ssl.create_default_context()
                connection = context.wrap_socket(connection, server_hostname=host)
            self.sock = connection
            threading.Thread(target=self.receive_loop, daemon=True).start()
            return True
        except (ValueError, OSError, ssl.SSLError) as error:
            self.auth_status.config(text=f"Nije moguće povezivanje sa serverom: {error}")
            return False

    def send(self, message: dict):
        if not self.sock:
            return
        try:
            data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
            with self.send_lock:
                self.sock.sendall(data)
        except OSError:
            self.incoming.put({"type": "connection_lost"})

    def receive_loop(self):
        buffer = b""
        try:
            while self.sock:
                data = self.sock.recv(4096)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if line:
                        try:
                            self.incoming.put(json.loads(line.decode("utf-8")))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            self.incoming.put({"type": "error", "message": "Server je poslao neispravnu poruku."})
        except OSError:
            pass
        finally:
            self.incoming.put({"type": "connection_lost"})

    def login(self):
        self.authenticate("login")

    def register(self):
        self.authenticate("register")

    def authenticate(self, action: str):
        if not self.connect():
            return
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            self.auth_status.config(text="Unesite username i lozinku.")
            return
        self.auth_status.config(text="Povezivanje...")
        self.send({"type": action, "username": username, "password": password})

    def show_lobby(self):
        self.phase = "lobby"
        self.clear()
        tk.Label(self.container, text=f"Zdravo, {self.username}!", font=("Arial", 19, "bold")).pack(pady=(0, 5))
        self.wins_label = tk.Label(self.container, text=f"Broj pobeda: {self.wins}", font=("Arial", 12))
        self.wins_label.pack(pady=(0, 15))
        tk.Label(self.container, text="Online multiplayer", font=("Arial", 13, "bold")).pack()
        tk.Button(self.container, text="Pronađi protivnika", width=24, command=self.find_game).pack(pady=10)
        tk.Button(self.container, text="Osveži rang-listu", width=24, command=lambda: self.send({"type": "leaderboard"})).pack(pady=3)
        tk.Label(self.container, text="TOP 10 IGRAČA", font=("Arial", 11, "bold")).pack(pady=(14, 4))
        self.leaderboard_text = tk.Label(self.container, text="Učitavanje...", justify="left", font=("Consolas", 10))
        self.leaderboard_text.pack()
        tk.Button(self.container, text="Odjavi se", width=24, command=self.logout).pack(pady=(14, 0))
        self.send({"type": "leaderboard"})

    def find_game(self):
        self.phase = "queue"
        self.clear()
        tk.Label(self.container, text="Traženje protivnika", font=("Arial", 18, "bold")).pack(pady=(5, 15))
        self.queue_status = tk.Label(self.container, text="Povezivanje sa drugim igračem...", font=("Arial", 11))
        self.queue_status.pack(pady=8)
        tk.Button(self.container, text="Odustani", width=18, command=self.cancel_queue).pack(pady=12)
        self.send({"type": "find_game"})

    def cancel_queue(self):
        self.send({"type": "leave_queue"})
        self.show_lobby()

    def show_game(self):
        self.phase = "placement"
        self.selected_ships = set()
        self.own_shots = {}
        self.enemy_shots = {}
        self.your_turn = False
        self.clear()
        self.game_title = tk.Label(self.container, text=f"Protivnik: {self.opponent}", font=("Arial", 15, "bold"))
        self.game_title.pack(pady=(0, 5))
        self.game_status = tk.Label(
            self.container, text=f"Postavite {SHIP_COUNT} brodova na svoju tablu (0/{SHIP_COUNT}).",
            font=("Arial", 10), wraplength=470
        )
        self.game_status.pack(pady=(0, 10))

        boards = tk.Frame(self.container)
        boards.pack()
        self.own_frame = tk.LabelFrame(boards, text="Vaša tabla", padx=7, pady=7)
        self.own_frame.grid(row=0, column=0, padx=6)
        self.enemy_frame = tk.LabelFrame(boards, text="Protivnikova tabla", padx=7, pady=7)
        self.enemy_frame.grid(row=0, column=1, padx=6)
        self.own_buttons = []
        self.enemy_buttons = []
        for row in range(BOARD_SIZE):
            own_row, enemy_row = [], []
            for col in range(BOARD_SIZE):
                own = tk.Button(
                    self.own_frame, text="~", width=3, height=1, bg="lightblue",
                    command=lambda r=row, c=col: self.select_ship(r, c)
                )
                own.grid(row=row, column=col, padx=1, pady=1)
                enemy = tk.Button(
                    self.enemy_frame, text="~", width=3, height=1, bg="lightblue",
                    state="disabled", command=lambda r=row, c=col: self.attack(r, c)
                )
                enemy.grid(row=row, column=col, padx=1, pady=1)
                own_row.append(own)
                enemy_row.append(enemy)
            self.own_buttons.append(own_row)
            self.enemy_buttons.append(enemy_row)
        self.enemy_frame.grid_remove()
        tk.Label(self.container, text="Zeleno = pogodak     Crveno = promašaj", font=("Arial", 9)).pack(pady=(8, 0))

    def select_ship(self, row: int, col: int):
        if self.phase != "placement" or len(self.selected_ships) >= SHIP_COUNT:
            return
        position = (row, col)
        if position in self.selected_ships:
            return
        self.selected_ships.add(position)
        self.own_buttons[row][col].config(text="S", bg="gray", state="disabled")
        self.game_status.config(text=f"Postavite brodove: {len(self.selected_ships)}/{SHIP_COUNT}.")
        if len(self.selected_ships) == SHIP_COUNT:
            self.phase = "waiting_ready"
            self.game_status.config(text="Brodovi su postavljeni. Čekamo da protivnik završi... ")
            self.send({"type": "place_ships", "positions": [list(pos) for pos in sorted(self.selected_ships)]})
            for row_buttons in self.own_buttons:
                for button in row_buttons:
                    button.config(state="disabled")

    def attack(self, row: int, col: int):
        if self.phase != "playing" or not self.your_turn:
            return
        if (row, col) in self.enemy_shots:
            return
        for row_buttons in self.enemy_buttons:
            for button in row_buttons:
                button.config(state="disabled")
        self.game_status.config(text="Napad je poslat serveru...")
        self.send({"type": "attack", "row": row, "col": col})

    def refresh_turn_buttons(self):
        if self.phase != "playing":
            return
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                already_shot = (row, col) in self.enemy_shots
                self.enemy_buttons[row][col].config(
                    state="normal" if self.your_turn and not already_shot else "disabled"
                )
        self.game_status.config(text="Vaš potez — izaberite polje." if self.your_turn else "Potez protivnika — sačekajte...")

    def update_leaderboard(self, items):
        if not hasattr(self, "leaderboard_text") or not self.leaderboard_text.winfo_exists():
            return
        if not items:
            self.leaderboard_text.config(text="Još nema rezultata.")
            return
        lines = [f"{index:>2}. {item['username']:<20} {item['wins']:>3} pob." for index, item in enumerate(items, 1)]
        self.leaderboard_text.config(text="\n".join(lines))

    def handle_message(self, message: dict):
        message_type = message.get("type")
        if message_type == "auth_result":
            if not message.get("ok"):
                if hasattr(self, "auth_status") and self.auth_status.winfo_exists():
                    self.auth_status.config(text=message.get("message", "Greška pri prijavi."))
                return
            self.username = message["username"]
            self.wins = message.get("wins", 0)
            self.show_lobby()
            self.update_leaderboard(message.get("leaderboard", []))

        elif message_type == "leaderboard":
            self.update_leaderboard(message.get("items", []))

        elif message_type == "queue_status":
            if self.phase == "queue":
                self.queue_status.config(text=message.get("message", "Tražimo protivnika..."))

        elif message_type == "match_found":
            self.opponent = message.get("opponent", "Protivnik")
            self.player_index = message.get("player_index")
            self.show_game()

        elif message_type == "placement_status":
            if self.phase in ("placement", "waiting_ready") and message.get("your_ready") and not message.get("opponent_ready"):
                self.game_status.config(text="Vaši brodovi su postavljeni. Čekamo protivnika...")

        elif message_type == "game_started":
            self.phase = "playing"
            self.own_frame.grid()
            self.enemy_frame.grid()
            self.game_status.config(text="Partija je počela. Čekamo potez servera...")

        elif message_type == "turn_update":
            self.your_turn = bool(message.get("your_turn"))
            if self.phase != "finished":
                self.phase = "playing"
                self.refresh_turn_buttons()

        elif message_type == "attack_result":
            row, col = message["row"], message["col"]
            hit = bool(message["hit"])
            self.enemy_shots[(row, col)] = hit
            self.enemy_buttons[row][col].config(
                text="X" if hit else "O", bg="green" if hit else "red", state="disabled"
            )

        elif message_type == "incoming_attack":
            row, col = message["row"], message["col"]
            hit = bool(message["hit"])
            self.own_shots[(row, col)] = hit
            self.own_buttons[row][col].config(
                text="X" if hit else "O", bg="green" if hit else "red", state="disabled"
            )

        elif message_type == "game_over":
            self.phase = "finished"
            self.your_turn = False
            if message.get("you_won"):
                self.wins = message.get("wins", self.wins + 1)
                result = f"Čestitamo! Pobeda protiv igrača {self.opponent}."
            else:
                result = f"Izgubili ste. Pobednik je {message.get('winner', self.opponent)}."
            self.show_game_over(result, message.get("leaderboard", []))

        elif message_type == "opponent_disconnected":
            self.phase = "finished"
            self.show_game_over(message.get("message", "Protivnik je prekinuo vezu."), [])

        elif message_type == "queue_left":
            if self.phase == "queue":
                self.show_lobby()

        elif message_type == "connection_lost":
            if self.phase != "closed":
                self.sock = None
                self.phase = "auth"
                self.show_auth()
                self.auth_status.config(text="Veza sa serverom je prekinuta. Povežite se ponovo.")

        elif message_type == "error":
            text = message.get("message", "Došlo je do greške.")
            if self.phase in ("placement", "waiting_ready", "playing") and hasattr(self, "game_status"):
                self.game_status.config(text=text)
            elif self.phase == "queue" and hasattr(self, "queue_status"):
                self.queue_status.config(text=text)
            elif hasattr(self, "auth_status") and self.auth_status.winfo_exists():
                self.auth_status.config(text=text)

    def show_game_over(self, result: str, items):
        self.clear()
        self.phase = "finished"
        tk.Label(self.container, text="KRAJ PARTIJE", font=("Arial", 20, "bold")).pack(pady=(8, 12))
        tk.Label(self.container, text=result, font=("Arial", 12), wraplength=400).pack(pady=6)
        tk.Label(self.container, text=f"Vaš ukupan broj pobeda: {self.wins}", font=("Arial", 11, "bold")).pack(pady=8)
        tk.Button(self.container, text="Nazad u meni", width=22, command=self.show_lobby).pack(pady=10)
        if items:
            tk.Label(self.container, text="Rang-lista je ažurirana.", fg="gray").pack()

    def logout(self):
        self.disconnect_socket()
        self.username = None
        self.wins = 0
        self.show_auth()

    def disconnect_socket(self):
        connection = self.sock
        self.sock = None
        if connection:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass

    def process_messages(self):
        try:
            while True:
                message = self.incoming.get_nowait()
                self.handle_message(message)
        except queue.Empty:
            pass
        if self.phase != "closed":
            self.root.after(100, self.process_messages)

    def close(self):
        self.phase = "closed"
        self.disconnect_socket()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    BattleshipClient(root)
    root.mainloop()
