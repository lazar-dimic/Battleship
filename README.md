# Battleship Online

Online, two-player version of Battleship made with Python, Tkinter, TCP sockets and SQLite.

## Features

- User registration and login.
- Passwords stored as PBKDF2-HMAC-SHA256 hashes with individual random salts.
- Automatic matchmaking: players who press **Pronađi protivnika** are paired.
- Each player places 5 ships on a 6x6 board.
- Server validates ship placement, turns and attacks.
- Hit/miss history is displayed on both clients.
- The winner's account receives one additional win.
- Top 10 leaderboard.
- Optional TLS support for a publicly hosted server.

## Requirements

- Python 3.10 or newer recommended.
- Tkinter (usually included with Python on Windows).
- No third-party Python packages.

## Run locally (two players on one computer)

1. Open a terminal in this folder.
2. Start the server:

   ```bash
   python server.py
   ```

3. Open two more terminals in the same folder and run the client in each:

   ```bash
   python client.py
   ```

4. In both clients, leave the server address as `127.0.0.1` and port as `5000`.
5. Register two different accounts, log in, and press **Pronađi protivnika** in both windows.

The server creates `battleship.db` automatically. Keep this file on the server; it contains account records and win statistics.

## Play over the internet

The server must run on a computer that is reachable by both players. A typical setup is a VPS or cloud virtual machine with a public IP address or domain name.

1. Copy `server.py` to the VPS and install Python 3.10+.
2. Start the server there:

   python server.py

3. Allow inbound TCP traffic to port `5000` in the VPS firewall / cloud firewall. For a production setup, use a non-default port if appropriate.
4. Each player runs `client.py` on their own computer and enters the VPS public IP address or domain instead of `127.0.0.1`.
5. Both players use the same port configured by the server (default `5000`).

**Important security note:** the default connection is not encrypted. Do not use real or reused passwords over an untrusted public network with TLS turned off. For public deployment, configure a valid TLS certificate and private key on the server, then enable the TLS checkbox in each client. For example, with certificate files from Let's Encrypt:

Linux/macOS:

export BATTLESHIP_TLS_CERT=/etc/letsencrypt/live/your-domain/fullchain.pem
export BATTLESHIP_TLS_KEY=/etc/letsencrypt/live/your-domain/privkey.pem
python server.py


The client must connect using the domain name that is covered by the certificate and check **Koristi TLS enkripciju**. The client uses the operating system's trusted certificate authorities.

## Rules

- Board size: 6x6.
- Each player places exactly 5 ships on different cells.
- Players alternate turns after every attack.
- Green `X` means a hit; red `O` means a miss.
- The first player to hit all 5 opponent ships wins.
- Disconnecting during a game ends the game without awarding a win.

## Project files

- `server.py` — accounts, database, matchmaking and authoritative game rules.
- `client.py` — Tkinter user interface and network client.
- `main.py` — alternative entry point for launching the client (`python main.py`).
- `battleship.db` — created automatically by the server when it first starts.

## Notes

This is a small educational multiplayer project, not a hardened commercial game service. For larger deployments, add rate limiting, stronger abuse controls, logging, backups and operational monitoring.
