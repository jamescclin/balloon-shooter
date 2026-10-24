"""用鍵盤手動控制三顆步進馬達，確認接線、方向，並找出安全範圍。

在 Jetson 的終端機執行 (接實體鍵盤的桌面終端機或 SSH 皆可，需要 Linux):
    python tools/motor_keyboard.py                      # 依 config.yaml
    python tools/motor_keyboard.py --step-delay 0.2     # 放慢到肉眼看得出 ULN2003 板上 LED 依序亮
    python tools/motor_keyboard.py --no-limit           # 不套用 config.yaml 的 min / max
    python tools/motor_keyboard.py --driver mock        # 不接硬體

按鍵:
    ← / →  或 a / d    水平 (pan) 左 / 右
    ↑ / ↓  或 w / s    垂直 (tilt) 上 / 下
    [ / ]              發射器反轉 / 正轉 (微調位置)
    空白鍵             發射一次 (轉 trigger.fire_degrees，依 trigger.return 決定是否轉回)
    1 ~ 5              每按一下轉幾度: 1 / 2 / 5 / 10 / 30
    h                  水平 / 垂直回到 home
    z                  把目前位置設為 home (手動擺正後按)
    r                  馬達斷電，可用手轉動
    q / Esc            離開 (會先回到 home)

步進馬達沒有絕對位置，啟動時的位置就是 home，請先手動把雲台擺正再啟動。
"""
import argparse
import os
import select
import sys
import termios
import tty
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shooter.config import DEFAULT_CONFIG, load_config  # noqa: E402
from shooter.drivers import create_driver  # noqa: E402
from shooter.turret import Axis  # noqa: E402

MOVES = {
    "\x1b[D": ("pan", -1), "a": ("pan", -1),
    "\x1b[C": ("pan", 1), "d": ("pan", 1),
    "\x1b[A": ("tilt", 1), "w": ("tilt", 1),
    "\x1b[B": ("tilt", -1), "s": ("tilt", -1),
    "[": ("trigger", -1),
    "]": ("trigger", 1),
}
STEP_SIZES = {"1": 1, "2": 2, "3": 5, "4": 10, "5": 30}


def read_key(fd, timeout):
    """讀一個按鍵，逾時回傳 None。方向鍵是 3 個字元的 escape sequence。"""
    if not select.select([fd], [], [], timeout)[0]:
        return None
    key = os.read(fd, 1).decode(errors="ignore")
    if key == "\x1b" and select.select([fd], [], [], 0.05)[0]:
        key += os.read(fd, 2).decode(errors="ignore")
    return key


def main():
    parser = argparse.ArgumentParser(description="鍵盤控制步進馬達")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--driver", choices=["mock", "uln2003"], help="覆蓋 driver.type")
    parser.add_argument("--step-delay", type=float, help="覆蓋每半步間隔 (秒)，放慢用來檢查接線")
    parser.add_argument("--no-limit", action="store_true", help="不套用 config.yaml 的 min / max")
    args = parser.parse_args()

    if not sys.stdin.isatty():
        sys.exit("請在終端機中直接執行 (需要讀取鍵盤)。")

    cfg = load_config(args.config)
    if args.driver:
        cfg["driver"]["type"] = args.driver
    kwargs = {"step_delay": args.step_delay} if cfg["driver"]["type"] == "uln2003" else {}
    driver = create_driver(cfg, **kwargs)
    if cfg["driver"]["type"] == "mock":
        driver.print_interval = float("inf")  # 狀態列已顯示角度

    axes = {name: Axis(name, cfg[name]) for name in ("pan", "tilt")}
    targets = {"pan": axes["pan"].home, "tilt": axes["tilt"].home, "trigger": 0.0}
    step = 5

    def clamp(axis, angle):
        if args.no_limit or axis == "trigger":
            return angle
        return axes[axis].clamp(angle)

    def go_home():
        for name, a in axes.items():
            targets[name] = a.home_from(driver.get_angle(name))
            driver.set_angle(name, targets[name])

    print(__doc__.split("按鍵:")[1].split("步進馬達沒有")[0])
    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    tty.setcbreak(fd)  # 不需按 Enter 就能讀到按鍵；Ctrl+C 仍有效
    try:
        while True:
            key = read_key(fd, 0.1)
            if key in ("q", "\x1b"):
                break
            if key in MOVES:
                axis, direction = MOVES[key]
                if axis != "trigger":
                    direction *= axes[axis].sign
                targets[axis] = clamp(axis, targets[axis] + direction * step)
                driver.set_angle(axis, targets[axis])
            elif key in STEP_SIZES:
                step = STEP_SIZES[key]
            elif key == " ":
                driver.fire()
            elif key == "h":
                go_home()
            elif key == "z":
                for name, a in axes.items():
                    targets[name] = a.home
                    driver.reset_position(name, a.home)
            elif key == "r":
                driver.release()

            status = "  ".join(
                f"{axis} {driver.get_angle(axis):+7.1f}" + (f" -> {targets[axis]:+7.1f}" if axis != "trigger" else "")
                for axis in ("pan", "tilt", "trigger")
            )
            sys.stdout.write(f"\r{status}  step {step:2d}°\x1b[K")
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        print("\n回到 home...")
        go_home()
        driver.close()


if __name__ == "__main__":
    main()
