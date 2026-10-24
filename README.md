# Space-Shooter Project Documentation

**Course project:** EF101-P05 — Python-Based 2D Game
**Genre:** Vertical space shooter
**Language / library:** Python 3 + pygame (pygame-ce for the packaged build)
**Assets:** None. All graphics are drawn with code and all sounds are synthesised at start-up, so the game uses no copyrighted or external files.

---

## 1. Overview

Space Shooter is a single-player arcade shooter. The player pilots a ship at the bottom of the screen and must destroy waves of invading ships and asteroids. Every 300 points the game moves to a harder level, with no upper limit. The run ends when all lives are lost, and the best score is saved to a file so it persists between sessions.

The game is available in three forms:

| Form | File | Who it is for |
|---|---|---|
| Python source | `space_shooter.py` | Marking / reading the code; run with Python + pygame |
| Windows executable | `StarDefender.exe` | Players with no Python installed (GitHub Releases) |
| Browser version | `index.html` (itch.io) | Anyone, with nothing to install |

The executable is built from the unmodified Python source. The browser version is a JavaScript port of the same game logic (a browser cannot run Python directly).

---

## 2. How to run

### 2.1 From source (Python)

```
pip install pygame
python space_shooter.py
```

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
| **Enter** | Start the game (title screen) |
| **R** | Restart (after game over, or from the pause screen) |
| **Esc** | Pause while playing; back to title from game over; quit from the title screen (desktop only) |
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

```
TITLE ──Enter──► PLAYING ◄──P/Esc──► PAUSED
                    │                   │
              lose all lives            R (restart)
                    ▼
                GAME_OVER ──R/Enter──► PLAYING
                    │
                  Esc ──► TITLE
```

---

## 5. Code structure (`space_shooter.py`)

The file is organised as small classes, each responsible for one thing.

| Class | Responsibility |
|---|---|
| `SaveData` | Loads and saves the high score and mute setting (JSON file) |
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
| Input events | `Game.handle_events()` (key *presses*) and `Player.handle_input()` (keys *held down*) |
| State / variables | `Game.state` (`TITLE`, `PLAYING`, `PAUSED`, `GAME_OVER`), plus score, level, lives, timers |
| Collisions | `Game.check_collisions()` — axis-aligned rectangle overlap (`Rect.colliderect`) |
| Coordinates | Origin `(0, 0)` is the **top-left**; x grows right, y grows **down**. Window is 800 × 700 |
| Timing / FPS | `clock.tick(60)` caps the frame rate; `dt` = seconds since the last frame (capped at 0.05 s) |
| Asset loading / persistence | `SaveData` (JSON on disk) and `SoundManager` (sounds synthesised at start-up) |

### 5.2 Frame-rate independence
Movement is always `position += velocity × dt`, so the game plays at the same speed on slow and fast computers. `dt` is capped at 0.05 s so a lag spike cannot teleport objects through each other.

### 5.3 Sound
Each effect is generated from a start frequency, an end frequency, a duration, a volume and a waveform (`square`, `sine` or `noise`) with a fading envelope. Effects: shoot, explode, hit, power-up, level-up, game over, rocket and blast. If no audio device is available, the game runs silently instead of crashing.

---

## 6. Saved data (high score)

The game stores two values in a small JSON file:

```json
{"high_score": 815, "muted": false}
```

The file is written when a game ends and when mute is toggled, and read at start-up. If the file is missing or damaged, the game starts with defaults (score 0, sound on) instead of crashing.

| Version | Where the file lives |
|---|---|
| Run from source | `savedata.json` next to `space_shooter.py` |
| Windows executable | `Documents\StarDefender\savedata.json` (created on first game over) |
| Browser | Saved automatically in the browser's local storage; **E** exports it as a real `savedata.json` file and **L** loads one back |

**Why the executable uses the Documents folder:** a packaged `.exe` unpacks itself to a temporary folder each time it runs, so a file stored "next to the program" would be lost. Documents is visible, backed up by many users, and survives re-downloading or deleting the `.exe`.

**Why the browser needs export/load:** a web page is not allowed to silently create files on a visitor's computer. The browser version therefore keeps the score in local storage and lets the player save and load a `savedata.json` file on request.

---

## 7. Building and publishing

### 7.1 Windows executable

The tool used is **PyInstaller**. A PowerShell script, `build_exe.ps1`, automates the whole process.

1. Put `build_exe.ps1` in the same folder as `space_shooter.py`.
2. Run:
   ```
   powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
   ```
3. The script creates a temporary virtual environment, installs `pygame-ce` and `pyinstaller`, builds a single windowed `.exe`, and produces `dist\StarDefender.exe` and `dist\StarDefender-windows.zip`.

The script builds from a **temporary copy** of the source in which only the `SAVE_FILE` line is replaced (to use the Documents folder). The original source file is not modified, and the gameplay code is identical.

### 7.2 Publishing the executable (GitHub Releases)

1. In the repository, open **Releases → Draft a new release**.
2. Create a tag such as `v1.0`.
3. Attach `StarDefender-windows.zip` and publish.

The source code stays in the repository; the executable sits beside it under Releases.

### 7.3 Publishing the browser version (itch.io)

1. Create a project with **Kind of project: HTML**.
2. Upload `star-defender-itch.zip` (it contains `index.html` at the root).
3. Tick **This file will be played in the browser**, set the viewport to **800 × 700**, and enable fullscreen.

---

## 8. Known limitations

- The Windows executable is unsigned, so Windows SmartScreen shows a warning on first run (see 2.2).
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
| `DOCUMENTATION.md` | This document |
| `savedata.json` | Created at run time; holds the high score and mute setting |
