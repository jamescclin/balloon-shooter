"""不接硬體的模擬驅動，只印出指令。用來在 PC 或沒接馬達的 Jetson 上測試流程。"""
import time

from .base import MotorDriver


class MockDriver(MotorDriver):
    def __init__(self, cfg, print_interval=0.5):
        self.angles = {"pan": cfg["pan"]["home"], "tilt": cfg["tilt"]["home"], "trigger": 0.0}
        self.print_interval = print_interval
        self._last_print = 0.0

    def set_angle(self, axis, angle, speed=None):
        self.angles[axis] = angle
        now = time.monotonic()
        if now - self._last_print >= self.print_interval:
            self._last_print = now
            print("[mock] " + "  ".join(f"{k}={v:6.1f}" for k, v in sorted(self.angles.items())))

    def get_angle(self, axis):
        return self.angles[axis]

    def reset_position(self, axis, angle):
        self.angles[axis] = angle

    def fire(self):
        print("[mock] FIRE!")
