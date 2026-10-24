"""攝影機開啟工具，支援 Jetson MIPI (CSI) 與 USB 攝影機。

複製自 ai-balloon/detection/camera.py。

source 格式:
    mipi        -> MIPI 攝影機 sensor-id=0
    mipi:1      -> MIPI 攝影機 sensor-id=1
    usb         -> USB 攝影機 /dev/video0
    usb:1       -> USB 攝影機 /dev/video1
    /dev/video2 -> 指定裝置路徑
    0           -> 攝影機編號
    其他字串     -> 視為影片檔路徑 (方便在沒有攝影機時測試)
"""
import sys

import cv2


def mipi_pipeline(sensor_id=0, width=1280, height=720, fps=30, flip=0):
    """建立 Jetson MIPI 攝影機的 GStreamer pipeline (nvarguscamerasrc)。

    在 NVMM 記憶體中以硬體 (nvvidconv) 完成縮放與色彩轉換，降低 CPU 負擔。
    """
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, format=NV12, framerate={fps}/1 ! "
        f"nvvidconv flip-method={flip} ! "
        f"video/x-raw, width={width}, height={height}, format=BGRx ! "
        "videoconvert ! "
        "video/x-raw, format=BGR ! "
        "appsink drop=1 max-buffers=1"
    )


def _open_usb(device, width, height, fps):
    backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
    cap = cv2.VideoCapture(device, backend)
    # 多數 USB 攝影機在 720p 以上需使用 MJPG 才能達到 30 FPS
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    # 只保留最新畫面，避免推論較慢時延遲越積越多
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def open_camera(source="mipi", width=1280, height=720, fps=30, flip=0):
    """依 source 開啟攝影機，回傳 cv2.VideoCapture。開啟失敗時拋出 RuntimeError。"""
    source = str(source)

    if source.startswith("mipi"):
        sensor_id = int(source.split(":", 1)[1]) if ":" in source else 0
        cap = cv2.VideoCapture(mipi_pipeline(sensor_id, width, height, fps, flip), cv2.CAP_GSTREAMER)
    elif source.startswith("usb"):
        index = int(source.split(":", 1)[1]) if ":" in source else 0
        cap = _open_usb(index, width, height, fps)
    elif source.startswith("/dev/video"):
        cap = _open_usb(source, width, height, fps)
    elif source.isdigit():
        cap = _open_usb(int(source), width, height, fps)
    else:
        cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        hint = ""
        if source.startswith("mipi"):
            hint = "\n請確認 MIPI 攝影機排線已接好，且 OpenCV 有 GStreamer 支援 (需使用 JetPack 內建的 OpenCV)。"
        elif source.startswith(("usb", "/dev/video")) or source.isdigit():
            hint = "\n請用 `v4l2-ctl --list-devices` 確認 USB 攝影機的裝置編號。"
        raise RuntimeError(f"無法開啟攝影機: {source}{hint}")

    return cap
