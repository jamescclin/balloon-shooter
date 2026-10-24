"""ULN2003 驅動板 + 28BYJ-48 步進馬達，由 Jetson 40-pin GPIO 直接控制。

每顆馬達用 4 支 GPIO 接 ULN2003 的 IN1~IN4，腳位在 config.yaml 設定 (BOARD 編號)。
28BYJ-48 必須用外部 5V 電源供電 (接 ULN2003 板的 + / -)，且 GND 要與 Jetson 共地。

步進馬達沒有絕對位置，啟動時的位置視為 home，所以啟動前要先手動把雲台擺正。
每顆馬達由各自的背景執行緒一步一步轉向目標，主迴圈只需要設定目標角度。
"""
import threading
import time

import Jetson.GPIO as GPIO

from .base import MotorDriver

# 半步驅動相序 (IN1~IN4)，解析度是全步的兩倍，轉動也較平順
HALF_STEP = (
    (1, 0, 0, 0), (1, 1, 0, 0), (0, 1, 0, 0), (0, 1, 1, 0),
    (0, 0, 1, 0), (0, 0, 1, 1), (0, 0, 0, 1), (1, 0, 0, 1),
)


class Stepper:
    def __init__(self, pins, steps_per_rev, step_delay, release_when_idle, start_angle=0.0):
        self.pins = list(pins)
        self.steps_per_deg = steps_per_rev / 360
        self.step_delay = step_delay
        self.release_when_idle = release_when_idle
        self.position = round(start_angle * self.steps_per_deg)
        self.target = self.position
        self._release_requested = False
        self._running = True
        self._cond = threading.Condition()
        GPIO.setup(self.pins, GPIO.OUT, initial=GPIO.LOW)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def angle(self):
        return self.position / self.steps_per_deg

    def move_to(self, angle):
        with self._cond:
            self.target = round(angle * self.steps_per_deg)
            self._cond.notify_all()

    def reset_position(self, angle):
        with self._cond:
            self.position = self.target = round(angle * self.steps_per_deg)
            self._cond.notify_all()

    def wait_idle(self, timeout=None):
        with self._cond:
            return self._cond.wait_for(lambda: self.position == self.target or not self._running, timeout)

    def release(self):
        with self._cond:
            self._release_requested = True
            self._cond.notify_all()

    def close(self):
        with self._cond:
            self._running = False
            self._cond.notify_all()
        self._thread.join(timeout=1.0)

    def _coils_off(self):
        GPIO.output(self.pins, (0, 0, 0, 0))

    def _run(self):
        # 只有這個執行緒會寫這顆馬達的 GPIO
        next_time = time.perf_counter()
        while True:
            with self._cond:
                while self._running and self.position == self.target:
                    if self.release_when_idle or self._release_requested:
                        self._coils_off()
                        self._release_requested = False
                    self._cond.notify_all()  # 喚醒 wait_idle
                    self._cond.wait()
                    next_time = time.perf_counter()
                if not self._running:
                    break
                self.position += 1 if self.target > self.position else -1
                phase = HALF_STEP[self.position % 8]
            GPIO.output(self.pins, phase)
            next_time += self.step_delay
            delay = next_time - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_time = time.perf_counter()
        self._coils_off()


class ULN2003Driver(MotorDriver):
    def __init__(self, cfg, step_delay=None):
        hw = cfg["driver"]["uln2003"]
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)

        def make(axis, start_angle):
            return Stepper(cfg[axis]["pins"], hw["steps_per_rev"],
                           step_delay or cfg[axis].get("step_delay", hw["step_delay"]),
                           hw["release_when_idle"], start_angle)

        self.motors = {
            "pan": make("pan", cfg["pan"]["home"]),
            "tilt": make("tilt", cfg["tilt"]["home"]),
            "trigger": make("trigger", 0.0),
        }
        self.fire_degrees = cfg["trigger"]["fire_degrees"]
        self.fire_return = cfg["trigger"]["return"]
        self._firing = threading.Lock()

    def set_angle(self, axis, angle):
        self.motors[axis].move_to(angle)

    def get_angle(self, axis):
        return self.motors[axis].angle

    def reset_position(self, axis, angle):
        self.motors[axis].reset_position(angle)

    def fire(self):
        if not self._firing.acquire(blocking=False):
            return
        threading.Thread(target=self._fire_cycle, daemon=True).start()

    def _fire_cycle(self):
        trigger = self.motors["trigger"]
        try:
            start = trigger.angle
            trigger.move_to(start + self.fire_degrees)
            trigger.wait_idle()
            if self.fire_return:
                trigger.move_to(start)
                trigger.wait_idle()
            else:
                trigger.reset_position(start)  # 單向轉 (例如凸輪轉一圈)，轉完視為回到原點
        finally:
            self._firing.release()

    def release(self):
        for motor in self.motors.values():
            motor.release()

    def close(self, timeout=15.0):
        """等馬達轉完 (例如回 home) 再斷電並釋放 GPIO。"""
        for motor in self.motors.values():
            motor.wait_idle(timeout)
        pins = []
        for motor in self.motors.values():
            motor.close()
            pins += motor.pins
        GPIO.cleanup(pins)
