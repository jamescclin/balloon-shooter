# balloon-shooter

[English](README.md) | 繁體中文

使用 [ai-balloon](https://github.com/jamescclin/ai-balloon) 訓練的氣球偵測模型，由 Jetson Orin Nano 控制雲台瞄準氣球並發射。

```text
攝影機 ──> YOLO (balloon.engine) ──> 選擇目標 ──> 角度誤差 ──> 水平 / 垂直步進馬達
                                    (離準心最近)       │
                                                       └─> 連續 N 幀對準 ──> 發射器步進馬達
```

攝影機裝在雲台上，跟著發射器一起轉動。氣球偏離準心幾度，雲台就還需要轉幾度。

給國中生的入門教學：[docs/tutorial.zh-TW.md](docs/tutorial.zh-TW.md)

```text
balloon-shooter/
├── main.py                  # 偵測 -> 瞄準 -> 發射
├── config.yaml              # 模型、攝影機、GPIO 腳位、馬達、手把與控制參數
├── shooter/
│   ├── camera.py            # MIPI / USB 攝影機 (複製自 ai-balloon)
│   ├── detector.py          # YOLO 包裝
│   ├── targeting.py         # 目標選擇、像素 -> 角度換算
│   ├── turret.py            # 雲台控制、發射判斷
│   ├── gamepad.py           # USB 手把讀取 (/dev/input/js0)
│   └── drivers/             # 馬達驅動: uln2003 / mock
├── tools/
│   ├── motor_gamepad.py     # 用 USB 手把控制馬達
│   └── motor_keyboard.py    # 用鍵盤控制馬達
├── requirements.txt
└── install.sh               # Jetson 環境安裝
```

## 1. 硬體

三組 ULN2003 驅動板 + 28BYJ-48 步進馬達，分別控制水平 (pan)、垂直 (tilt) 與發射器 (trigger)。每片驅動板使用 Jetson 40-pin 的 4 支 GPIO (BOARD 編號，可在 `config.yaml` 修改)：

| 馬達 | IN1 | IN2 | IN3 | IN4 |
|---|---|---|---|---|
| pan (水平) | 7 | 11 | 13 | 15 |
| tilt (垂直) | 29 | 31 | 33 | 35 |
| trigger (發射器) | 37 | 16 | 18 | 22 |

發射器的 IN1 原本規劃用 pin 12，但在我們這片 Jetson 上 pin 12 沒有輸出，所以改用 pin 37。

電源：

- ULN2003 板的 `+` / `-` 請接**外部 5V 電源** (2A 以上)，不要使用 Jetson 的 5V 腳位。每顆 28BYJ-48 約耗 240 mA，電流突波可能讓 Jetson 重開機。
- **外部電源的 GND 要接到 Jetson 的 GND 腳位** (例如 pin 6)。沒有共地的話，GPIO 訊號無法傳到驅動板。
- ULN2003 的輸入可直接使用 Jetson 的 3.3V GPIO。

USB 手把是選配，用來手動控制馬達。我們用的是「Twin USB Joystick」PS2 轉接器 (USB ID `2563:0555`)。

## 2. 環境安裝 (Jetson)

把本 repo clone 到 ai-balloon 旁邊。`config.yaml` 預設從 `../ai-balloon/models/balloon.engine` 載入模型。

```text
~/Documents/workspace/ai-balloon/models/balloon.engine   # 在 Jetson 上用 ai-balloon/detection/export_engine.py 產生
~/Documents/workspace/balloon-shooter/
```

```bash
./install.sh
# 登出再登入一次 (加入 gpio 群組後才會生效)
source venv/bin/activate
```

馬達工具只需要 `Jetson.GPIO` 和 `pyyaml`。JetPack 內建的 `python3` 兩個都有，所以還沒執行 `install.sh` 也能使用。

### GPIO pinmux (JetPack 6)

JetPack 6 中，40-pin 排針大部分腳位的輸出預設是關閉的。這時 `Jetson.GPIO` 寫入腳位**不會有任何錯誤，但實際上沒有輸出**：ULN2003 的 LED 不會亮，馬達也不會動。預設為上拉的腳位 (29、31) 則相反，LED 會一直亮著。

查詢腳位狀態 (`tristate=1` 代表輸出被關閉)：

```bash
sudo grep -A14 "(soc_gpio32_pq5)" /sys/kernel/debug/pinctrl/2430000.pinmux/pinconf-groups | grep -E "tristate|pull="
```

腳位的 group 名稱可以用 `Jetson.GPIO` 對應的 GPIO 名稱查詢，例如 `sudo grep PQ.05 /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-pins`。

要開啟輸出，把腳位加進 40-pin overlay 並設定 `nvidia,tristate = <0x00>`，然後重開機：

- 用 `sudo /opt/nvidia/jetson-io/jetson-io.py` 啟用這些腳位上的功能，**或**
- 用 `dtc` 反編譯 `/boot/jetson-io-hdr40-user-custom.dtbo`，為每支腳加上 `hdr40-pinNN` 節點後重新編譯。修改前請先備份原檔。

之後再用 jetson-io 存檔，可能會整份重寫 overlay，把手動加入的腳位蓋掉。

## 3. 手把控制馬達

步進馬達沒有絕對位置：**啟動時的位置就是 home**，所以請先用手把雲台擺正，再執行：

```bash
python3 tools/motor_gamepad.py
```

| 按鍵 | 動作 |
|---|---|
| 十字鍵 / 左搖桿 | 水平 / 垂直，按住持續轉動 |
| `L1` (按住) | 慢速 (1/4 速)，用來微調瞄準 |
| `B` / `X` (按住) | 發射器馬達正轉 / 反轉，不限角度 |
| `A` | 發射一次 |
| `Y` | 水平 / 垂直回到 home |
| `SELECT` | 把目前位置設為 home |
| `R2` | 馬達斷電 (可用手轉動) |
| `START` | 離開 (會先回到 home) |

按鍵編號設定在 `config.yaml` 的 `gamepad` 區段。這組編號是在 Twin USB Joystick 轉接器的數位模式下實測的，這個模式下十字鍵和左搖桿都會送出軸 0/1。其他手把的編號可能不同；要查手把送出的編號，可以讀取 `/dev/input/js0` (參考 `shooter/gamepad.py`)。

## 4. 鍵盤測試馬達

沒有手把時可以用鍵盤。工具在終端機中執行，接在 Jetson 上的實體鍵盤或透過 SSH 都可以使用。

```bash
python3 tools/motor_keyboard.py
```

| 按鍵 | 動作 |
|---|---|
| `←` `→` / `a` `d` | 水平 左 / 右 |
| `↑` `↓` / `w` `s` | 垂直 上 / 下 |
| `[` `]` | 發射器馬達反轉 / 正轉 (微調位置) |
| `空白鍵` | 發射一次 |
| `1`–`5` | 每按一下轉幾度：1 / 2 / 5 / 10 / 30 |
| `h` | 水平 / 垂直回到 home |
| `z` | 把目前位置設為 home |
| `r` | 馬達斷電 (可用手轉動) |
| `q` / `Esc` | 離開 (會先回到 home) |

## 5. 校正

1. **接線**：執行 `python3 tools/motor_keyboard.py --step-delay 0.2` 後按鍵，該片 ULN2003 板上的 4 顆 LED 應該依序亮起。
   - 某顆 LED 都不亮：檢查那支腳的接線和 pinmux (見 [GPIO pinmux](#gpio-pinmux-jetpack-6))。要確認線和板子是否正常，可以把那條線的 Jetson 端改插到 pin 1 (3.3V)，LED 應該會亮。
   - 馬達原地抖動、不轉：通常是少了一相 (有一顆 LED 不亮)，或是兩條 IN 線接反了。
2. **方向**：若往右時水平卻往左轉，或往上時垂直卻往下轉，把該軸的 `invert` 改成 `true`。我們的垂直馬達需要 `invert: true`。
3. **範圍**：從 home 開始移動各軸，在機構卡住前停下，記下畫面顯示的角度，填入 `config.yaml` 的 `min` / `max`。加 `--no-limit` 可以超出目前的範圍限制。
   - `min: null` / `max: null` 表示不限制，該軸可以無限轉，目前垂直就是這樣設定。不限制的軸回 home 時走最短路徑，不會把轉過的圈數倒轉回去。請注意線材是否會被纏住。
4. **發射器**：按住 `B` / `X` 找出能完成一次發射的轉動角度，設為 `trigger.fire_degrees`。發射後需要轉回原位就用 `return: true`；若只會往同方向轉 (例如凸輪每次轉一圈)，就用 `return: false`。

`steps_per_rev: 4096` 是 28BYJ-48 半步模式的標稱步數，`step_delay: 0.002` 約為 44°/s。如果馬達抖動或掉步，把 `step_delay` 調大。也可以在各馬達的區段中個別設定 `step_delay`。

## 6. 執行

先用手把雲台擺正，再執行：

```bash
python main.py                         # MIPI 攝影機，開啟視窗，不發射
python main.py --source usb --headless # USB 攝影機，透過 SSH 執行
python main.py --arm                   # 允許發射
```

視窗中紅框是目前的目標，十字是準心。按鍵：`q` 離開、`a` 切換是否允許發射、`h` 回到 home。結束時雲台會回到 home，下次啟動時就是擺正的狀態。

不接馬達測試時，使用 `--driver mock` (也可以在 PC 上搭配影片檔、`balloon.pt` 和 `opencv-python` 執行)：

```bash
python main.py --driver mock --model ../ai-balloon/models/balloon.pt --source test.mp4
```

## 7. 調整參數

- **視角**：把 `camera.hfov` 設為攝影機的水平視角。如果雲台一直轉過頭或轉不夠，通常是這個值不對。
- **控制**：雲台來回震盪就調小 `aim.kp`，太慢就調大。
- **準心偏移**：發射器和鏡頭不在同一個位置。把氣球放在平常的射擊距離，觀察實際命中點，再用 `aim.offset_x` / `offset_y` (像素) 把準心移到命中點上。
- **發射條件**：水平與垂直誤差都小於 `fire.lock_tolerance` 度，且連續 `fire.lock_frames` 幀，才會發射。兩次發射至少間隔 `fire.cooldown` 秒。
