from abc import ABC, abstractmethod


class MotorDriver(ABC):
    """馬達驅動介面。

    axis 為 "pan" / "tilt" / "trigger"，角度單位為度。
    範圍限制與方向反轉由 Turret 處理，驅動只負責把角度送到硬體。
    """

    @abstractmethod
    def set_angle(self, axis, angle, speed=None):
        """設定目標角度。不阻塞，馬達會在背景轉過去。speed 為度/秒，None 表示最快速度。"""

    def stop(self, axis):
        """停在目前位置。"""
        self.set_angle(axis, self.get_angle(axis))

    @abstractmethod
    def get_angle(self, axis):
        """馬達目前實際所在的角度 (轉動中時與目標不同)。"""

    @abstractmethod
    def reset_position(self, axis, angle):
        """把目前位置當成 angle (用手把雲台擺正後重新歸零)。"""

    @abstractmethod
    def fire(self):
        """發射一次。不阻塞；發射動作還沒結束時再呼叫會被忽略。"""

    def release(self):
        """馬達斷電 (可用手轉動)。"""

    def close(self):
        pass
