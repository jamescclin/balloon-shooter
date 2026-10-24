"""目標選擇與像素 -> 角度換算。

攝影機裝在雲台上、與槍管一起轉動，所以「目標在畫面中偏離準心多少度」
就是雲台還需要轉多少度。
"""
import math


def aim_point(width, height, offset_x=0, offset_y=0):
    """準心在畫面中的像素座標。offset 用來補償槍管與鏡頭的視差。"""
    return width / 2 + offset_x, height / 2 + offset_y


def select_target(detections, aim_x, aim_y):
    """選擇離準心最近的氣球，沒有氣球時回傳 None。"""
    if not detections:
        return None
    return min(detections, key=lambda d: (d.cx - aim_x) ** 2 + (d.cy - aim_y) ** 2)


def angle_error(target, aim_x, aim_y, width, hfov_deg):
    """回傳 (pan_err, tilt_err)，單位為度。

    pan_err > 0: 目標在準心右邊，需要往右轉
    tilt_err > 0: 目標在準心上方，需要往上抬
    假設像素為正方形，垂直方向的焦距與水平相同，所以只需要水平視角。
    """
    focal_px = (width / 2) / math.tan(math.radians(hfov_deg) / 2)
    pan_err = math.degrees(math.atan2(target.cx - aim_x, focal_px))
    tilt_err = math.degrees(math.atan2(aim_y - target.cy, focal_px))
    return pan_err, tilt_err
