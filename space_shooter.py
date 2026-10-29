"""
EF101-P05  -  Python-Based 2D Game: "STAR DEFENDER" (space shooter)

Run:      pip install pygame
          python space_shooter.py

Controls: Arrow keys / WASD  move          SPACE  shoot
          P  pause/resume    M  mute/unmute
          B  (or X) fire the BONUS ROCKET - destroys ALL enemies on screen
          ENTER  start       R  restart (after game over)    ESC  back / quit

All graphics are drawn with code and all sounds are synthesised at start-up,
so the game uses NO copyrighted or external assets.

Where each concept from "Required Understanding" lives in the code
------------------------------------------------------------------
* Game loop ........ Game.run()             (events -> update -> draw, every frame)
* Frame updates ... Game.update(dt)         (moves every object by speed * dt)
* Input events .... Game.handle_events()    (KEYDOWN) and Player.handle_input() (held keys)
* State/variables . Game.state              (TITLE / PLAYING / PAUSED / GAME_OVER)
* Collisions ....... Game.check_collisions() (rectangle overlap tests)
* Coordinates ...... (0,0) is the TOP-LEFT of the window; x grows right, y grows DOWN
* Timing/FPS ....... clock.tick(FPS) caps at 60 fps; dt = seconds since last frame
* Asset loading .... SaveData (JSON file on disk) and SoundManager (sounds generated
                     in memory). If you add PNG/WAV files, load them with
                     pygame.image.load / pygame.mixer.Sound from an "assets" folder.
"""
"""
EF101-P05  -  Python-Based 2D Game: "STAR DEFENDER" (space shooter)

Run:      pip install pygame
          python space_shooter.py
"""

import array
import json
import math
import os
import random
import sys
import threading
import urllib.parse
import urllib.request
import uuid

