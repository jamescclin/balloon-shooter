"""用 USB 手把控制三顆步進馬達。按鍵編號在 config.yaml 的 gamepad 區段設定。

範例:
    python tools/motor_gamepad.py
    python tools/motor_gamepad.py --no-limit        # 不套用 config.yaml 的 min / max
    python tools/motor_gamepad.py --driver mock     # 不接馬達

操作 (預設配置):
    十字鍵 / 左搖桿    水平 / 垂直，按住持續轉動
    L1 (按住)          慢速，用來微調
    A                  發射
    X / B (按住)       發射器反轉 / 正轉，可無限轉
    Y                  水平 / 垂直回到 home
    SELECT             把目前位置設為 home
    R2                 馬達斷電 (可用手轉動)
    START / Ctrl+C     離開 (會先回到 home)

步進馬達沒有絕對位置，啟動時的位置就是 home，請先手動把雲台擺正再啟動。
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shooter.config import DEFAULT_CONFIG, load_config  # noqa: E402
from shooter.drivers import create_driver  # noqa: E402
from shooter.gamepad import Gamepad  # noqa: E402
from shooter.turret import Axis  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="手把控制步進馬達")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--driver", choices=["mock", "uln2003"], help="覆蓋 driver.type")
    parser.add_argument("--no-limit", action="store_true", help="不套用 config.yaml 的 min / max")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.driver:
        cfg["driver"]["type"] = args.driver
    pad_cfg = cfg["gamepad"]
    btn = pad_cfg["buttons"]

    try:
        pad = Gamepad(pad_cfg["device"])
    except RuntimeError as e:
        sys.exit(str(e))
    driver = create_driver(cfg)
    if cfg["driver"]["type"] == "mock":
        driver.print_interval = float("inf")  # 由下面的狀態輸出顯示角度

    axes = {name: Axis(name, cfg[name]) for name in ("pan", "tilt")}
    # 搖桿往右 / 往上為正；Linux joystick 的 Y 軸往上是負值
    sticks = {"pan": (pad_cfg["pan_axis"], 1), "tilt": (pad_cfg["tilt_axis"], -1)}
    moving = {"pan": None, "tilt": None, "trigger": None}  # 目前送給馬達的 (方向, 速度)，避免每圈重送

    def limits(axis):
        """沒有限制時用很遠的角度當目標，放開時再 stop。發射器不限制。"""
        if axis == "trigger":
            return -1e6, 1e6
        a = axes[axis]
        lo = -1e6 if args.no_limit or a.min is None else a.min
        hi = 1e6 if args.no_limit or a.max is None else a.max
        return lo, hi

    def go_home():
        for name, a in axes.items():
            driver.set_angle(name, a.home_from(driver.get_angle(name)))

    print(__doc__.split("操作 (預設配置):")[1].split("步進馬達沒有")[0])
    last_status, last_print = None, 0.0
    try:
        while True:
            pressed = pad.poll(0.02)
            if btn["quit"] in pressed:
                break

            speed_scale = pad_cfg["slow_factor"] if pad.held(btn["slow"]) else 1.0
            inputs = {axis: pad.axis(stick_axis) * sign * axes[axis].sign
                      for axis, (stick_axis, sign) in sticks.items()}
            inputs["trigger"] = float(pad.held(btn["trigger_forward"])) - float(pad.held(btn["trigger_back"]))
            for axis, value in inputs.items():
                lo, hi = limits(axis)
                angle = driver.get_angle(axis)
                if abs(value) < pad_cfg["deadzone"] or (value > 0 and angle >= hi) or (value < 0 and angle <= lo):
                    state = None
                else:
                    state = (1 if value > 0 else -1, round(abs(value) * pad_cfg["max_speed"] * speed_scale, 1))
                if state == moving[axis]:
                    continue
                moving[axis] = state
                if state is None:
                    driver.stop(axis)
                else:
                    # 目標設在範圍邊界，放開搖桿時再 stop
                    driver.set_angle(axis, hi if state[0] > 0 else lo, speed=state[1])

            if btn["fire"] in pressed:
                driver.fire()
                print("FIRE")
            if btn["home"] in pressed:
                go_home()
                moving.update(pan=None, tilt=None)
                print("回到 home")
            if btn["zero"] in pressed:
                for name, a in axes.items():
                    driver.reset_position(name, a.home)
                print("目前位置設為 home")
            if btn["release"] in pressed:
                driver.release()
                print("馬達斷電")

            status = tuple(round(driver.get_angle(a), 1) for a in ("pan", "tilt", "trigger"))
            now = time.monotonic()
            if status != last_status and now - last_print >= 0.3:
                last_status, last_print = status, now
                print("pan {:+7.1f}  tilt {:+7.1f}  trigger {:+7.1f}".format(*status), flush=True)
    except KeyboardInterrupt:
        pass
    except RuntimeError as e:  # 手把斷線
        print(e)
    finally:
        print("回到 home...")
        go_home()
        driver.close()
        pad.close()


if __name__ == "__main__":
    main()
