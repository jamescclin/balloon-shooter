#!/usr/bin/env bash
# Jetson Orin Nano 環境安裝 (JetPack 6)。
# Python 環境的處理方式與 ai-balloon/install.sh 的 detect 相同。
set -e

if [ "$(uname -m)" != "aarch64" ]; then
    echo "This script is for Jetson (aarch64). On a PC, create a venv and run: pip install -r requirements.txt opencv-python"
    exit 1
fi

sudo apt-get update
sudo apt-get install -y v4l-utils python3-pip python3-venv libopenblas-dev

# --system-site-packages: 使用 JetPack 的 OpenCV (GStreamer) 與 TensorRT
python3 -m venv --system-site-packages venv
if ! grep -q "balloon-shooter jetson env" venv/bin/activate; then
    cat >> venv/bin/activate <<'EOF'

# >>> balloon-shooter jetson env >>>
export PYTHONNOUSERSITE=1
for _d in "$VIRTUAL_ENV"/lib/python3*/site-packages/nvidia/cu12/lib; do
    [ -d "$_d" ] && export LD_LIBRARY_PATH="/usr/lib/aarch64-linux-gnu:$_d${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
done
unset _d
# <<< balloon-shooter jetson env <<<
EOF
fi
source venv/bin/activate

pip install --upgrade pip

L4T_MAJOR=$(head -1 /etc/nv_tegra_release 2>/dev/null | sed -n 's/^# R\([0-9]*\).*/\1/p')
if ! python3 -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
    if [ "$L4T_MAJOR" = "36" ]; then
        echo "Installing PyTorch for Jetson (JetPack 6 / CUDA 12.6)..."
        pip install --extra-index-url https://pypi.jetson-ai-lab.io/jp6/cu126 \
            torch==2.11.0 torchvision==0.26.0
    else
        echo "WARNING: PyTorch with CUDA not found."
        echo "Install NVIDIA's PyTorch L4T wheel BEFORE continuing, otherwise pip will pull a CPU-only build:"
        echo "  https://forums.developer.nvidia.com/t/pytorch-for-jetson/72048"
    fi
fi
pip install -r requirements.txt

# 同 ai-balloon: 移除會覆蓋 JetPack OpenCV 的 pip opencv，以及不適用 Jetson 的 pip cuBLAS
pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python 2>/dev/null || true
rm -rf "$VIRTUAL_ENV"/lib/python3*/site-packages/cv2
pip uninstall -y nvidia-cublas-cu12 nvidia-cublas 2>/dev/null || true
python3 -c "import cv2; print('OpenCV', cv2.__version__, '| GStreamer:', 'YES' if 'GStreamer:                   YES' in cv2.getBuildInformation() else 'NO')"

# 讓一般使用者 (不用 sudo) 控制 GPIO，重新登入後生效
sudo groupadd -f -r gpio
sudo usermod -aG gpio "$USER"
GPIO_RULES=$(ls "$VIRTUAL_ENV"/lib/python3*/site-packages/Jetson/GPIO/99-gpio.rules \
    /usr/lib/python3/dist-packages/Jetson/GPIO/99-gpio.rules 2>/dev/null | head -1)
if [ -n "$GPIO_RULES" ] && [ ! -f /etc/udev/rules.d/99-gpio.rules ]; then
    sudo cp "$GPIO_RULES" /etc/udev/rules.d/
    sudo udevadm control --reload-rules && sudo udevadm trigger
fi

echo "Environment setup is complete!"
echo "Log out and back in once so the gpio group takes effect."
echo "To activate the virtual environment, run: source venv/bin/activate"
