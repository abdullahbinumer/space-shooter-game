
import array
import datetime
import json
import math
import os
import random
import sys

import pygame

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
WIDTH, HEIGHT = 800, 700
FPS = 60


def _save_path():
    """Where savedata.json lives.

    Normal run:   next to space_shooter.py.
    Built .exe:   next to the .exe (NOT __file__, which points to a temporary folder that
                  PyInstaller deletes on exit - the high score would be lost). If that folder
                  is not writable (e.g. Program Files), use %APPDATA%\\StarDefender instead.
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    if not os.access(base, os.W_OK):
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "StarDefender")
        os.makedirs(base, exist_ok=True)
    return os.path.join(base, "savedata.json")


SAVE_FILE = _save_path()
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

MAX_NAME_LEN = 12               # longest player name
LEADERBOARD_SIZE = 10           # rows shown on the leaderboard
MENU_ROWS = 8                   # player rows visible in the select menu

TITLE, PLAYING, PAUSED, GAME_OVER = "title", "playing", "paused", "game_over"
SELECT_USER, NAME_ENTRY, LEADERBOARD = "select_user", "name_entry", "leaderboard"


# --------------------------------------------------------------------------
# Persistent storage (high score + settings)
# --------------------------------------------------------------------------
class SaveData:
    """Stores every player's record, the last player and the mute setting in savedata.json.

    File layout:
        {"muted": false, "last_user": "Ali",
         "users": {"Ali": {"high_score": 420, "best_level": 2,
                           "games_played": 5, "last_played": "2025-01-31"}}}
    """

    def __init__(self):
        self.muted = False
        self.last_user = None
        self.users = {}
        self.load()

    # ---- file access ------------------------------------------------------
    def load(self):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("unexpected file layout")
        except FileNotFoundError:
            return                      # first run -> keep defaults
        except (OSError, ValueError):
            self._backup_corrupt_file()
            return
        self.muted = bool(data.get("muted", False))
        users = data.get("users")
        if isinstance(users, dict):
            for name, rec in users.items():
                if not isinstance(rec, dict):
                    continue
                try:
                    self.users[str(name)[:MAX_NAME_LEN]] = {
                        "high_score": max(0, int(rec.get("high_score", 0))),
                        "best_level": max(1, int(rec.get("best_level", 1))),
                        "games_played": max(0, int(rec.get("games_played", 0))),
                        "last_played": str(rec.get("last_played", "")),
                    }
                except (TypeError, ValueError):
                    continue
        last = data.get("last_user")
        self.last_user = self.find_user(last) if isinstance(last, str) else None

    def _backup_corrupt_file(self):
        """Keep an unreadable save file as savedata.json.bak instead of overwriting it."""
        try:
            os.replace(SAVE_FILE, SAVE_FILE + ".bak")
            print("Warning: save file was unreadable - kept a copy as savedata.json.bak")
        except OSError:
            pass

    def save(self):
        data = {"muted": self.muted, "last_user": self.last_user, "users": self.users}
        tmp = SAVE_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, SAVE_FILE)  # atomic: a crash can never leave a half-written file
        except OSError:
            print("Warning: could not write save file.")

    # ---- users ------------------------------------------------------------
    def find_user(self, name):
        """Case-insensitive lookup. Returns the stored spelling of the name, or None."""
        for stored in self.users:
            if stored.lower() == name.strip().lower():
                return stored
        return None

    def add_user(self, name):
        name = name.strip()[:MAX_NAME_LEN]
        existing = self.find_user(name)
        if existing:
            return existing
        self.users[name] = {"high_score": 0, "best_level": 1, "games_played": 0, "last_played": ""}
        self.save()
        return name

    def user_names(self):
        return sorted(self.users, key=str.lower)

    def best_of(self, name):
        return self.users[name]["high_score"] if name in self.users else 0

    # ---- scores / leaderboard --------------------------------------------
    def record_score(self, name, score, level):
        """Store a finished game. Returns (new_personal_best, leaderboard_rank)."""
        rec = self.users[name]
        new_best = score > rec["high_score"]
        if new_best:
            rec["high_score"] = score
            rec["best_level"] = level
        rec["games_played"] += 1
        rec["last_played"] = datetime.date.today().isoformat()
        self.last_user = name
        self.save()
        return new_best, self.rank_of(name)

    def ranking(self):
        """[(name, record), ...] for players who have played, best score first."""
        played = [(n, r) for n, r in self.users.items() if r["games_played"] > 0]
        played.sort(key=lambda item: (-item[1]["high_score"], item[0].lower()))
        return played

    def rank_of(self, name):
        for i, (n, _) in enumerate(self.ranking()):
            if n == name:
                return i + 1
        return None


# --------------------------------------------------------------------------
# Sound (synthesised, so no external files needed)
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
# Game objects
# --------------------------------------------------------------------------
class Starfield:
    """Scrolling background stars with 3 depth layers (parallax)."""

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
    """Player bullet - travels straight up."""

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
    """Bonus rocket: flies up fast, then detonates and wipes out every enemy."""

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
        self.invulnerable = 0.0   # seconds of protection after being hit
        self.rapid = 0.0          # seconds of rapid fire left
        self.shield = 0.0         # seconds of shield left
        self.rockets = START_ROCKETS
        self.rect.center = (self.x, self.y)

    @property
    def hitbox(self):
        return self.rect.inflate(-14, -10)   # slightly forgiving collisions

    def handle_input(self, keys, dt):
        """Held-key movement (continuous), scaled by dt so speed is frame-rate independent."""
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
        """Return a list of new bullets (empty if still cooling down)."""
        if self.cooldown > 0:
            return []
        self.cooldown = 0.11 if self.rapid > 0 else 0.26
        if self.rapid > 0:
            return [Bullet(self.x - 12, self.y - 20, -40), Bullet(self.x + 12, self.y - 20, 40)]
        return [Bullet(self.x, self.y - 26)]

    def draw(self, surf):
        # Blink while invulnerable
        if self.invulnerable > 0 and int(self.invulnerable * 12) % 2 == 0:
            return
        x, y = self.x, self.y
        # engine flame (flickers)
        flame = random.randint(10, 20)
        pygame.draw.polygon(surf, ORANGE, [(x - 8, y + 20), (x + 8, y + 20), (x, y + 20 + flame)])
        # wings
        pygame.draw.polygon(surf, (60, 120, 200), [(x - 22, y + 20), (x - 6, y - 4), (x - 6, y + 20)])
        pygame.draw.polygon(surf, (60, 120, 200), [(x + 22, y + 20), (x + 6, y - 4), (x + 6, y + 20)])
        # body
        pygame.draw.polygon(surf, (190, 210, 240), [(x, y - 26), (x + 10, y + 20), (x - 10, y + 20)])
        pygame.draw.circle(surf, CYAN, (int(x), int(y - 4)), 5)
        if self.shield > 0:
            pygame.draw.circle(surf, (90, 200, 255), (int(x), int(y)), 36, 2)


class Enemy:
    """kind: 'drone' (straight), 'zigzag' (sine path), 'gunner' (shoots), 'asteroid' (tough)."""

    STATS = {
        #  hp, points, width, height
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
            else:   # hover and strafe sideways
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
        else:  # asteroid
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
# The game itself
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
        self.current_user = self.save.last_user   # whoever played last is pre-selected
        self.menu_index = 0                       # highlighted row in the player menu
        self.menu_origin = TITLE                  # screen to return to when the menu is closed
        self.select_starts_game = False           # start playing right after choosing a player?
        self.name_input = ""                      # text typed on the "new player" screen
        self.board_origin = TITLE                 # screen to return to from the leaderboard
        self.last_rank = None                     # leaderboard rank after the latest game
        self.sound = SoundManager(self.save.muted)
        self.stars = Starfield()
        self.player = Player()
        self.state = TITLE
        self.new_game()
        self.state = TITLE
        self.new_high = False

    # ---- state management -------------------------------------------------
    def new_game(self):
        self.player.reset()
        self.bullets, self.enemies, self.enemy_bullets = [], [], []
        self.powerups, self.particles = [], []
        self.score = 0
        self.level = 1
        self.spawn_timer = 1.0
        self.banner_time = 2.0       # "LEVEL n" banner
        self.rocket = None           # the rocket currently in flight (if any)
        self.flash = 0.0             # white screen-flash timer for the blast
        self.rocket_reward = False   # show "+1 ROCKET" on the level banner
        self.new_high = False
        self.score_saved = False     # has this run's score been written to savedata.json yet?
        self.state = PLAYING

    def end_game(self):
        self.state = GAME_OVER
        self.rocket = None
        self.sound.play("gameover")
        self.new_high, self.last_rank = self.save.record_score(self.current_user, self.score, self.level)
        self.score_saved = True

    def save_progress(self):
        """Write the score of a run that is still in progress to savedata.json.

        Called whenever a run is abandoned (Main Menu, restart, quit, window closed) so a
        high score is never lost just because the player did not reach GAME OVER.
        """
        if (self.state in (PLAYING, PAUSED) and not self.score_saved
                and self.score > 0 and self.current_user in self.save.users):
            self.new_high, self.last_rank = self.save.record_score(self.current_user, self.score, self.level)
            self.score_saved = True

    def go_to_main_menu(self):
        """X key: leave the current game and return to the Main Menu (title screen)."""
        self.save_progress()
        self.rocket = None
        self.state = TITLE

    def toggle_mute(self):
        self.sound.toggle_mute()
        self.save.muted = self.sound.muted
        self.save.save()

    # ---- main loop ---------------------------------------------------------
    def run(self):
        while True:
            # dt = seconds since the previous frame. Multiplying speeds by dt keeps
            # movement identical on slow and fast computers.
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def quit(self):
        self.save_progress()     # keep the score of a run that is still in progress
        self.save.save()
        pygame.quit()
        sys.exit()

    # ---- player / menu helpers ---------------------------------------------
    def start_or_pick_player(self):
        """ENTER on the title screen: play as the current player, or ask who is playing."""
        if self.current_user:
            self.new_game()
        else:
            self.open_select(TITLE, start=True)

    def open_select(self, origin, start=False):
        self.menu_origin = origin
        self.select_starts_game = start
        names = self.save.user_names()
        if not names:
            self.open_name_entry()
            return
        self.menu_index = names.index(self.current_user) if self.current_user in names else 0
        self.state = SELECT_USER

    def open_name_entry(self):
        self.name_input = ""
        self.state = NAME_ENTRY

    def choose_user(self, name):
        self.current_user = name
        self.save.last_user = name
        self.save.save()
        if self.select_starts_game:
            self.new_game()
        else:
            self.state = TITLE

    def open_leaderboard(self, origin):
        self.board_origin = origin
        self.state = LEADERBOARD

    # ---- input -------------------------------------------------------------
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit()
            if event.type != pygame.KEYDOWN:
                continue
            key = event.key
            if self.state == NAME_ENTRY:      # typing a name: letters must not trigger shortcuts
                self.handle_name_entry(event)
                continue
            if key == pygame.K_m:
                self.toggle_mute()
            if self.state == TITLE:
                if key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.start_or_pick_player()
                elif key == pygame.K_u:
                    self.open_select(TITLE)
                elif key == pygame.K_l:
                    self.open_leaderboard(TITLE)
                elif key == pygame.K_ESCAPE:
                    self.quit()
            elif self.state == SELECT_USER:
                names = self.save.user_names()
                if key in (pygame.K_UP, pygame.K_w):
                    self.menu_index = (self.menu_index - 1) % len(names)
                elif key in (pygame.K_DOWN, pygame.K_s):
                    self.menu_index = (self.menu_index + 1) % len(names)
                elif key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.choose_user(names[self.menu_index])
                elif key == pygame.K_n:
                    self.open_name_entry()
                elif key == pygame.K_ESCAPE:
                    self.state = self.menu_origin
            elif self.state == LEADERBOARD:
                if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_l):
                    self.state = self.board_origin
            elif self.state == PLAYING:
                if key == pygame.K_x:
                    self.go_to_main_menu()
                elif key in (pygame.K_p, pygame.K_ESCAPE):
                    self.state = PAUSED
                elif key == pygame.K_b:
                    self.fire_rocket()
            elif self.state == PAUSED:
                if key == pygame.K_x:
                    self.go_to_main_menu()
                elif key in (pygame.K_p, pygame.K_ESCAPE):
                    self.state = PLAYING
                elif key == pygame.K_r:
                    self.save_progress()      # restarting abandons this run - keep its score
                    self.new_game()
            elif self.state == GAME_OVER:
                if key in (pygame.K_r, pygame.K_RETURN):
                    self.new_game()
                elif key == pygame.K_u:
                    self.open_select(GAME_OVER, start=True)   # hand over to the next player
                elif key == pygame.K_l:
                    self.open_leaderboard(GAME_OVER)
                elif key in (pygame.K_x, pygame.K_ESCAPE):
                    self.go_to_main_menu()

    def handle_name_entry(self, event):
        key = event.key
        if key == pygame.K_RETURN:
            name = self.name_input.strip()
            if name:   # an existing name (any capitalisation) simply selects that player
                self.choose_user(self.save.add_user(name))
        elif key == pygame.K_ESCAPE:
            self.state = SELECT_USER if self.save.users else self.menu_origin
        elif key == pygame.K_BACKSPACE:
            self.name_input = self.name_input[:-1]
        else:
            ch = event.unicode
            if ch and ch.isascii() and (ch.isalnum() or ch in " _-") and len(self.name_input) < MAX_NAME_LEN:
                self.name_input += ch

    # ---- update ------------------------------------------------------------
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

        # remove objects that left the screen
        self.bullets = [b for b in self.bullets if -30 < b.y < HEIGHT + 30 and -30 < b.x < WIDTH + 30]
        self.enemies = [e for e in self.enemies if e.y < HEIGHT + 60]
        self.enemy_bullets = [eb for eb in self.enemy_bullets
                              if -30 < eb.x < WIDTH + 30 and -30 < eb.y < HEIGHT + 30]
        self.powerups = [pu for pu in self.powerups if pu.y < HEIGHT + 30]

        # progression: new level every POINTS_PER_LEVEL points (no upper limit)
        new_level = self.score // POINTS_PER_LEVEL + 1
        if new_level > self.level:
            self.level = new_level
            self.banner_time = 2.0
            self.sound.play("levelup")
            before = self.player.rockets
            self.player.rockets = min(MAX_ROCKETS, before + 1)   # reward for reaching a new level
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
        # Difficulty rises with the level: faster spawns, tougher enemy mix.
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
        """Launch the bonus rocket (only one in flight, and you need one in stock)."""
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
        # detonate when it hits an enemy or reaches the upper part of the screen
        if r.y < 150 or any(r.rect.colliderect(e.rect) for e in self.enemies):
            self.detonate(r.x, r.y)
            self.rocket = None

    def detonate(self, x, y):
        """Big blast: every enemy and enemy bullet on screen is destroyed."""
        for e in self.enemies:
            self.destroy_enemy(e, drop=False)   # still scores points for each enemy
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
        """Axis-aligned rectangle overlap tests (Rect.colliderect)."""
        p = self.player

        # player bullets vs enemies
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

        # enemies vs player
        for e in self.enemies[:]:
            if p.hitbox.colliderect(e.rect):
                self.enemies.remove(e)
                self.explode(e.x, e.y, RED, 16)
                self.sound.play("explode")
                self.hurt_player()
                if self.state != PLAYING:
                    return

        # enemy bullets vs player
        for eb in self.enemy_bullets[:]:
            if p.hitbox.colliderect(eb.rect):
                self.enemy_bullets.remove(eb)
                self.hurt_player()
                if self.state != PLAYING:
                    return

        # power-ups vs player
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

    # ---- drawing -----------------------------------------------------------
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
        if self.state == SELECT_USER:
            self.draw_select_user()
            return
        if self.state == NAME_ENTRY:
            self.draw_name_entry()
            return
        if self.state == LEADERBOARD:
            self.draw_leaderboard()
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
        if self.flash > 0:   # white flash fading out after the blast
            fl = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            fl.fill((255, 255, 255, int(200 * self.flash / 0.5)))
            self.screen.blit(fl, (0, 0))
        self.draw_hud()

        if self.banner_time > 0 and self.state == PLAYING:
            self.draw_text(f"LEVEL {self.level}", self.font_big, YELLOW, center=(WIDTH // 2, HEIGHT // 3))
            if self.rocket_reward:
                self.draw_text("+1 ROCKET", self.font, ORANGE, center=(WIDTH // 2, HEIGHT // 3 + 55))
        if self.state == PAUSED:
            self.draw_overlay("PAUSED", ["P - resume", "R - restart", "X - main menu", "M - mute"])
        elif self.state == GAME_OVER:
            lines = [f"{self.current_user}:  Score {self.score}   Level {self.level}",
                     "NEW PERSONAL BEST!" if self.new_high else f"Your best: {self.save.best_of(self.current_user)}",
                     f"Leaderboard rank: #{self.last_rank}" if self.last_rank else "",
                     "R - play again     U - switch player",
                     "L - leaderboard    X - main menu"]
            self.draw_overlay("GAME OVER", lines, RED)

    def draw_overlay(self, title, lines, color=WHITE):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        self.screen.blit(shade, (0, 0))
        self.draw_text(title, self.font_big, color, center=(WIDTH // 2, HEIGHT // 2 - 90))
        for i, line in enumerate(lines):
            c = GREEN if line.startswith("NEW") else WHITE
            self.draw_text(line, self.font, c, center=(WIDTH // 2, HEIGHT // 2 - 10 + i * 40))

    def draw_hud(self):
        p = self.player
        self.draw_text(f"SCORE {self.score}", self.font, WHITE, topleft=(14, 10))
        best = max(self.save.best_of(self.current_user), self.score)
        self.draw_text(f"{self.current_user}  BEST {best}", self.font_small, GREY, topleft=(14, 40))
        self.draw_text(f"LEVEL {self.level}", self.font, YELLOW, topright=(WIDTH - 14, 10))
        # next-level progress bar
        progress = (self.score % POINTS_PER_LEVEL) / POINTS_PER_LEVEL
        pygame.draw.rect(self.screen, (40, 45, 70), (WIDTH - 164, 44, 150, 8), border_radius=4)
        pygame.draw.rect(self.screen, YELLOW, (WIDTH - 164, 44, int(150 * progress), 8), border_radius=4)
        # lives as small ship icons
        for i in range(p.lives):
            x = WIDTH // 2 - (p.lives * 26) // 2 + i * 26 + 13
            pygame.draw.polygon(self.screen, CYAN, [(x, 14), (x + 9, 34), (x - 9, 34)])
        # bonus rockets in stock
        self.draw_text("ROCKET [B]", self.font_small, ORANGE, topleft=(14, 66))
        for i in range(p.rockets):
            rx = 150 + i * 22
            pygame.draw.rect(self.screen, WHITE, (rx, 66, 8, 18), border_radius=3)
            pygame.draw.polygon(self.screen, RED, [(rx, 66), (rx + 8, 66), (rx + 4, 58)])
        # active power-ups
        y = HEIGHT - 28
        if p.rapid > 0:
            self.draw_text(f"RAPID FIRE {p.rapid:0.1f}s", self.font_small, YELLOW, topleft=(14, y))
        if p.shield > 0:
            self.draw_text(f"SHIELD {p.shield:0.1f}s", self.font_small, CYAN, topleft=(240, y))
        if self.sound.muted:
            self.draw_text("MUTED (M)", self.font_small, GREY, topright=(WIDTH - 14, HEIGHT - 28))

    def draw_title(self):
        self.draw_text("STAR DEFENDER", self.font_big, CYAN, center=(WIDTH // 2, 150))
        self.draw_text("OBJECTIVE", self.font, YELLOW, center=(WIDTH // 2, 240))
        for i, line in enumerate(["Destroy the invading ships and asteroids.",
                                  "Survive as long as you can: every 300 points",
                                  "starts a harder level. Lose all 3 lives = game over."]):
            self.draw_text(line, self.font_small, WHITE, center=(WIDTH // 2, 275 + i * 26))
        self.draw_text("CONTROLS", self.font, YELLOW, center=(WIDTH // 2, 385))
        for i, line in enumerate(["Arrows / WASD - move       SPACE - shoot",
                                  "P - pause   M - mute   X - main menu   ESC - quit",
                                  "U - switch player        L - leaderboard",
                                  "Pick-ups:  R rapid fire   S shield   + extra life",
                                  "B - BONUS ROCKET: wipes out every enemy on screen"]):
            self.draw_text(line, self.font_small, WHITE, center=(WIDTH // 2, 420 + i * 26))
        if int(pygame.time.get_ticks() / 500) % 2 == 0:
            self.draw_text("PRESS ENTER TO START", self.font, GREEN, center=(WIDTH // 2, 575))
        if self.current_user:
            who = f"Player: {self.current_user}   (best {self.save.best_of(self.current_user)})"
        else:
            who = "No player selected yet"
        self.draw_text(who, self.font, WHITE, center=(WIDTH // 2, 625))

    def draw_select_user(self):
        names = self.save.user_names()
        self.draw_text("SELECT PLAYER", self.font_big, CYAN, center=(WIDTH // 2, 100))
        first = min(max(0, self.menu_index - MENU_ROWS // 2), max(0, len(names) - MENU_ROWS))
        for row, name in enumerate(names[first:first + MENU_ROWS]):
            y = 190 + row * 44
            selected = first + row == self.menu_index
            if selected:
                pygame.draw.rect(self.screen, (30, 50, 90), (170, y - 18, WIDTH - 340, 38), border_radius=6)
                pygame.draw.rect(self.screen, CYAN, (170, y - 18, WIDTH - 340, 38), 2, border_radius=6)
            color = YELLOW if selected else WHITE
            self.draw_text(name, self.font, color, topleft=(190, y - 12))
            self.draw_text(f"best {self.save.best_of(name)}", self.font_small, GREY, topright=(WIDTH - 190, y - 8))
        if len(names) > MENU_ROWS:
            self.draw_text(f"{self.menu_index + 1} / {len(names)}", self.font_small, GREY,
                           center=(WIDTH // 2, 190 + MENU_ROWS * 44))
        self.draw_text("UP/DOWN - choose     ENTER - select", self.font_small, WHITE, center=(WIDTH // 2, HEIGHT - 90))
        self.draw_text("N - new player     ESC - back", self.font_small, WHITE, center=(WIDTH // 2, HEIGHT - 60))

    def draw_name_entry(self):
        self.draw_text("NEW PLAYER", self.font_big, CYAN, center=(WIDTH // 2, 150))
        self.draw_text("Type your name and press ENTER", self.font, WHITE, center=(WIDTH // 2, 260))
        box = pygame.Rect(0, 0, 420, 56)
        box.center = (WIDTH // 2, 340)
        pygame.draw.rect(self.screen, (20, 25, 50), box, border_radius=8)
        pygame.draw.rect(self.screen, CYAN, box, 2, border_radius=8)
        cursor = "_" if int(pygame.time.get_ticks() / 400) % 2 == 0 else " "
        self.draw_text(self.name_input + cursor, self.font, YELLOW, center=box.center)
        self.draw_text(f"letters, numbers, space, - and _   (max {MAX_NAME_LEN})", self.font_small, GREY,
                       center=(WIDTH // 2, 395))
        self.draw_text("ENTER - confirm     ESC - cancel", self.font_small, WHITE, center=(WIDTH // 2, HEIGHT - 70))

    def draw_leaderboard(self):
        self.draw_text("LEADERBOARD", self.font_big, CYAN, center=(WIDTH // 2, 90))
        top = 160
        self.draw_text("RANK", self.font_small, GREY, topleft=(110, top))
        self.draw_text("PLAYER", self.font_small, GREY, topleft=(200, top))
        self.draw_text("SCORE", self.font_small, GREY, topright=(530, top))
        self.draw_text("LEVEL", self.font_small, GREY, topright=(620, top))
        self.draw_text("GAMES", self.font_small, GREY, topright=(710, top))
        pygame.draw.line(self.screen, GREY, (100, top + 28), (WIDTH - 90, top + 28), 1)
        board = self.save.ranking()
        if not board:
            self.draw_text("No scores yet - be the first!", self.font, WHITE, center=(WIDTH // 2, 330))
        for i, (name, rec) in enumerate(board[:LEADERBOARD_SIZE]):
            self.draw_board_row(top + 48 + i * 34, i + 1, name, rec)
        rank = self.save.rank_of(self.current_user) if self.current_user else None
        if rank and rank > LEADERBOARD_SIZE:   # always show where the current player stands
            y = top + 48 + LEADERBOARD_SIZE * 34 + 6
            self.draw_text("...", self.font_small, GREY, topleft=(110, y - 12))
            self.draw_board_row(y + 12, rank, self.current_user, self.save.users[self.current_user])
        self.draw_text("ESC - back", self.font_small, WHITE, center=(WIDTH // 2, HEIGHT - 40))

    def draw_board_row(self, y, rank, name, rec):
        if name == self.current_user:
            color = GREEN
        else:
            color = YELLOW if rank == 1 else WHITE
        self.draw_text(f"#{rank}", self.font_small, color, topleft=(110, y))
        self.draw_text(name, self.font_small, color, topleft=(200, y))
        self.draw_text(str(rec["high_score"]), self.font_small, color, topright=(530, y))
        self.draw_text(str(rec["best_level"]), self.font_small, color, topright=(620, y))
        self.draw_text(str(rec["games_played"]), self.font_small, color, topright=(710, y))


if __name__ == "__main__":
    Game().run()
