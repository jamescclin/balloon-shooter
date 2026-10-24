"""雲台 (pan / tilt) 角度控制與發射判斷。"""


class Axis:
    """單一軸的角度狀態。限制在 [min, max] (null 表示該方向不限制)，invert 用來配合馬達安裝方向。"""

    def __init__(self, name, cfg):
        self.name = name
        self.min = cfg.get("min")
        self.max = cfg.get("max")
        self.home = cfg["home"]
        self.sign = -1 if cfg.get("invert", False) else 1
        self.angle = self.home

    @property
    def unlimited(self):
        return self.min is None and self.max is None

    def clamp(self, angle):
        if self.min is not None:
            angle = max(self.min, angle)
        if self.max is not None:
            angle = min(self.max, angle)
        return angle

    def home_from(self, current):
        """從 current 回 home 的目標角度。可無限轉的軸走最短路徑，不把轉過的圈數轉回來。"""
        if not self.unlimited:
            return self.home
        return current + (self.home - current + 180) % 360 - 180


class Turret:
    def __init__(self, driver, cfg):
        self.driver = driver
        self.pan = Axis("pan", cfg["pan"])
        self.tilt = Axis("tilt", cfg["tilt"])
        aim = cfg["aim"]
        self.kp = aim["kp"]
        self.max_step = aim["max_step"]
        self.deadband = aim["deadband"]

    def home(self):
        self.set(self.pan.home_from(self.driver.get_angle("pan")),
                 self.tilt.home_from(self.driver.get_angle("tilt")))

    def set(self, pan, tilt):
        """直接設定兩軸角度 (度)，超出範圍會被限制。"""
        for axis, angle in ((self.pan, pan), (self.tilt, tilt)):
            axis.angle = axis.clamp(angle)
            self.driver.set_angle(axis.name, axis.angle)

    def track(self, pan_err, tilt_err):
        """依角度誤差做比例控制，往目標轉一步。

        誤差是從畫面量到的，代表「馬達目前實際位置」還差多少，所以以實際位置為基準，
        而不是上一次設定的目標 (步進馬達轉得慢，用目標會不斷累加而衝過頭)。
        """
        targets = []
        for axis, err in ((self.pan, pan_err), (self.tilt, tilt_err)):
            if abs(err) < self.deadband:
                targets.append(axis.angle)
                continue
            # kp < 1: 推論與馬達都有延遲，一次只修正部分誤差，避免來回震盪
            step = max(-self.max_step, min(self.max_step, self.kp * err))
            targets.append(self.driver.get_angle(axis.name) + axis.sign * step)
        self.set(*targets)


class FireControl:
    """連續 lock_frames 幀都對準才發射，兩次發射至少間隔 cooldown 秒。"""

    def __init__(self, cfg, armed=False):
        self.tolerance = cfg["lock_tolerance"]
        self.lock_frames = cfg["lock_frames"]
        self.cooldown = cfg["cooldown"]
        self.armed = armed
        self.locked_count = 0
        self.last_fire = float("-inf")

    def is_on_target(self, pan_err, tilt_err):
        return abs(pan_err) <= self.tolerance and abs(tilt_err) <= self.tolerance

    def update(self, on_target, now):
        """每幀呼叫一次，回傳此幀是否應該發射。"""
        self.locked_count = self.locked_count + 1 if on_target else 0
        if (self.armed and self.locked_count >= self.lock_frames
                and now - self.last_fire >= self.cooldown):
            self.last_fire = now
            self.locked_count = 0
            return True
        return False
