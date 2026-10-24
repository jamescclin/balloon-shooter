"""讀取 USB 手把 (Linux joystick 介面 /dev/input/jsN)，不需要額外套件。

每個事件 8 bytes: struct js_event { u32 time; s16 value; u8 type; u8 number; }
"""
import os
import select
import struct

_EVENT = struct.Struct("IhBB")
_BUTTON = 0x01
_AXIS = 0x02
_INIT = 0x80  # 開啟裝置時送出的初始狀態，不算按下


class Gamepad:
    def __init__(self, device="/dev/input/js0"):
        try:
            self.fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            raise RuntimeError(f"無法開啟手把 {device}: {e}\n請用 `ls /dev/input/js*` 確認手把已連接。") from e
        self.axes = {}
        self.buttons = {}

    def poll(self, timeout=0.0):
        """讀取所有待處理的事件，回傳這段期間被按下的按鍵編號。"""
        pressed = []
        if not select.select([self.fd], [], [], timeout)[0]:
            return pressed
        while True:
            try:
                data = os.read(self.fd, _EVENT.size * 32)
            except BlockingIOError:
                break
            except OSError as e:
                raise RuntimeError(f"手把已斷線: {e}") from e
            if not data:
                break
            for offset in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
                _, value, kind, number = _EVENT.unpack_from(data, offset)
                if kind & _BUTTON:
                    if value and not kind & _INIT:
                        pressed.append(number)
                    self.buttons[number] = bool(value)
                elif kind & _AXIS:
                    self.axes[number] = value / 32767
        return pressed

    def axis(self, number):
        """-1.0 ~ 1.0"""
        return self.axes.get(number, 0.0)

    def held(self, number):
        return self.buttons.get(number, False)

    def close(self):
        os.close(self.fd)
