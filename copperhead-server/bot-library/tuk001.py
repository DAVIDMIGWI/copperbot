#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
TUK001 — CopperHead tournament bot.

Strategy
--------
1. Danger map from snake bodies (tails excluded), same as CopperBot/Pathfinder.
2. BFS shortest path to prioritized food (apples slightly preferred); take first step.
3. If no path, score safe moves by flood-fill reachability, food pickup, head-on
   prediction (difficulty-scaled), and a center-of-arena bias — TUK001 prefers
   staying in open central space; that bias scales up with difficulty.
4. Occasional mistakes at low difficulty (noise on scores / path follow).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from collections import deque

import websockets


DIRS = ("up", "down", "left", "right")
DIR_VEC = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}
OPPOSITES = {"up": "down", "down": "up", "left": "right", "right": "left"}


def bfs_path(
    start: tuple[int, int],
    goal: tuple[int, int],
    dangerous: set[tuple[int, int]],
    width: int,
    height: int,
) -> list[tuple[int, int]] | None:
    if start == goal:
        return [start]

    q: deque[tuple[int, int]] = deque([start])
    came: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    while q:
        x, y = q.popleft()
        for d in DIRS:
            dx, dy = DIR_VEC[d]
            nx, ny = x + dx, y + dy
            if nx < 0 or nx >= width or ny < 0 or ny >= height:
                continue
            if (nx, ny) in dangerous:
                continue
            if (nx, ny) in came:
                continue
            came[(nx, ny)] = (x, y)
            if (nx, ny) == goal:
                out: list[tuple[int, int]] = [goal]
                cur = (x, y)
                while cur is not None:
                    out.append(cur)
                    cur = came[cur]
                out.reverse()
                return out
            q.append((nx, ny))

    return None


def flood_reachable(
    start: tuple[int, int],
    dangerous: set[tuple[int, int]],
    width: int,
    height: int,
    cap: int = 150,
) -> int:
    if start[0] < 0 or start[0] >= width or start[1] < 0 or start[1] >= height:
        return 0
    if start in dangerous:
        return 0

    q: deque[tuple[int, int]] = deque([start])
    seen = {start}
    while q and len(seen) < cap:
        x, y = q.popleft()
        for d in DIRS:
            dx, dy = DIR_VEC[d]
            nx, ny = x + dx, y + dy
            if nx < 0 or nx >= width or ny < 0 or ny >= height:
                continue
            if (nx, ny) in dangerous or (nx, ny) in seen:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return len(seen)


