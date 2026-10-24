"""偵測氣球、控制雲台瞄準並發射。

範例:
    python main.py                          # 依 config.yaml，不發射 (只瞄準)
    python main.py --arm                    # 允許發射
    python main.py --source usb --headless  # USB 攝影機，不開視窗 (透過 SSH 執行時使用)
    python main.py --driver mock --source test.mp4   # 不接馬達，用影片測試

啟動時的雲台位置就是 home (步進馬達沒有絕對位置)，請先手動擺正再啟動。
視窗按鍵: q 離開 / a 切換是否允許發射 / h 回到 home
"""
import argparse
import sys
import time
from pathlib import Path

import cv2

from shooter.camera import open_camera
from shooter.config import DEFAULT_CONFIG, load_config
from shooter.detector import BalloonDetector
from shooter.drivers import create_driver
from shooter.targeting import aim_point, angle_error, select_target
from shooter.turret import FireControl, Turret


def parse_args():
    parser = argparse.ArgumentParser(description="氣球射擊雲台")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--model", help="覆蓋 model.path")
    parser.add_argument("--source", help="覆蓋 camera.source")
    parser.add_argument("--driver", choices=["mock", "uln2003"], help="覆蓋 driver.type")
    parser.add_argument("--arm", action="store_true", help="允許發射 (預設只瞄準不發射)")
    parser.add_argument("--headless", action="store_true", help="不開啟視窗，只在終端機輸出")
    return parser.parse_args()


def draw_overlay(frame, detections, target, aim_xy, status):
    ax, ay = int(aim_xy[0]), int(aim_xy[1])
    for d in detections:
        color = (0, 0, 255) if d is target else (0, 255, 0)
        cv2.rectangle(frame, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), color, 2)
        cv2.putText(frame, f"{d.conf:.2f}", (int(d.x1), int(d.y1) - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    if target:
        cv2.line(frame, (ax, ay), (int(target.cx), int(target.cy)), (0, 0, 255), 1)
    cv2.drawMarker(frame, (ax, ay), (255, 255, 0), cv2.MARKER_CROSS, 30, 2)
    cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)


def main():
    args = parse_args()
    cfg = load_config(args.config)
    if args.model:
        cfg["model"]["path"] = args.model
    if args.source:
        cfg["camera"]["source"] = args.source
    if args.driver:
        cfg["driver"]["type"] = args.driver

    model_path = Path(cfg["model"]["path"])
    if not model_path.exists():
        sys.exit(f"找不到模型: {model_path}\n"
                 "請先在 ai-balloon 執行 detection/export_engine.py 產生 TensorRT engine，"
                 "或用 --model 指定模型路徑。")

    cam = cfg["camera"]
    aim = cfg["aim"]
    detector = BalloonDetector(model_path, cfg["model"]["imgsz"], cfg["model"]["conf"])
    try:
        cap = open_camera(cam["source"], cam["width"], cam["height"], cam["fps"], cam["flip"])
    except RuntimeError as e:
        sys.exit(str(e))

    driver = create_driver(cfg)
    turret = Turret(driver, cfg)
    fire_ctl = FireControl(cfg["fire"], armed=args.arm)
    turret.home()

    print(f"驅動: {cfg['driver']['type']}  發射: {'ARMED' if fire_ctl.armed else '關閉 (加 --arm 開啟)'}")
    print("開始... " + ("(Ctrl+C 離開)" if args.headless else "(視窗按鍵: q 離開 / a 切換發射 / h 回 home)"))

    fps = 0.0
    prev = time.perf_counter()
    last_seen = time.monotonic()
    at_home = True
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("無法讀取攝影機畫面。")
                break

            h, w = frame.shape[:2]
            aim_xy = aim_point(w, h, aim["offset_x"], aim["offset_y"])
            detections = detector.detect(frame)
            target = select_target(detections, *aim_xy)
            now = time.monotonic()

            if target:
                last_seen = now
                at_home = False
                pan_err, tilt_err = angle_error(target, *aim_xy, w, cam["hfov"])
                turret.track(pan_err, tilt_err)
                if fire_ctl.update(fire_ctl.is_on_target(pan_err, tilt_err), now):
                    driver.fire()
                    print(f"FIRE  pan={turret.pan.angle:.1f} tilt={turret.tilt.angle:.1f}")
            else:
                pan_err = tilt_err = None
                fire_ctl.update(False, now)
                if (not at_home and aim["return_home_after"] > 0
                        and now - last_seen > aim["return_home_after"]):
                    turret.home()
                    at_home = True

            t = time.perf_counter()
            fps = 0.9 * fps + 0.1 / (t - prev) if fps else 1.0 / (t - prev)
            prev = t

            err_text = f"err=({pan_err:+.1f},{tilt_err:+.1f})" if target else "no target"
            status = (f"{fps:4.1f} FPS  {len(detections)} balloons  {err_text}  "
                      f"pan={turret.pan.angle:.0f} tilt={turret.tilt.angle:.0f}  "
                      f"{'ARMED' if fire_ctl.armed else 'SAFE'}")

            if args.headless:
                if target:
                    print(status)
                continue

            draw_overlay(frame, detections, target, aim_xy, status)
            cv2.imshow("Balloon Shooter", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("a"):
                fire_ctl.armed = not fire_ctl.armed
                print("發射: " + ("ARMED" if fire_ctl.armed else "SAFE"))
            elif key == ord("h"):
                turret.home()
                at_home = True
    except KeyboardInterrupt:
        pass
    finally:
        turret.home()
        driver.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
