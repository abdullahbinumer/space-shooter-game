# Space-Shooter Project Documentation

**Course project:** EF101-P05 — Python-Based 2D Game  
**Genre:** Vertical space shooter  
**Language / library:** Python 3 + pygame (pygame-ce for packaged build)  
**Assets:** None. All graphics are drawn with code and all sounds are synthesised at start-up, so the game uses no copyrighted or external files.

---

## 1. Overview

Space Shooter is a single-player / local multi-player arcade shooter. The player pilots a ship at the bottom of the screen and must destroy waves of invading ships and asteroids. Every 300 points the game moves to a harder level, with no upper limit. The run ends when all lives are lost, and the best scores are saved so they persist between sessions.

The game is available in three forms:

| Form | File | Who it is for |
|---|---|---|
| Python source | `space_shooter.py` | Marking / reading the code; run with Python + pygame |
| Windows executable | `StarDefender.exe` | Players with no Python installed (GitHub Releases) |
| Browser version | `index.html` (itch.io) | Anyone, with nothing to install |

The executable is built from the unmodified Python source. The browser version is a JavaScript port of the same game logic (a browser cannot run Python directly).

**Multi-User Profiles & Leaderboard:** The game supports multiple player profiles on a single computer. Each player creates a profile name, and their individual high scores, best levels, and games played are securely tracked and ranked on a local Leaderboard.

---

## 2. How to run

### 2.1 From source (Python)

    pip install pygame
    python space_shooter.py

### 2.2 Executable (Windows)

1. Download `StarDefender-windows.zip` from the repository's **Releases** page.
2. Unzip and double-click `StarDefender.exe`. No Python or terminal is needed.
3. Windows may show "Windows protected your PC" because the file is not code-signed. Click **More info → Run anyway**.

### 2.3 Browser

Open the itch.io page and click the game once so the keyboard works. Desktop browsers only (keyboard controls).

---

## 3. Controls

| Key | Action |
|---|---|
| Arrow keys / **W A S D** | Move the ship |
| **Space** | Shoot (hold for continuous fire) |
| **B** or **X** | Fire the bonus rocket |
| **P** | Pause / resume |
| **M** | Mute / unmute sound |
| **Enter** | Start the game (title screen) / Select option |
| **U** | Switch / create player profile |
| **N** | Add a new player (from player menu) |
| **L** | Open Leaderboard |
| **R** | Restart (after game over, or from the pause screen) |
| **Esc** | Pause while playing; back to title from game over; quit from title screen |
| **E** | *(browser version)* Download the high score as `savedata.json` |
| **L** | *(browser version)* Load a previously saved `savedata.json` |

---

## 4. Gameplay rules

### 4.1 Objective and progression
- Destroy enemies to earn points. **Level = score ÷ 300 + 1**; the progress bar at the top right shows how close the next level is.
- Each level increases enemy speed, spawns enemies more often, and (from level 2) adds tougher enemy types.
- Starting a new level also awards **+1 bonus rocket** (maximum 3 held).

### 4.2 The player
| Property | Value |
|---|---|
| Movement speed | 340 px/s (diagonals are normalised) |
| Movement area | The lower ~65 % of the screen |
| Lives | Start with 3, maximum 5 |
| Fire rate | One bullet every 0.26 s |
| After being hit | 2 s of invulnerability (the ship blinks) |
| Hitbox | Slightly smaller than the sprite, so near-misses feel fair |

### 4.3 Enemies

| Type | HP | Points | Behaviour | Appears from |
|---|---|---|---|---|
| Drone | 1 | 10 | Flies straight down | Level 1 |
| Asteroid | 3 | 15 | Drifts down and sideways while rotating | Level 1 |
| Zigzag | 2 | 20 | Moves down along a sine-wave path | Level 2 |
| Gunner | 3 | 40 | Descends, then hovers and strafes while firing aimed shots at the player | Level 3 |

- Enemy fall speed is randomly 90–130 px/s plus 14 px/s for each level (capped at +12 levels).
- Spawn interval is `max(0.3, 1.2 − 0.1 × (level − 1))` seconds, randomised by ±30 %.
- Gunners fire faster at higher levels (interval `max(0.7, 1.7 − 0.08 × difficulty)` s) and their bullets get faster up to level 10.
- Colliding with an enemy destroys it and costs the player a life.

### 4.4 Power-ups
Each destroyed enemy has a 13 % chance to drop a power-up that falls down the screen. Collect it by touching it.

| Icon | Name | Effect |
|---|---|---|
| **R** (yellow) | Rapid fire | 8 s of faster firing (0.11 s) with two angled bullets |
| **S** (cyan) | Shield | 10 s shield that absorbs one hit (then 0.8 s of protection) |
| **+** (green) | Extra life | +1 life, up to the maximum of 5 |

### 4.5 Bonus rocket
- Press **B** (or **X**) to launch a rocket straight up. You start with 1 and can hold up to 3; a new one is earned every level.
- It explodes when it hits an enemy or reaches the upper part of the screen.
- The blast **destroys every enemy and every enemy bullet on screen**. You still score the points for each enemy destroyed, but no power-ups drop.
- Only one rocket can be in flight at a time.

### 4.6 Game states

    TITLE ──Enter──► PLAYING ◄──P/Esc──► PAUSED
      │                 │                   │
     U/L           lose all lives       R (restart)
      │                 ▼                   │
      ▼             GAME_OVER ──R/Enter─────┘
    MENUS               │
    [SELECT_USER] ◄── U/L/Esc
    [LEADERBOARD]       ▼
    [NAME_ENTRY]      TITLE