class TUK001:
    """TUK001: BFS to food, flood-fill fallback, center-weighted scoring."""

    def __init__(
        self,
        server_url: str,
        name: str | None = None,
        difficulty: int = 5,
        quiet: bool = False,
        skip_wait: bool = False,
    ):
        self.server_url = server_url
        self.name = name or "TUK001"
        self.difficulty = max(1, min(10, difficulty))
        self.quiet = quiet
        self.skip_wait = skip_wait
        self.player_id = None
        self.game_state = None
        self.running = False
        self.wins = 0
        self.games_played = 0
        self.room_id = None
        self.grid_width = 30
        self.grid_height = 20

    def log(self, msg: str) -> None:
        if not self.quiet:
            print(msg.encode("ascii", errors="replace").decode("ascii"))

    async def wait_for_open_competition(self) -> None:
        import aiohttp

        base_url = self.server_url.rstrip("/")
        if base_url.endswith("/ws"):
            base_url = base_url[:-3]
        http_url = base_url.replace("ws://", "http://").replace("wss://", "https://")

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{http_url}/status") as resp:
                        if resp.status == 200:
                            self.log("Server reachable - joining lobby...")
                            return
                        self.log(f"Server not ready (status {resp.status}), waiting...")
            except Exception as e:
                self.log(f"Cannot reach server: {e}, waiting...")

            await asyncio.sleep(5)

    async def connect(self) -> bool:
        if not self.skip_wait:
            await self.wait_for_open_competition()

        base_url = self.server_url.rstrip("/")
        if base_url.endswith("/ws"):
            base_url = base_url[:-3]
        url = f"{base_url}/ws/join"

        try:
            self.log(f"Connecting to {url}...")
            self.ws = await websockets.connect(url)
            self.log("Connected! Waiting for player assignment...")
            return True
        except Exception as e:
            self.log(f"Connection failed: {e}")
            return False

    async def play(self) -> None:
        if not await self.connect():
            self.log("Failed to connect to server. Exiting.")
            return

        self.running = True
        await self.ws.send(json.dumps({"action": "join", "name": self.name}))

        try:
            while self.running:
                message = await self.ws.recv()
                data = json.loads(message)
                await self.handle_message(data)
        except websockets.ConnectionClosed:
            self.log("Connection closed.")
        except Exception as e:
            self.log(f"Error: {e}")
        finally:
            self.running = False
            try:
                await self.ws.close()
            except Exception:
                pass
            self.log("Bot stopped.")

    async def handle_message(self, data: dict) -> None:
        msg_type = data.get("type")

        if msg_type == "error":
            self.log(f"Server error: {data.get('message', 'Unknown error')}")
            self.running = False
            return

        if msg_type == "lobby_joined":
            self.log(f"Joined lobby as '{data.get('name', self.name)}'")
            return

        if msg_type == "lobby_update":
            return

        if msg_type == "lobby_left":
            self.log("Left the lobby.")
            self.running = False
            return

        if msg_type == "lobby_kicked":
            self.log("Kicked from lobby!")
            self.running = False
            return

        if msg_type == "joined":
            self.player_id = data.get("player_id")
            self.room_id = data.get("room_id")
            self.log(f"Joined Room {self.room_id} as Player {self.player_id}")
            self.log(f"Ready! Playing as '{self.name}' at difficulty {self.difficulty}")

        elif msg_type == "state":
            self.game_state = data.get("game")
            grid = (self.game_state or {}).get("grid", {})
            if grid:
                self.grid_width = grid.get("width", self.grid_width)
                self.grid_height = grid.get("height", self.grid_height)
            if self.game_state and self.game_state.get("running"):
                direction = self.calculate_move()
                if direction:
                    await self.ws.send(json.dumps({"action": "move", "direction": direction}))

        elif msg_type == "start":
            self.log("Game started!")

        elif msg_type == "gameover":
            self.games_played += 1
            winner = data.get("winner")
            my_wins = data.get("wins", {}).get(str(self.player_id), 0) or data.get("wins", {}).get(
                self.player_id, 0
            )
            opp_id = 3 - self.player_id
            opp_wins = data.get("wins", {}).get(str(opp_id), 0) or data.get("wins", {}).get(opp_id, 0)
            points_to_win = data.get("points_to_win", 5)

            if winner == self.player_id:
                self.wins += 1
                self.log(f"Won game! (Match: {my_wins}-{opp_wins}, first to {points_to_win})")
            elif winner:
                self.log(f"Lost game! (Match: {my_wins}-{opp_wins}, first to {points_to_win})")
            else:
                self.log(f"Draw! (Match: {my_wins}-{opp_wins}, first to {points_to_win})")

            await self.ws.send(json.dumps({"action": "ready", "name": self.name}))
            self.log("Ready for next game...")

        elif msg_type == "match_complete":
            winner_id = data.get("winner", {}).get("player_id")
            winner_name = data.get("winner", {}).get("name", "Unknown")
            final_score = data.get("final_score", {})
            my_score = final_score.get(str(self.player_id), 0) or final_score.get(self.player_id, 0)
            opp_id = 3 - self.player_id
            opp_score = final_score.get(str(opp_id), 0) or final_score.get(opp_id, 0)

            if winner_id == self.player_id:
                self.log(f"Match won! Final: {my_score}-{opp_score}")
                self.log("Waiting for next round assignment...")
            else:
                self.log(f"Match lost to {winner_name}. Final: {my_score}-{opp_score}")
                self.log("Exiting.")
                self.running = False

        elif msg_type == "match_assigned":
            self.room_id = data.get("room_id")
            self.player_id = data.get("player_id")
            self.game_state = None
            opponent = data.get("opponent", "Opponent")
            self.log(f"Assigned to Arena {self.room_id} as Player {self.player_id} vs {opponent}")
            await self.ws.send(json.dumps({"action": "ready", "name": self.name}))

        elif msg_type == "competition_complete":
            champion = data.get("champion", {}).get("name", "Unknown")
            self.log(f"Competition complete! Champion: {champion}")
            self.log("Exiting.")
            self.running = False

        elif msg_type == "waiting":
            self.log("Waiting for opponent...")

    def _foods(self) -> list[dict]:
        foods = (self.game_state or {}).get("foods", [])
        if not foods and (self.game_state or {}).get("food"):
            old_food = self.game_state.get("food")
            foods = [{"x": old_food[0], "y": old_food[1], "type": "apple"}]
        return foods

    def _dangerous(self, snakes: dict) -> set[tuple[int, int]]:
        dangerous: set[tuple[int, int]] = set()
        for snake_data in snakes.values():
            body = snake_data.get("body", [])
            for segment in body[:-1]:
                dangerous.add((segment[0], segment[1]))
        return dangerous

    def _head_on_score(self, new_x: int, new_y: int, my_len: int, opp_len: int, opp_next) -> float:
        if not opp_next or (new_x, new_y) != opp_next:
            return 0.0
        collision_bonus = 2000.0
        collision_penalty = -5000.0
        d = self.difficulty
        if d == 1:
            return collision_penalty
        if d <= 5:
            avoid_prob = 0.9 - (d - 2) * 0.8 / 3
            return collision_penalty if random.random() < avoid_prob else collision_bonus
        if d <= 9:
            prioritize_prob = 0.1 + (d - 6) * 0.8 / 3
            if my_len > opp_len and random.random() < prioritize_prob:
                return collision_bonus
            return collision_penalty
        return collision_bonus if my_len > opp_len else collision_penalty

    def _center_score(self, x: int, y: int, w: int, h: int) -> float:
        """Higher when closer to map center; weight scales with difficulty."""
        cx = (w - 1) / 2.0
        cy = (h - 1) / 2.0
        manhattan = abs(x - cx) + abs(y - cy)
        max_m = cx + cy + 0.01
        closeness = max_m - manhattan
        return closeness * (self.difficulty / 10.0) * 6.0

    def calculate_move(self) -> str | None:
        if not self.game_state:
            return None

        snakes = self.game_state.get("snakes", {})
        my_snake = snakes.get(str(self.player_id)) or snakes.get(self.player_id)
        if not my_snake or not my_snake.get("body"):
            return None

        head = (my_snake["body"][0][0], my_snake["body"][0][1])
        current_dir = my_snake.get("direction", "right")
        my_len = len(my_snake.get("body", []))

        dangerous = self._dangerous(snakes)
        w, h = self.grid_width, self.grid_height

        opponent_id = 3 - self.player_id
        opponent = snakes.get(str(opponent_id)) or snakes.get(opponent_id)
        opp_next = None
        opp_len = 0
        if opponent and opponent.get("body"):
            oh = opponent["body"][0]
            od = opponent.get("direction", "left")
            dx, dy = DIR_VEC.get(od, (0, 0))
            opp_next = (oh[0] + dx, oh[1] + dy)
            opp_len = len(opponent.get("body", []))

        foods = self._foods()

        def food_key(f: dict) -> tuple[float, int]:
            dist = abs(head[0] - f["x"]) + abs(head[1] - f["y"])
            if f.get("type") == "apple":
                dist -= 0.5
            return (dist, f["x"] + f["y"])

        foods_sorted = sorted(foods, key=food_key)

        path_first_step: str | None = None
        for food in foods_sorted:
            goal = (food["x"], food["y"])
            path = bfs_path(head, goal, dangerous, w, h)
            if path and len(path) >= 2:
                step = path[1]
                sdx, sdy = step[0] - head[0], step[1] - head[1]
                for dir_name, (vx, vy) in DIR_VEC.items():
                    if (vx, vy) == (sdx, sdy) and dir_name != OPPOSITES.get(current_dir):
                        path_first_step = dir_name
                        break
                if path_first_step:
                    break

        safe_moves: list[dict] = []
        for d in DIRS:
            if d == OPPOSITES.get(current_dir):
                continue
            dx, dy = DIR_VEC[d]
            nx, ny = head[0] + dx, head[1] + dy
            if nx < 0 or nx >= w or ny < 0 or ny >= h:
                continue
            if (nx, ny) in dangerous:
                continue
            safe_moves.append({"direction": d, "x": nx, "y": ny})

        if not safe_moves:
            for d in DIRS:
                if d != OPPOSITES.get(current_dir):
                    return d
            return current_dir

        mistake_chance = (10 - self.difficulty) / 20

        def score_move(m: dict) -> float:
            s = 0.0
            s += self._head_on_score(m["x"], m["y"], my_len, opp_len, opp_next)
            s += flood_reachable((m["x"], m["y"]), dangerous, w, h) * 3.5
            s += self._center_score(m["x"], m["y"], w, h)
            for f in foods:
                if m["x"] == f["x"] and m["y"] == f["y"]:
                    s += 1000.0
                    break
            if random.random() < mistake_chance:
                s -= random.randint(0, 30)
            return s

        if path_first_step and any(m["direction"] == path_first_step for m in safe_moves):
            if random.random() >= mistake_chance:
                return path_first_step

        scored = [(score_move(m), m["direction"]) for m in safe_moves]
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[0][1]


async def main() -> None:
    parser = argparse.ArgumentParser(description="TUK001 — CopperHead bot")
    parser.add_argument(
        "--server",
        "-s",
        default="ws://localhost:8765/ws/",
        help="Server WebSocket URL (default: ws://localhost:8765/ws/)",
    )
    parser.add_argument("--name", "-n", default=None, help="Bot display name (default: TUK001)")
    parser.add_argument("--difficulty", "-d", type=int, default=5, help="AI difficulty 1-10 (default: 5)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    parser.add_argument("--skip-wait", action="store_true", help="Skip HTTP reachability check")
    args = parser.parse_args()

    bot = TUK001(
        args.server,
        name=args.name,
        difficulty=args.difficulty,
        quiet=args.quiet,
        skip_wait=args.skip_wait,
    )

    if not args.quiet:
        print("TUK001")
        print(f"   Server: {args.server}")
        print(f"   Difficulty: {args.difficulty}")
        print()

    await bot.play()


if __name__ == "__main__":
    asyncio.run(main())
