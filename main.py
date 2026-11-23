
import tkinter as tk
from tkinter import messagebox

SIZE = 6
SHIP_COUNT = 5


class Battleship:

    def __init__(self, root):
        self.root = root
        self.root.title("Battleship")
        self.root.resizable(False, False)

        self.players = ["Player 1", "Player 2"]

        self.ships = [set(), set()]
        self.shots = [{}, {}]

        self.current_player = 0
        self.phase = "placement"
        self.placed = 0

        self.own_buttons = []
        self.enemy_buttons = []

        self.info = tk.Label(
            root,
            text="Player 1: Place your ships (0/5)",
            font=("Arial", 15, "bold")
        )
        self.info.pack(pady=15)

        self.main_frame = tk.Frame(root)
        self.main_frame.pack(padx=15, pady=10)

        self.own_frame = tk.LabelFrame(
            self.main_frame,
            text="Your ships",
            font=("Arial", 11, "bold"),
            padx=10,
            pady=10
        )
        self.own_frame.grid(row=0, column=0, padx=10)

        self.enemy_frame = tk.LabelFrame(
            self.main_frame,
            text="Enemy board",
            font=("Arial", 11, "bold"),
            padx=10,
            pady=10
        )
        self.enemy_frame.grid(row=0, column=1, padx=10)

        self.create_boards()

        self.status = tk.Label(
            root,
            text="Click 5 different cells to place your ships.",
            font=("Arial", 10)
        )
        self.status.pack(pady=10)

        self.start_placement()

    def create_boards(self):

        for row in range(SIZE):
            own_row = []
            enemy_row = []

            for col in range(SIZE):

                own_button = tk.Button(
                    self.own_frame,
                    text="~",
                    width=4,
                    height=2,
                    bg="lightblue",
                    state="disabled"
                )
                own_button.grid(row=row, column=col, padx=2, pady=2)
                own_row.append(own_button)

                enemy_button = tk.Button(
                    self.enemy_frame,
                    text="~",
                    width=4,
                    height=2,
                    bg="lightblue",
                    command=lambda r=row, c=col: self.attack(r, c)
                )
                enemy_button.grid(row=row, column=col, padx=2, pady=2)
                enemy_row.append(enemy_button)

            self.own_buttons.append(own_row)
            self.enemy_buttons.append(enemy_row)

    def start_placement(self):

        self.enemy_frame.grid_remove()

        for row in range(SIZE):
            for col in range(SIZE):
                self.own_buttons[row][col].config(
                    state="normal",
                    command=lambda r=row, c=col: self.place_ship(r, c)
                )

    def place_ship(self, row, col):

        player = self.current_player
        position = (row, col)

        if position in self.ships[player]:
            return

        self.ships[player].add(position)
        self.placed += 1

        self.own_buttons[row][col].config(
            text="S",
            bg="gray"
        )

        self.info.config(
            text=f"{self.players[player]}: Place ships ({self.placed}/5)"
        )

        if self.placed == SHIP_COUNT:

            if player == 0:
                self.status.config(
                    text="Player 1 finished. Passing to Player 2..."
                )

                self.root.after(2000, self.start_player_two)

            else:
                self.phase = "playing"
                self.current_player = 0

                self.root.after(2000, self.prepare_turn)

    def start_player_two(self):

        self.current_player = 1
        self.placed = 0

        for row in range(SIZE):
            for col in range(SIZE):
                self.own_buttons[row][col].config(
                    text="~",
                    bg="lightblue",
                    state="normal",
                    command=lambda r=row, c=col: self.place_ship(r, c)
                )

        self.info.config(
            text="Player 2: Place your ships (0/5)"
        )

        self.status.config(
            text="Click 5 different cells to place your ships."
        )

    def prepare_turn(self):

        player = self.current_player

        self.own_frame.grid()
        self.enemy_frame.grid()

        self.info.config(
            text=f"{self.players[player]}'s turn"
        )

        self.status.config(
            text="Choose a position on the enemy board."
        )

        for row in range(SIZE):
            for col in range(SIZE):

                position = (row, col)

                if position in self.ships[player]:
                    self.own_buttons[row][col].config(
                        text="S",
                        bg="gray",
                        state="disabled"
                    )
                else:
                    self.own_buttons[row][col].config(
                        text="~",
                        bg="lightblue",
                        state="disabled"
                    )

                if position in self.shots[player]:

                    result = self.shots[player][position]

                    if result == "X":
                        self.enemy_buttons[row][col].config(
                            text="X",
                            bg="green",
                            state="disabled"
                        )
                    else:
                        self.enemy_buttons[row][col].config(
                            text="O",
                            bg="red",
                            state="disabled"
                        )

                else:
                    self.enemy_buttons[row][col].config(
                        text="~",
                        bg="lightblue",
                        state="normal"
                    )

    def attack(self, row, col):

        if self.phase != "playing":
            return

        player = self.current_player
        opponent = 1 - player

        position = (row, col)

        if position in self.shots[player]:
            return

        if position in self.ships[opponent]:

            self.shots[player][position] = "X"

            self.enemy_buttons[row][col].config(
                text="X",
                bg="green",
                state="disabled"
            )

            self.status.config(text="HIT!")

        else:

            self.shots[player][position] = "O"

            self.enemy_buttons[row][col].config(
                text="O",
                bg="red",
                state="disabled"
            )

            self.status.config(text="MISS!")

        hits = list(self.shots[player].values()).count("X")

        if hits == SHIP_COUNT:

            self.phase = "finished"

            messagebox.showinfo(
                "Game Over",
                f"{self.players[player]} wins!"
            )

            self.root.destroy()
            return

        self.phase = "switching"

        self.root.after(2000, self.switch_player)

    def switch_player(self):

        self.current_player = 1 - self.current_player

        self.own_frame.grid_remove()
        self.enemy_frame.grid_remove()

        self.info.config(
            text=f"Pass the computer to {self.players[self.current_player]}"
        )

        self.status.config(
            text="Next player's turn will start shortly..."
        )

        self.root.after(2000, self.prepare_next_turn)

    def prepare_next_turn(self):

        self.phase = "playing"
        self.prepare_turn()


root = tk.Tk()
game = Battleship(root)
root.mainloop()