import pygame
import ssl

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
WIDTH, HEIGHT = 800, 700
FPS = 60
def _get_save_file():
    """Store preferences and a persistent random device ID outside the game folder."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    folder = os.path.join(base, "StarDefender")
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        # Last-resort fallback: user home, not the game/EXE directory.
        folder = os.path.expanduser("~")
    return os.path.join(folder, "savedata.json")


SAVE_FILE = _get_save_file()
POINTS_PER_LEVEL = 300          # score needed to advance one level
START_LIVES = 3
MAX_LIVES = 5
START_ROCKETS = 1               # bonus rockets you begin with
MAX_ROCKETS = 3                 # most you can hold; +1 earned every level

WHITE = (240, 240, 250)
BLACK = (5, 6, 15)
CYAN = (80, 220, 255)
RED = (255, 80, 80)
GREEN = (90, 255, 140)
YELLOW = (255, 220, 80)
ORANGE = (255, 150, 60)
PURPLE = (180, 110, 255)
GREY = (140, 145, 165)

TITLE, PLAYING, PAUSED, GAME_OVER = "title", "playing", "paused", "game_over"

API_URL = os.environ.get("SPACE_SHOOTER_API_URL", "https://space-shooter-game-score.vercel.app/api/score").rstrip("/")


# --------------------------------------------------------------------------
# Persistent & Online Storage
# --------------------------------------------------------------------------
class SaveData:
    """Local preferences plus asynchronous online leaderboard access.

    The game remains playable without a network connection. No Redis credentials
    belong in this client; those are configured on the Vercel server.
    """

    def __init__(self):
        self.device_id = ""
        self.high_score = 0
        self.muted = False
        self.player_name = "PLAYER1"
        self.device_scores = {}
        self.global_scores = []
        self.online_status = "LOADING ONLINE LEADERBOARD..."
        self._fetch_in_progress = False
        self.load_local()
        if not self.device_id:
            self.device_id = str(uuid.uuid4())
            self.save_local()
        self.fetch_online()

    def load_local(self):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.high_score = max(0, int(data.get("high_score", 0)))
            self.muted = bool(data.get("muted", False))
            name = str(data.get("player_name", "PLAYER1"))
            self.player_name = name[:12] or "PLAYER1"
            self.device_id = str(data.get("device_id", ""))
        except (OSError, ValueError, TypeError):
            pass

    def save_local(self):
        try:
            os.makedirs(os.path.dirname(SAVE_FILE), exist_ok=True)
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "device_id": self.device_id,
                    "high_score": self.high_score,
                    "muted": self.muted,
                    "player_name": self.player_name
                }, f)
        except (OSError, TypeError):
            pass

    def fetch_online(self):
        """Fetch scores in a background thread so the game loop never stalls."""
        if self._fetch_in_progress:
            return
        self._fetch_in_progress = True

        def fetch():
            try:
                query = urllib.parse.urlencode({"device_id": self.device_id})
                req = urllib.request.Request(
                    f"{API_URL}?{query}",
                    headers={"Accept": "application/json", "User-Agent": "StarDefender/1.0"},
                    method="GET"
                )
                with urllib.request.urlopen(req, timeout=4) as response:
                    data = json.loads(response.read().decode("utf-8"))
                device_scores = data.get("device_scores", {})
                global_scores = data.get("global_scores", [])
                if not isinstance(device_scores, dict):
                    device_scores = {}
                if not isinstance(global_scores, list):
                    global_scores = []
                # Normalize server data so malformed entries cannot break drawing.
                clean_scores = []
                for entry in global_scores:
                    if not isinstance(entry, dict):
                        continue
                    try:
                        score = max(0, int(entry.get("score", 0)))
                    except (TypeError, ValueError):
                        continue
                    name = str(entry.get("name", "PLAYER"))[:12]
                    clean_scores.append({"name": name, "score": score})
                self.device_scores = device_scores
                self.global_scores = clean_scores[:10]
                try:
                    own_best = int(self.device_scores.get(self.player_name, 0))
                    self.high_score = max(self.high_score, own_best)
                except (TypeError, ValueError):
                    pass
                self.online_status = "ONLINE LEADERBOARD"
            except Exception:
                self.online_status = "OFFLINE - LEADERBOARD UNAVAILABLE"
            finally:
                self._fetch_in_progress = False

        threading.Thread(target=fetch, daemon=True).start()

    def submit_score_online(self, score_to_submit):
        """Submit only at Game Over; the game itself never waits for the request."""
        try:
            score_to_submit = int(score_to_submit)
        except (TypeError, ValueError):
            return
        name = self.player_name.strip()[:12]
        if score_to_submit <= 0 or not name:
            return

        def push():
            try:
                payload = json.dumps({
                    "device_id": self.device_id,
                    "name": name,
                    "score": score_to_submit
                }).encode("utf-8")
                req = urllib.request.Request(
                    API_URL,
                    data=payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=4) as response:
                    if response.status < 200 or response.status >= 300:
                        raise RuntimeError(f"Score API returned HTTP {response.status}")
                # Refresh after the POST completes. fetch_online itself is async.
                self.online_status = "SCORE SUBMITTED - REFRESHING..."
                self.fetch_online()
            except Exception:
                self.online_status = "OFFLINE - SCORE NOT UPLOADED"

        threading.Thread(target=push, daemon=True).start()

# --------------------------------------------------------------------------
# Sound
# --------------------------------------------------------------------------
class SoundManager:
    RATE = 44100

    def __init__(self, muted=False):
        self.muted = muted
        self.enabled = False
        self.sounds = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(self.RATE, -16, 1, 512)
            self.enabled = True
            self.sounds["shoot"] = self._tone(900, 300, 0.12, 0.25, "square")
            self.sounds["explode"] = self._tone(200, 40, 0.35, 0.45, "noise")
            self.sounds["hit"] = self._tone(300, 80, 0.4, 0.5, "noise")
            self.sounds["powerup"] = self._tone(400, 1200, 0.25, 0.3, "sine")
            self.sounds["levelup"] = self._tone(500, 1000, 0.5, 0.3, "square")
            self.sounds["gameover"] = self._tone(500, 60, 0.9, 0.4, "square")
            self.sounds["rocket"] = self._tone(150, 700, 0.5, 0.3, "noise")
            self.sounds["blast"] = self._tone(140, 20, 1.0, 0.7, "noise")
        except pygame.error:
            print("Audio device not available - running without sound.")

    def _tone(self, f_start, f_end, duration, volume, kind):
        n = int(self.RATE * duration)
        buf = array.array("h")
        phase = 0.0
        for i in range(n):
            t = i / n
            freq = f_start + (f_end - f_start) * t
            phase += 2 * math.pi * freq / self.RATE
            if kind == "square":
                v = 1.0 if math.sin(phase) >= 0 else -1.0
            elif kind == "sine":
                v = math.sin(phase)
            else:
                v = random.uniform(-1, 1)
            envelope = (1 - t) ** 1.5
            buf.append(int(v * envelope * volume * 32767))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, name):
        if self.enabled and not self.muted and name in self.sounds:
            self.sounds[name].play()

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted and self.enabled:
            pygame.mixer.stop()


# --------------------------------------------------------------------------
# Game Objects
# --------------------------------------------------------------------------
class Starfield:
    def __init__(self):
        self.stars = [
            [random.uniform(0, WIDTH), random.uniform(0, HEIGHT), random.choice((30, 60, 110))]
            for _ in range(90)
        ]

    def update(self, dt, boost=1.0):
        for s in self.stars:
            s[1] += s[2] * dt * boost
            if s[1] > HEIGHT:
                s[0], s[1] = random.uniform(0, WIDTH), 0

    def draw(self, surf):
        for x, y, speed in self.stars:
            c = 80 + speed
            size = 1 if speed < 100 else 2
            pygame.draw.rect(surf, (c, c, min(255, c + 30)), (x, y, size, size))


class Particle:
    def __init__(self, x, y, color):
        angle = random.uniform(0, math.tau)
        speed = random.uniform(40, 260)
        self.x, self.y = x, y
        self.vx, self.vy = math.cos(angle) * speed, math.sin(angle) * speed
        self.life = self.max_life = random.uniform(0.3, 0.7)
        self.color = color

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    def draw(self, surf):
        fade = max(0, self.life / self.max_life)
        c = tuple(int(v * fade) for v in self.color)
        pygame.draw.circle(surf, c, (int(self.x), int(self.y)), max(1, int(3 * fade)))


class Bullet:
    def __init__(self, x, y, vx=0):
        self.x, self.y, self.vx = x, y, vx
        self.rect = pygame.Rect(0, 0, 6, 16)
        self.rect.center = (x, y)

    def update(self, dt):
        self.y -= 650 * dt
        self.x += self.vx * dt
        self.rect.center = (self.x, self.y)

    def draw(self, surf):
        pygame.draw.rect(surf, CYAN, self.rect, border_radius=3)
        pygame.draw.rect(surf, WHITE, self.rect.inflate(-3, -6), border_radius=2)


class EnemyBullet:
    def __init__(self, x, y, target_x, target_y, speed):
        dx, dy = target_x - x, target_y - y
        dist = math.hypot(dx, dy) or 1
        self.x, self.y = x, y
        self.vx, self.vy = dx / dist * speed, dy / dist * speed
        self.rect = pygame.Rect(0, 0, 10, 10)
        self.rect.center = (x, y)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rect.center = (self.x, self.y)

    def draw(self, surf):
        pygame.draw.circle(surf, ORANGE, self.rect.center, 6)
        pygame.draw.circle(surf, YELLOW, self.rect.center, 3)


class Rocket:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.rect = pygame.Rect(0, 0, 14, 34)
        self.rect.center = (x, y)

    def update(self, dt):
        self.y -= 520 * dt
        self.rect.center = (self.x, self.y)

    def draw(self, surf):
        x, y = int(self.x), int(self.y)
        pygame.draw.polygon(surf, ORANGE, [(x - 5, y + 17), (x + 5, y + 17), (x, y + 17 + random.randint(16, 30))])
        pygame.draw.polygon(surf, YELLOW, [(x - 3, y + 17), (x + 3, y + 17), (x, y + 17 + random.randint(6, 14))])
        pygame.draw.polygon(surf, RED, [(x - 6, y + 6), (x - 14, y + 20), (x - 6, y + 16)])
        pygame.draw.polygon(surf, RED, [(x + 6, y + 6), (x + 14, y + 20), (x + 6, y + 16)])
        pygame.draw.rect(surf, WHITE, (x - 6, y - 14, 12, 32), border_radius=4)
        pygame.draw.polygon(surf, RED, [(x - 6, y - 14), (x + 6, y - 14), (x, y - 30)])
        pygame.draw.circle(surf, CYAN, (x, y), 3)


class Player:
    SPEED = 340

    def __init__(self):
        self.rect = pygame.Rect(0, 0, 44, 48)
        self.reset()

    def reset(self):
        self.x, self.y = WIDTH / 2, HEIGHT - 80
        self.lives = START_LIVES
        self.cooldown = 0.0
        self.invulnerable = 0.0
        self.rapid = 0.0
        self.shield = 0.0
        self.rockets = START_ROCKETS
        self.rect.center = (self.x, self.y)

    @property
    def hitbox(self):
        return self.rect.inflate(-14, -10)

    def handle_input(self, keys, dt):
        dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
        dy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
        if dx and dy:
            dx *= 0.7071
            dy *= 0.7071
        self.x += dx * self.SPEED * dt
        self.y += dy * self.SPEED * dt
        self.x = max(25, min(WIDTH - 25, self.x))
        self.y = max(HEIGHT * 0.35, min(HEIGHT - 30, self.y))
        self.rect.center = (self.x, self.y)

    def update(self, dt):
        self.cooldown = max(0, self.cooldown - dt)
        self.invulnerable = max(0, self.invulnerable - dt)
        self.rapid = max(0, self.rapid - dt)
        self.shield = max(0, self.shield - dt)

    def try_shoot(self):
        if self.cooldown > 0:
            return []
        self.cooldown = 0.11 if self.rapid > 0 else 0.26
        if self.rapid > 0:
            return [Bullet(self.x - 12, self.y - 20, -40), Bullet(self.x + 12, self.y - 20, 40)]
        return [Bullet(self.x, self.y - 26)]

    def draw(self, surf):
        if self.invulnerable > 0 and int(self.invulnerable * 12) % 2 == 0:
            return
        x, y = self.x, self.y
        flame = random.randint(10, 20)
        pygame.draw.polygon(surf, ORANGE, [(x - 8, y + 20), (x + 8, y + 20), (x, y + 20 + flame)])
        pygame.draw.polygon(surf, (60, 120, 200), [(x - 22, y + 20), (x - 6, y - 4), (x - 6, y + 20)])
        pygame.draw.polygon(surf, (60, 120, 200), [(x + 22, y + 20), (x + 6, y - 4), (x + 6, y + 20)])
        pygame.draw.polygon(surf, (190, 210, 240), [(x, y - 26), (x + 10, y + 20), (x - 10, y + 20)])
        pygame.draw.circle(surf, CYAN, (int(x), int(y - 4)), 5)
        if self.shield > 0:
            pygame.draw.circle(surf, (90, 200, 255), (int(x), int(y)), 36, 2)


class Enemy:
    STATS = {
        "drone": (1, 10, 36, 32),
        "zigzag": (2, 20, 36, 32),
        "gunner": (3, 40, 46, 38),
        "asteroid": (3, 15, 54, 54),
    }

    def __init__(self, kind, level):
        self.kind = kind
        self.hp, self.points, w, h = self.STATS[kind]
        self.rect = pygame.Rect(0, 0, w, h)
        self.x = random.uniform(40, WIDTH - 40)
        self.y = -40.0
        self.base_x = self.x
        self.t = random.uniform(0, 6)
        diff = min(level - 1, 12)
        self.vy = random.uniform(90, 130) + diff * 14
        self.dir = random.choice((-1, 1))
        self.shoot_timer = random.uniform(0.8, 1.6)
        self.shoot_interval = max(0.7, 1.7 - diff * 0.08)
        self.spin = random.uniform(-2, 2)
        self.angle = 0.0
        self.rock = [(math.cos(a) * random.uniform(20, 28), math.sin(a) * random.uniform(20, 28))
                     for a in [i * math.tau / 9 for i in range(9)]]
        self.rect.center = (self.x, self.y)

    def update(self, dt, player, enemy_bullets, level):
        self.t += dt
        if self.kind == "drone":
            self.y += self.vy * dt
        elif self.kind == "zigzag":
            self.y += self.vy * 0.8 * dt
            self.x = self.base_x + math.sin(self.t * 3) * 90
        elif self.kind == "asteroid":
            self.y += self.vy * 0.7 * dt
            self.x += self.dir * 30 * dt
            self.angle += self.spin * dt
        elif self.kind == "gunner":
            if self.y < 110:
                self.y += self.vy * dt
            else:
                self.x += self.dir * 110 * dt
                if self.x < 40 or self.x > WIDTH - 40:
                    self.dir *= -1
            self.shoot_timer -= dt
            if self.shoot_timer <= 0 and self.y > 0:
                self.shoot_timer = self.shoot_interval
                speed = 230 + min(level, 10) * 12
                enemy_bullets.append(EnemyBullet(self.x, self.y + 18, player.x, player.y, speed))
        self.x = max(20, min(WIDTH - 20, self.x))
        self.rect.center = (self.x, self.y)

    def draw(self, surf):
        x, y = int(self.x), int(self.y)
        if self.kind == "drone":
            pygame.draw.polygon(surf, RED, [(x, y + 16), (x - 18, y - 14), (x + 18, y - 14)])
            pygame.draw.circle(surf, YELLOW, (x, y - 2), 5)
        elif self.kind == "zigzag":
            pygame.draw.polygon(surf, PURPLE, [(x - 18, y), (x, y - 16), (x + 18, y), (x, y + 16)])
            pygame.draw.circle(surf, WHITE, (x, y), 5)
        elif self.kind == "gunner":
            pygame.draw.ellipse(surf, (200, 90, 60), (x - 23, y - 12, 46, 24))
            pygame.draw.rect(surf, GREY, (x - 4, y + 6, 8, 16))
            pygame.draw.circle(surf, YELLOW, (x, y - 2), 6)
        else:
            c, s = math.cos(self.angle), math.sin(self.angle)
            pts = [(x + px * c - py * s, y + px * s + py * c) for px, py in self.rock]
            pygame.draw.polygon(surf, (120, 110, 100), pts)
            pygame.draw.polygon(surf, (170, 160, 150), pts, 2)


class PowerUp:
    COLORS = {"rapid": YELLOW, "shield": CYAN, "life": GREEN}
    LABELS = {"rapid": "R", "shield": "S", "life": "+"}

    def __init__(self, x, y, kind, font):
        self.x, self.y, self.kind = x, y, kind
        self.rect = pygame.Rect(0, 0, 26, 26)
        self.rect.center = (x, y)
        self.label = font.render(self.LABELS[kind], True, BLACK)

    def update(self, dt):
        self.y += 110 * dt
        self.rect.center = (self.x, self.y)

    def draw(self, surf):
        pygame.draw.circle(surf, self.COLORS[self.kind], self.rect.center, 14)
        pygame.draw.circle(surf, WHITE, self.rect.center, 14, 2)
        surf.blit(self.label, self.label.get_rect(center=self.rect.center))


# --------------------------------------------------------------------------
# Main Game Class
# --------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("STAR DEFENDER - EF101-P05")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()

        self.font_small = pygame.font.SysFont("consolas,couriernew,monospace", 18, bold=True)
        self.font = pygame.font.SysFont("consolas,couriernew,monospace", 24, bold=True)
        self.font_big = pygame.font.SysFont("consolas,couriernew,monospace", 64, bold=True)

        self.save = SaveData()
        self.sound = SoundManager(self.save.muted)
        self.stars = Starfield()
        self.player = Player()
        self.state = TITLE
        self.new_game()
        self.state = TITLE
        self.new_high = False

    def new_game(self):
        self.player.reset()
        self.bullets, self.enemies, self.enemy_bullets = [], [], []
        self.powerups, self.particles = [], []
        self.score = 0
        self.level = 1
        self.spawn_timer = 1.0
        self.banner_time = 2.0
        self.rocket = None
        self.flash = 0.0
        self.rocket_reward = False
        self.new_high = False
        self.state = PLAYING

    def end_game(self):
        self.state = GAME_OVER
        self.rocket = None
        self.sound.play("gameover")
        if self.score > self.save.high_score:
            self.save.high_score = self.score
            self.new_high = True
        self.save.save_local()
        # Submit score only when the game session ends
        if self.score > 0:
            self.save.submit_score_online(self.score)

    def toggle_mute(self):
        self.sound.toggle_mute()
        self.save.muted = self.sound.muted
        self.save.save_local()

    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def quit(self):
        # Quitting is not a completed run: scores upload only from end_game().
        self.save.save_local()
        pygame.quit()
        sys.exit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit()
            if event.type != pygame.KEYDOWN:
                continue
            key = event.key
            if key == pygame.K_m:
                self.toggle_mute()
            if self.state == TITLE:
                if key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.save.player_name.strip():
                        self.save.high_score = self.save.device_scores.get(self.save.player_name, self.save.high_score)
                        self.new_game()
                elif key == pygame.K_ESCAPE:
                    self.quit()
                elif key == pygame.K_BACKSPACE:
                    self.save.player_name = self.save.player_name[:-1]
                elif event.unicode.isprintable() and len(self.save.player_name) < 12 and event.unicode != " ":
                    self.save.player_name += event.unicode.upper()
            elif self.state == PLAYING:
                if key in (pygame.K_p, pygame.K_ESCAPE):
                    self.state = PAUSED
                elif key in (pygame.K_b, pygame.K_x):
                    self.fire_rocket()
            elif self.state == PAUSED:
                if key in (pygame.K_p, pygame.K_ESCAPE):
                    self.state = PLAYING
                elif key == pygame.K_r:
                    self.new_game()
            elif self.state == GAME_OVER:
                if key in (pygame.K_r, pygame.K_RETURN):
                    self.new_game()
                elif key == pygame.K_ESCAPE:
                    self.state = TITLE

    def update(self, dt):
        self.stars.update(dt, 1.0 if self.state != PAUSED else 0.0)
        if self.state != PLAYING:
            if self.state == GAME_OVER:
                self.update_particles(dt)
            return

        keys = pygame.key.get_pressed()
        p = self.player
        p.handle_input(keys, dt)
        p.update(dt)
        if keys[pygame.K_SPACE]:
            new = p.try_shoot()
            if new:
                self.sound.play("shoot")
                self.bullets.extend(new)

        self.spawn_enemies(dt)

        for b in self.bullets:
            b.update(dt)
        for e in self.enemies:
            e.update(dt, p, self.enemy_bullets, self.level)
        for eb in self.enemy_bullets:
            eb.update(dt)
        for pu in self.powerups:
            pu.update(dt)
        self.update_particles(dt)

        self.update_rocket(dt)
        self.check_collisions()

        self.bullets = [b for b in self.bullets if -30 < b.y < HEIGHT + 30 and -30 < b.x < WIDTH + 30]
        self.enemies = [e for e in self.enemies if e.y < HEIGHT + 60]
        self.enemy_bullets = [eb for eb in self.enemy_bullets if -30 < eb.x < WIDTH + 30 and -30 < eb.y < HEIGHT + 30]
        self.powerups = [pu for pu in self.powerups if pu.y < HEIGHT + 30]

        new_level = self.score // POINTS_PER_LEVEL + 1
        if new_level > self.level:
            self.level = new_level
            self.banner_time = 2.0
            self.sound.play("levelup")
            before = self.player.rockets
            self.player.rockets = min(MAX_ROCKETS, before + 1)
            self.rocket_reward = self.player.rockets > before
        self.banner_time = max(0, self.banner_time - dt)

    def update_particles(self, dt):
        for pt in self.particles:
            pt.update(dt)
        self.particles = [pt for pt in self.particles if pt.life > 0]

    def spawn_enemies(self, dt):
        self.spawn_timer -= dt
        if self.spawn_timer > 0:
            return
        self.spawn_timer = max(0.3, 1.2 - 0.1 * (self.level - 1)) * random.uniform(0.7, 1.3)
        pool = ["drone", "drone", "asteroid"]
        if self.level >= 2:
            pool += ["zigzag", "zigzag"]
        if self.level >= 3:
            pool += ["gunner"]
        if self.level >= 5:
            pool += ["gunner", "zigzag"]
        self.enemies.append(Enemy(random.choice(pool), self.level))

    def fire_rocket(self):
        p = self.player
        if self.rocket is None and p.rockets > 0:
            p.rockets -= 1
            self.rocket = Rocket(p.x, p.y - 30)
            self.sound.play("rocket")

    def update_rocket(self, dt):
        self.flash = max(0, self.flash - dt)
        r = self.rocket
        if r is None:
            return
        r.update(dt)
        if r.y < 150 or any(r.rect.colliderect(e.rect) for e in self.enemies):
            self.detonate(r.x, r.y)
            self.rocket = None

    def detonate(self, x, y):
        for e in self.enemies:
            self.destroy_enemy(e, drop=False)
        self.enemies = []
        self.enemy_bullets = []
        self.explode(x, y, WHITE, 70)
        self.explode(x, y, ORANGE, 50)
        self.flash = 0.5
        self.sound.play("blast")

    def explode(self, x, y, color, count=18):
        for _ in range(count):
            self.particles.append(Particle(x, y, color))

    def hurt_player(self):
        p = self.player
        if p.invulnerable > 0:
            return
        if p.shield > 0:
            p.shield = 0
            p.invulnerable = 0.8
            self.sound.play("hit")
            return
        p.lives -= 1
        p.invulnerable = 2.0
        self.explode(p.x, p.y, CYAN, 30)
        self.sound.play("hit")
        if p.lives <= 0:
            self.explode(p.x, p.y, ORANGE, 50)
            self.end_game()

    def check_collisions(self):
        p = self.player

        for b in self.bullets[:]:
            for e in self.enemies:
                if b.rect.colliderect(e.rect):
                    e.hp -= 1
                    if b in self.bullets:
                        self.bullets.remove(b)
                    self.explode(b.x, b.y, YELLOW, 4)
                    if e.hp <= 0:
                        self.destroy_enemy(e)
                    break
        self.enemies = [e for e in self.enemies if e.hp > 0]

        if self.state != PLAYING:
            return

        for e in self.enemies[:]:
            if p.hitbox.colliderect(e.rect):
                self.enemies.remove(e)
                self.explode(e.x, e.y, RED, 16)
                self.sound.play("explode")
                self.hurt_player()
                if self.state != PLAYING:
                    return

        for eb in self.enemy_bullets[:]:
            if p.hitbox.colliderect(eb.rect):
                self.enemy_bullets.remove(eb)
                self.hurt_player()
                if self.state != PLAYING:
                    return

        for pu in self.powerups[:]:
            if p.hitbox.colliderect(pu.rect):
                self.powerups.remove(pu)
                self.sound.play("powerup")
                if pu.kind == "rapid":
                    p.rapid = 8.0
                elif pu.kind == "shield":
                    p.shield = 10.0
                elif pu.kind == "life":
                    p.lives = min(MAX_LIVES, p.lives + 1)

    def destroy_enemy(self, e, drop=True):
        self.score += e.points
        self.explode(e.x, e.y, ORANGE, 22)
        self.sound.play("explode")
        if drop and random.random() < 0.13:
            kind = random.choices(["rapid", "shield", "life"], weights=[4, 4, 2])[0]
            self.powerups.append(PowerUp(e.x, e.y, kind, self.font_small))

    # ---- Drawing -----------------------------------------------------------
    def draw_text(self, text, font, color, center=None, topleft=None, topright=None):
        img = font.render(text, True, color)
        rect = img.get_rect()
        if center:
            rect.center = center
        elif topleft:
            rect.topleft = topleft
        elif topright:
            rect.topright = topright
        self.screen.blit(img, rect)

    def draw(self):
        self.screen.fill(BLACK)
        self.stars.draw(self.screen)

        if self.state == TITLE:
            self.draw_title()
            return

        for pu in self.powerups:
            pu.draw(self.screen)
        for e in self.enemies:
            e.draw(self.screen)
        for b in self.bullets:
            b.draw(self.screen)
        for eb in self.enemy_bullets:
            eb.draw(self.screen)
        if self.rocket:
            self.rocket.draw(self.screen)
        if self.state != GAME_OVER:
            self.player.draw(self.screen)
        for pt in self.particles:
            pt.draw(self.screen)
        if self.flash > 0:
            fl = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            fl.fill((255, 255, 255, int(200 * self.flash / 0.5)))
            self.screen.blit(fl, (0, 0))
        
        self.draw_hud()

        if self.banner_time > 0 and self.state == PLAYING:
            self.draw_text(f"LEVEL {self.level}", self.font_big, YELLOW, center=(WIDTH // 2, HEIGHT // 3))
            if self.rocket_reward:
                self.draw_text("+1 ROCKET", self.font, ORANGE, center=(WIDTH // 2, HEIGHT // 3 + 55))
        if self.state == PAUSED:
            self.draw_overlay("PAUSED", ["P - resume", "R - restart", "M - mute"])
        elif self.state == GAME_OVER:
            lines = [f"Score: {self.score}   Level: {self.level}",
                     "NEW HIGH SCORE!" if self.new_high else f"High score: {self.save.high_score}",
                     "R - play again    ESC - title screen"]
            self.draw_overlay("GAME OVER", lines, RED)
            self.draw_leaderboard_overlay()

    def draw_overlay(self, title, lines, color=WHITE):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        self.screen.blit(shade, (0, 0))
        self.draw_text(title, self.font_big, color, center=(WIDTH // 2, HEIGHT // 2 - 140))
        for i, line in enumerate(lines):
            c = GREEN if line == "NEW HIGH SCORE!" else WHITE
            self.draw_text(line, self.font, c, center=(WIDTH // 2, HEIGHT // 2 - 60 + i * 40))

    def draw_leaderboard_overlay(self):
        """Draws the global top scores directly on the Game Over screen."""
        panel = pygame.Surface((340, 210), pygame.SRCALPHA)
        panel.fill((15, 20, 35, 220))
        pygame.draw.rect(panel, CYAN, panel.get_rect(), 2, border_radius=6)
        self.screen.blit(panel, (WIDTH // 2 - 170, HEIGHT // 2 + 70))
        
        self.draw_text("GLOBAL LEADERBOARD", self.font_small, YELLOW, center=(WIDTH // 2, HEIGHT // 2 + 90))
        if not self.save.global_scores:
            self.draw_text(self.save.online_status[:34], self.font_small, GREY,
                           center=(WIDTH // 2, HEIGHT // 2 + 130))
            return
        for idx, entry in enumerate(self.save.global_scores[:5]):
            line = f"{idx+1}. {entry['name']:<10} {entry['score']:>6}"
            color = GREEN if entry['name'] == self.save.player_name else WHITE
            self.draw_text(line, self.font_small, color, center=(WIDTH // 2, HEIGHT // 2 + 120 + idx * 24))

    def draw_hud(self):
        p = self.player
        self.draw_text(f"SCORE {self.score}", self.font, WHITE, topleft=(14, 10))
        self.draw_text(f"BEST {max(self.save.high_score, self.score)}", self.font_small, GREY, topleft=(14, 40))
        self.draw_text(f"LEVEL {self.level}", self.font, YELLOW, topright=(WIDTH - 14, 10))
        
        progress = (self.score % POINTS_PER_LEVEL) / POINTS_PER_LEVEL
        pygame.draw.rect(self.screen, (40, 45, 70), (WIDTH - 164, 44, 150, 8), border_radius=4)
        pygame.draw.rect(self.screen, YELLOW, (WIDTH - 164, 44, int(150 * progress), 8), border_radius=4)
        
        for i in range(p.lives):
            x = WIDTH // 2 - (p.lives * 26) // 2 + i * 26 + 13
            pygame.draw.polygon(self.screen, CYAN, [(x, 14), (x + 9, 34), (x - 9, 34)])
        
        self.draw_text("ROCKET [B]", self.font_small, ORANGE, topleft=(14, 66))
        for i in range(p.rockets):
            rx = 150 + i * 22
            pygame.draw.rect(self.screen, WHITE, (rx, 66, 8, 18), border_radius=3)
            pygame.draw.polygon(self.screen, RED, [(rx, 66), (rx + 8, 66), (rx + 4, 58)])
        
        y = HEIGHT - 28
        if p.rapid > 0:
            self.draw_text(f"RAPID FIRE {p.rapid:0.1f}s", self.font_small, YELLOW, topleft=(14, y))
        if p.shield > 0:
            self.draw_text(f"SHIELD {p.shield:0.1f}s", self.font_small, CYAN, topleft=(240, y))
        if self.sound.muted:
            self.draw_text("MUTED (M)", self.font_small, GREY, topright=(WIDTH - 14, HEIGHT - 28))

    def draw_title(self):
        self.draw_text("STAR DEFENDER", self.font_big, CYAN, center=(WIDTH // 2, 70))
        
        # Global leaderboard is always visible; network requests run in the background.
        panel = pygame.Surface((320, 160), pygame.SRCALPHA)
        panel.fill((15, 20, 35, 200))
        pygame.draw.rect(panel, CYAN, panel.get_rect(), 1, border_radius=4)
        self.screen.blit(panel, (WIDTH // 2 - 160, 130))
        title = "ONLINE LEADERBOARD" if self.save.global_scores else "GLOBAL LEADERBOARD"
        self.draw_text(title, self.font_small, ORANGE, center=(WIDTH // 2, 145))
        if self.save.global_scores:
            for idx, entry in enumerate(self.save.global_scores[:4]):
                line = f"{idx+1}. {entry['name']:<10} {entry['score']:>6}"
                self.draw_text(line, self.font_small, WHITE, center=(WIDTH // 2, 170 + idx * 22))
        else:
            status = self.save.online_status
            color = GREEN if status.startswith("ONLINE") else GREY
            self.draw_text(status[:34], self.font_small, color, center=(WIDTH // 2, 190))
            if status.startswith("OFFLINE"):
                self.draw_text("PLAY IS STILL AVAILABLE", self.font_small, WHITE, center=(WIDTH // 2, 216))

        self.draw_text("OBJECTIVE", self.font, YELLOW, center=(WIDTH // 2, 310))
        for i, line in enumerate(["Destroy the invading ships and asteroids.",
                                  "Survive as long as you can: every 300 points",
                                  "starts a harder level. Lose all 3 lives = game over."]):
            self.draw_text(line, self.font_small, WHITE, center=(WIDTH // 2, 340 + i * 22))
            
        self.draw_text("CONTROLS", self.font, YELLOW, center=(WIDTH // 2, 420))
        for i, line in enumerate(["Arrows / WASD - move       SPACE - shoot",
                                  "P - pause      M - mute      ESC - quit",
                                  "Pick-ups:  R rapid fire   S shield   + extra life",
                                  "B - BONUS ROCKET: wipes out every enemy on screen"]):
            self.draw_text(line, self.font_small, WHITE, center=(WIDTH // 2, 450 + i * 22))
        
        # Player Profile Input
        name_str = f"ENTER NAME: < {self.save.player_name} >"
        self.draw_text(name_str, self.font, CYAN, center=(WIDTH // 2, 560))
        
        if int(pygame.time.get_ticks() / 500) % 2 == 0:
            self.draw_text("PRESS ENTER TO START", self.font, GREEN, center=(WIDTH // 2, 600))
            
        cur_best = self.save.device_scores.get(self.save.player_name, self.save.high_score)
        self.draw_text(f"High score ({self.save.player_name}): {cur_best}", self.font_small, GREY, center=(WIDTH // 2, 640))


if __name__ == "__main__":
    Game().run()
