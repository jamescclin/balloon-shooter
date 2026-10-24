# balloon-shooter

English | [繁體中文](README.zh-TW.md)

Uses the balloon detection model from [ai-balloon](https://github.com/jamescclin/ai-balloon) to aim a pan-tilt turret at balloons from a Jetson Orin Nano, then fire.

```text
camera ──> YOLO (balloon.engine) ──> pick target ──> angle error ──> pan / tilt steppers
                                     (nearest to         │
                                      crosshair)         └─> on target for N frames ──> trigger stepper
```

The camera is mounted on the turret and turns with the launcher. How far the balloon is from the crosshair (in degrees) is how far the turret still has to turn.

```text
balloon-shooter/
├── main.py                  # Detect -> aim -> fire
├── config.yaml              # Model, camera, GPIO pins, motor and control settings
├── shooter/
│   ├── camera.py            # MIPI / USB camera (copied from ai-balloon)
│   ├── detector.py          # YOLO wrapper
│   ├── targeting.py         # Target choice, pixel -> angle
│   ├── turret.py            # Pan/tilt control, fire decision
│   └── drivers/             # Motor drivers: uln2003 / mock
├── tools/motor_keyboard.py  # Drive the motors from the keyboard
├── requirements.txt
└── install.sh               # Jetson setup
```

## 1. Hardware

Three ULN2003 driver boards with 28BYJ-48 stepper motors: pan (horizontal), tilt (vertical) and trigger (launcher). Each board takes 4 GPIO pins from the Jetson 40-pin header (BOARD numbering, set in `config.yaml`):

| Motor | IN1 | IN2 | IN3 | IN4 |
|---|---|---|---|---|
| pan | 7 | 11 | 13 | 15 |
| tilt | 29 | 31 | 33 | 35 |
| trigger | 12 | 16 | 18 | 22 |

Power:

- Power the ULN2003 boards (`+` / `-`) from an **external 5 V supply** (2 A or more). Don't use the Jetson's 5 V pins. Each 28BYJ-48 draws about 240 mA, and current spikes can reset the Jetson.
- **Connect the supply's GND to a Jetson GND pin** (for example pin 6). Without a common ground, the GPIO signals don't reach the boards.
- The ULN2003 inputs work with the Jetson's 3.3 V GPIO.

## 2. Setup (Jetson)

Clone this repo next to ai-balloon. By default `config.yaml` loads the model from `../ai-balloon/models/balloon.engine`.

```text
~/ai-balloon/models/balloon.engine   # built on the Jetson with ai-balloon/detection/export_engine.py
~/balloon-shooter/
```

```bash
./install.sh
# Log out and back in once (adds you to the gpio group)
source venv/bin/activate
```

## 3. Keyboard motor test

Before you run detection, check each motor with the keyboard. Stepper motors have no absolute position: **the position at startup becomes home**, so center the turret by hand first.

```bash
python tools/motor_keyboard.py
```

| Key | Action |
|---|---|
| `←` `→` / `a` `d` | pan left / right |
| `↑` `↓` / `w` `s` | tilt up / down |
| `[` `]` | Turn the trigger motor back / forward (fine adjustment) |
| `Space` | Fire once |
| `1`–`5` | Degrees per key press: 1 / 2 / 5 / 10 / 30 |
| `h` | Return pan / tilt to home |
| `z` | Make the current position home |
| `r` | Cut motor power (turn by hand) |
| `q` / `Esc` | Quit (returns home first) |

It runs in a terminal, so it works from a keyboard plugged into the Jetson or over SSH. Check:

1. **Wiring**: run `python tools/motor_keyboard.py --step-delay 0.2` and press a key. The 4 LEDs on that ULN2003 board should light up one by one. If an LED never lights, check that pin's wiring. If all LEDs light but the motor only buzzes, two IN wires are probably swapped.
2. **Direction**: if `→` turns pan left or `↑` turns tilt down, set `invert: true` for that axis.
3. **Range**: from home, move each axis until just before the mechanism jams, and note the angle shown. Enter the values as `min` / `max` in `config.yaml`. Use `--no-limit` to go past the current limits.
4. **Trigger**: use `[` `]` to find the turn that launches a shot, and set `trigger.fire_degrees`. If the launcher must turn back after a shot, use `return: true`. If it only turns one way (for example a cam that turns a full circle), use `return: false`.

`steps_per_rev: 4096` is the nominal 28BYJ-48 half-step count, and `step_delay: 0.002` gives about 44°/s. If a motor buzzes or skips steps, raise `step_delay`. You can also set `step_delay` per motor in its section.

## 4. Run

Center the turret by hand, then:

```bash
python main.py                         # MIPI camera, with a window, no firing
python main.py --source usb --headless # USB camera, over SSH
python main.py --arm                   # Allow firing
```

In the window, the red box is the current target and the cross is the crosshair. Keys: `q` quit, `a` toggle firing, `h` go home. On exit the turret returns home, so the next start is centered.

To test without motors, use `--driver mock` (you can also run it on a PC with a video file, `balloon.pt` and `opencv-python`):

```bash
python main.py --driver mock --model ../ai-balloon/models/balloon.pt --source test.mp4
```

## 5. Tuning

- **Field of view**: set `camera.hfov` to the camera's horizontal field of view. If the turret keeps overshooting or stops short, the value is probably wrong.
- **Control**: if the turret oscillates, lower `aim.kp`. If it is too slow, raise it.
- **Crosshair offset**: the launcher and the lens are not at the same spot. Put a balloon at the usual shooting distance and see where the shot lands. Use `aim.offset_x` / `offset_y` (pixels) to move the crosshair onto the point of impact.
- **Firing**: it fires only when both pan and tilt errors are under `fire.lock_tolerance` degrees for `fire.lock_frames` frames in a row. Two shots are at least `fire.cooldown` seconds apart.
