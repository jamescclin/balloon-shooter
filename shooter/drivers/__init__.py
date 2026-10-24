"""馬達驅動。所有驅動都提供相同介面 (見 base.MotorDriver)，由 config.yaml 的 driver.type 選擇。"""


def create_driver(cfg, **kwargs):
    kind = cfg["driver"]["type"]
    # 延遲 import，沒有 Jetson.GPIO 的 PC 上仍可使用 mock
    if kind == "mock":
        from .mock import MockDriver
        return MockDriver(cfg)
    if kind == "uln2003":
        from .uln2003 import ULN2003Driver
        return ULN2003Driver(cfg, **kwargs)
    raise ValueError(f"未知的 driver.type: {kind} (可用: mock / uln2003)")