---

## 5. Code structure (`space_shooter.py`)

The file is organised as small classes, each responsible for one thing.

| Class | Responsibility |
|---|---|
| `SaveData` | Loads and saves user profiles, high scores, and mute settings (JSON file) |
| `SoundManager` | Generates all sound effects in memory and plays them |
| `Starfield` | Scrolling background with three parallax depth layers |
| `Particle` | Short-lived explosion sparks that fade out |
| `Bullet` / `EnemyBullet` | Player shots (straight up) and aimed enemy shots |
| `Rocket` | The bonus rocket |
| `Player` | Ship state: position, lives, cooldown, power-up timers, rockets |
| `Enemy` | All four enemy types, selected by a `kind` field |
| `PowerUp` | Falling pick-ups |
| `Game` | Owns everything: main loop, state machine, input, updates, collisions, drawing |

### 5.1 Where each required concept lives

| Concept | Where in the code |
|---|---|
| Game loop | `Game.run()` — each frame: events → update → draw |
| Frame updates | `Game.update(dt)` — every object moves by `speed × dt` |
| Input events | `Game.handle_events()` (key presses) and `Player.handle_input()` (keys held down) |
| State / variables | `Game.state` (`TITLE`, `PLAYING`, `PAUSED`, `GAME_OVER`, `SELECT_USER`, `NAME_ENTRY`, `LEADERBOARD`), plus score, level, lives, timers |
| Collisions | `Game.check_collisions()` — axis-aligned rectangle overlap (`Rect.colliderect`) |
| Coordinates | Origin `(0, 0)` is the **top-left**; x grows right, y grows **down**. Window is 800 × 700 |
| Timing / FPS | `clock.tick(60)` caps the frame rate; `dt` = seconds since the last frame (capped at 0.05 s) |
| Asset loading / persistence | `SaveData` (JSON on disk) and `SoundManager` (sounds synthesised at start-up) |

### 5.2 Frame-rate independence
Movement is always `position += velocity × dt`, so the game plays at the same speed on slow and fast computers. `dt` is capped at 0.05 s so a lag spike cannot teleport objects through each other.

### 5.3 Sound
Each effect is generated from a start frequency, an end frequency, a duration, a volume and a waveform (`square`, `sine` or `noise`) with a fading envelope. Effects: shoot, explode, hit, power-up, level-up, game over, rocket and blast. If no audio device is available, the game runs silently instead of crashing.

---

## 6. Saved data & Multi-User Profiles

The game stores profile details, scores, and settings in a JSON file:

    {
      "muted": false,
      "last_user": "Ali",
      "users": {
        "Ali": {
          "high_score": 420,
          "best_level": 2,
          "games_played": 5,
          "last_played": "2026-11-06"
        }
      }
    }

| Version | Where the file lives |
|---|---|
| Run from source | `savedata.json` next to `space_shooter.py` |
| Windows executable | `%APPDATA%\StarDefender\savedata.json` (or executable folder if writable) |
| Browser | Saved automatically in local storage; **E** exports file and **L** loads file back |

**Atomic Saving & Backup:** The game writes to a temporary file (`.tmp`) and replaces the main save file atomically to prevent corruption on sudden shutdowns. If an unreadable save file is encountered, it is backed up to `savedata.json.bak` instead of being overwritten.

---

## 7. Building and publishing

### 7.1 Windows executable

The tool used is **PyInstaller**. A PowerShell script, `build_exe.ps1`, automates the whole process.

1. Put `build_exe.ps1` in the same folder as `space_shooter.py`.
2. Run:

    powershell -ExecutionPolicy Bypass -File .\build_exe.ps1

3. The script creates a temporary virtual environment, installs `pygame-ce` and `pyinstaller`, builds a single windowed `.exe`, and produces `dist\StarDefender.exe` and `dist\StarDefender-windows.zip`.

The script builds from a temporary copy of the source in which only the `SAVE_FILE` line is replaced (to use the Documents folder). The original source file is not modified, and the gameplay code is identical.

### 7.2 Publishing the executable (GitHub Releases)

1. In the repository, open **Releases → Draft a new release**.
2. Create a tag such as `v1.0`.
3. Attach `StarDefender-windows.zip` and publish.

### 7.3 Publishing the browser version (itch.io)

1. Create a project with **Kind of project: HTML**.
2. Upload `star-defender-itch.zip` (it contains `index.html` at the root).
3. Tick **This file will be played in the browser**, set the viewport to **800 × 700**, and enable fullscreen.

---

## 8. Known limitations

- The Windows executable is unsigned, so Windows SmartScreen shows a warning on first run.
- The executable is built for Windows only. macOS and Linux builds must be made on those systems.
- The browser version supports keyboard play on desktop only (no touch controls).
- In the browser version, the `E` download depends on the hosting page allowing downloads; if it does not work on a given site, the high score is still kept automatically in local storage.
- The first launch of the single-file executable can take a few seconds while it unpacks and generates the sounds.

---

## 9. Project files

| File | Purpose |
|---|---|
| `space_shooter.py` | The game (Python / pygame) |
| `build_exe.ps1` | Builds the Windows executable with PyInstaller |
| `index.html` | Browser version (JavaScript port, single file) |
| `DOCUMENTATION.md` / PDF | This document |
| `savedata.json` | Created at run time; holds player profiles, high scores, and settings |
