# balloon-shooter

English | [繁體中文](README.zh-TW.md)

Uses the balloon detection model from [ai-balloon](https://github.com/jamescclin/ai-balloon) to aim a pan-tilt turret at balloons from a Jetson Orin Nano, then fire.

```text
camera ──> YOLO (balloon.engine) ──> pick target ──> angle error ──> pan / tilt steppers
                                     (nearest to         │
                                      crosshair)         └─> on target for N frames ──> trigger stepper
```

The camera is mounted on the turret and turns with the launcher. How far the balloon is from the crosshair (in degrees) is how far the turret still has to turn.

Beginner tutorial for junior high students (Traditional Chinese): [docs/tutorial.zh-TW.md](docs/tutorial.zh-TW.md)

```text
balloon-shooter/
├── main.py                  # Detect -> aim -> fire
├── config.yaml              # Model, camera, GPIO pins, motor, gamepad and control settings
├── shooter/
│   ├── camera.py            # MIPI / USB camera (copied from ai-balloon)
│   ├── detector.py          # YOLO wrapper
│   ├── targeting.py         # Target choice, pixel -> angle
│   ├── turret.py            # Pan/tilt control, fire decision
│   ├── gamepad.py           # USB gamepad reader (/dev/input/js0)
│   └── drivers/             # Motor drivers: uln2003 / mock
├── tools/
│   ├── motor_gamepad.py     # Drive the motors with a USB gamepad
│   └── motor_keyboard.py    # Drive the motors from the keyboard
├── requirements.txt
└── install.sh               # Jetson setup
```

## 1. Hardware

Three ULN2003 driver boards with 28BYJ-48 stepper motors: pan (horizontal), tilt (vertical) and trigger (launcher). Each board takes 4 GPIO pins from the Jetson 40-pin header (BOARD numbering, set in `config.yaml`):

| Motor | IN1 | IN2 | IN3 | IN4 |
|---|---|---|---|---|
| pan | 7 | 11 | 13 | 15 |
| tilt | 29 | 31 | 33 | 35 |
| trigger | 37 | 16 | 18 | 22 |

The trigger's IN1 was planned for pin 12, but pin 12 gave no output on our Jetson, so it uses pin 37.

Power:

- Power the ULN2003 boards (`+` / `-`) from an **external 5 V supply** (2 A or more). Don't use the Jetson's 5 V pins. Each 28BYJ-48 draws about 240 mA, and current spikes can reset the Jetson.
- **Connect the supply's GND to a Jetson GND pin** (for example pin 6). Without a common ground, the GPIO signals don't reach the boards.
- The ULN2003 inputs work with the Jetson's 3.3 V GPIO.

A USB gamepad is optional, for driving the motors by hand. We use a "Twin USB Joystick" PS2 adapter (USB ID `2563:0555`).

## 2. Setup (Jetson)

Clone this repo next to ai-balloon. By default `config.yaml` loads the model from `../ai-balloon/models/balloon.engine`.

```text
~/Documents/workspace/ai-balloon/models/balloon.engine   # built on the Jetson with ai-balloon/detection/export_engine.py
~/Documents/workspace/balloon-shooter/
```

```bash
./install.sh
# Log out and back in once (adds you to the gpio group)
source venv/bin/activate
```

The motor tools only need `Jetson.GPIO` and `pyyaml`. JetPack's system `python3` already has both, so you can run them before `install.sh`.

### GPIO pinmux (JetPack 6)

On JetPack 6, most 40-pin header pins start with their output driver turned off. `Jetson.GPIO` then writes to the pin **without any error, but nothing comes out**: the ULN2003 LED stays dark and the motor doesn't move. Pins that default to a pull-up (29 and 31) keep their LED lit all the time instead.

Check a pin's state (`tristate=1` means the output is off):

```bash
sudo grep -A14 "(soc_gpio32_pq5)" /sys/kernel/debug/pinctrl/2430000.pinmux/pinconf-groups | grep -E "tristate|pull="
```

To find a pin's group name, run `sudo grep PQ.05 /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-pins` with the GPIO name that `Jetson.GPIO` uses for that pin.

To turn the outputs on, add the pins to the 40-pin overlay with `nvidia,tristate = <0x00>`, then reboot:

- Use `sudo /opt/nvidia/jetson-io/jetson-io.py` to enable the functions on those pins, **or**
- Decompile `/boot/jetson-io-hdr40-user-custom.dtbo` with `dtc`, add a `hdr40-pinNN` node for each pin, then recompile it. Keep a backup of the original first.

Saving again from jetson-io may rewrite the overlay and drop pins you added by hand.

## 3. Gamepad motor control

Stepper motors have no absolute position: **the position at startup becomes home**, so center the turret by hand first. Then run:

```bash
python3 tools/motor_gamepad.py
```

| Button | Action |
|---|---|
| D-pad / left stick | pan / tilt; hold to keep turning |
| `L1` (hold) | Slow mode (1/4 speed) for fine aiming |
| `B` / `X` (hold) | Turn the trigger motor forward / back, no limit |
| `A` | Fire once |
| `Y` | Return pan / tilt to home |
| `SELECT` | Make the current position home |
| `R2` | Cut motor power (turn by hand) |
| `START` | Quit (returns home first) |

The button numbers are in the `gamepad` section of `config.yaml`. They were measured on the Twin USB Joystick adapter in digital mode, where the D-pad and the left stick both send axes 0/1. Other gamepads may use other numbers. To see which numbers your gamepad sends, read `/dev/input/js0` (see `shooter/gamepad.py`).

## 4. Keyboard motor test

If you have no gamepad, use the keyboard. It runs in a terminal, so it works from a keyboard plugged into the Jetson or over SSH.

```bash
python3 tools/motor_keyboard.py
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

## 5. Calibration

1. **Wiring**: run `python3 tools/motor_keyboard.py --step-delay 0.2` and press a key. The 4 LEDs on that ULN2003 board should light up one by one.
   - An LED that never lights: check that pin's wire and its pinmux (see [GPIO pinmux](#gpio-pinmux-jetpack-6)). To test the wire and the board, move the wire's Jetson end to pin 1 (3.3 V): the LED should light.
   - A motor that only buzzes in place: one phase is usually missing (an LED that doesn't light), or two IN wires are swapped.
2. **Direction**: if right turns pan left, or up turns tilt down, set `invert: true` for that axis. Our tilt motor needs `invert: true`.
3. **Range**: from home, move each axis until just before the mechanism jams, and note the angle shown. Enter the values as `min` / `max` in `config.yaml`. Use `--no-limit` to go past the current limits.
   - `min: null` / `max: null` removes the limit, so the axis can turn without end. Tilt is set this way now. An axis without limits returns home by the shortest path, so it never unwinds the turns it has made. Watch for cables that could wrap around.
4. **Trigger**: hold `B` / `X` to find the turn that launches a shot, and set `trigger.fire_degrees`. If the launcher must turn back after a shot, use `return: true`. If it only turns one way (for example a cam that turns a full circle), use `return: false`.

`steps_per_rev: 4096` is the nominal 28BYJ-48 half-step count, and `step_delay: 0.002` gives about 44°/s. If a motor buzzes or skips steps, raise `step_delay`. You can also set `step_delay` per motor in its section.

## 6. Run

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

## 7. Tuning

- **Field of view**: set `camera.hfov` to the camera's horizontal field of view. If the turret keeps overshooting or stops short, the value is probably wrong.
- **Control**: if the turret oscillates, lower `aim.kp`. If it is too slow, raise it.
- **Crosshair offset**: the launcher and the lens are not at the same spot. Put a balloon at the usual shooting distance and see where the shot lands. Use `aim.offset_x` / `offset_y` (pixels) to move the crosshair onto the point of impact.
- **Firing**: it fires only when both pan and tilt errors are under `fire.lock_tolerance` degrees for `fire.lock_frames` frames in a row. Two shots are at least `fire.cooldown` seconds apart.
