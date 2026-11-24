# 微风盒（BreezeBox）12V PWM 风扇控制器

[English](#english) · 中文

基于 `ESP32-WROOM-32E-N4` 的本地 12V PWM 风扇控制器，支持多点自动温控曲线、自动风扇校准、外置蓝牙温湿度传感器直连、机身 0.91 寸 OLED + 五向摇杆、内置离线网页、Home Assistant 原生接入以及 iOS / Android 配套 App。无需云端，无需账号，DIY 复刻成本约 **30 元**。

当前发布固件版本：**`v1.4.0`**

---

## 快捷入口

| 资源 | 说明 | 地址 |
| --- | --- | --- |
| **固件与安卓 App 下载** | `factory.bin` / `ota.bin` / Android APK | [GitHub Releases](https://github.com/maodun96/breezebox/releases) |
| **iOS App** | 免费提供，iOS 17.0 及以上 | [App Store · 微风盒](https://apps.apple.com/cn/app/id6834356846) |
| **PCB 硬件开源** | 嘉立创 EDA 专业版原理图、PCB、BOM | [嘉立创开源硬件 · 微风盒 BreezeBox](https://oshwhub.com/maodun96/project_mkhircso) |
| **3D 打印外壳模型** | PLA 免支撑 3MF，CC BY-NC 4.0 | [拓竹 MakerWorld](https://makerworld.com.cn/zh/models/3330566-wei-feng-he-breezebox-12v-si-zhen-pwm-feng-shan-ko#profileId-3938861) ｜ [创想云](https://www.crealitycloud.cn/model-detail/6b05be3bb2a2575a3c5e61fc?profileId=6b05be3bb2a2575a3c5e6202) |
| **在线使用说明书** | 图文接线、配网、温控曲线与 FAQ | [飞书在线说明书](https://my.feishu.cn/docx/ZOi6dRNPao81GGx7LmCcXoj1nYg) |
| **成品购买（免焊接）** | 已焊好并装好外壳，到手插电即用 | [拼多多 · 微风盒成品](https://mobile.yangkeduo.com/goods.html?goods_id=1032587630292) |

---

## 仓库目录与许可

| 目录 | 内容 | 许可证 |
| --- | --- | --- |
| [`firmware/`](firmware/) | ESPHome / ESP-IDF 控制器固件源码、内置离线网页与构建测试脚本 | [GPLv3](LICENSE) |
| [`enclosure/`](enclosure/) | 3D 打印外壳 3MF 模型（通用版 & Bambu A1 PLA 切片配置） | CC BY-NC 4.0 |
| [`hardware/`](hardware/) | 硬件参数、GPIO 定义、BOM 外采购件与串口烧录说明 | 开源硬件（详见 [OSHWHub](https://oshwhub.com/maodun96/project_mkhircso)） |

- 配套 iOS / Android App 为免费闭源分发，不在此仓库内。
- 字体 `Noto Sans SC` 遵循 SIL OFL 1.1，详见 [`firmware/fonts/OFL.txt`](firmware/fonts/OFL.txt)。
- `firmware/components/` 中源自 ESPHome 的组件遵循其原许可，详见 [`firmware/components/ESPHOME-LICENSE`](firmware/components/ESPHOME-LICENSE)。

---

## 核心特性

- **12V 断电真停转 + 25 kHz PWM 调速**：高边负载开关 `TPS22810DRVR` 彻底切断风扇 12V 供电实现 0% 零待机停转，额定输出 2A。
- **自动风扇校准**：自动测量最低稳转点、起转点与转速对照表，校准后支持 1%～100% 稳定低速运行及按 RPM 精确调速。
- **2～10 点温控曲线**：0～50℃ 整数温度节点，曲线存于主板 NVS，断网脱机照常运行。
- **外置蓝牙温湿度传感器直连**：支持直接通过 BLE 轮询**某米的温湿度传感器 2**，无需第三方传感器固件或网关；3 分钟无有效读数时自动模式触发 100% 满速保护。
- **四端本地控制**：iOS / Android App、内置离线 Web UI、Home Assistant 原生 ESPHome API（6053 端口，免密钥自动发现）、机身 0.91 寸 OLED 与五向摇杆。
- **双配网方式**：Improv BLE 蓝牙配网 + 机身无密码 Wi-Fi 热点配网（`192.168.4.1`）。

---

## 硬件与首次烧录

- **主控**：`ESP32-WROOM-32E-N4`（4 MB Flash）
- **供电**：12V 直流，DC5521 母座（兼容 DC5525 插头），严禁接入超过 12V 的电源
- **风扇接口**：标准 12V PWM 风扇接口（KF2510-3+1P），最大负载电流 2A
- **首次串口烧录**：
  1. 从 [Releases](https://github.com/maodun96/breezebox/releases) 下载对应版本的 `single-fan-x.y.z.factory.bin`（不要用 `.ota.bin` 做首次串口烧录）。
  2. 使用 3.3V USB-TTL 下载器连接板边烧录焊盘 `R / T / G / 3V3`（分别对应 `RXD / TXD / GND / 3.3V`，注意 `TX/RX` 交叉连接）。
  3. **按住五向摇杆中键（`GPIO0`）不松手，再给板子上电**，进入下载模式后松开按键。
  4. 使用 `esptool` 或乐鑫烧录工具将 `factory.bin` 烧录至地址 **`0x0`**，断电重启即可。

完整硬件参数、GPIO 映射与 BOM 外物料见 [`hardware/README.md`](hardware/README.md)；固件编译与 OTA 说明见 [`firmware/README.md`](firmware/README.md)。

---

## 安全说明

设备面向家庭可信局域网，内置网页、OTA 接口与 Home Assistant API 均不设密码且不启用加密，以便局域网免密直连。请仅在可信的家庭局域网中使用。

---

## English

**BreezeBox** is a local 12V PWM fan controller built around `ESP32-WROOM-32E-N4` and ESPHome. It supports multi-point automatic temperature curves, automatic fan calibration, target RPM control, direct BLE polling for external `LYWSD03MMC` temperature/humidity sensors, an onboard 0.91" OLED with a 5-way joystick, a built-in offline web UI, native Home Assistant integration, and companion iOS / Android apps. No cloud or account required.

Latest firmware release: **`v1.4.0`**

### Quick Links

| Resource | Description | Link |
| --- | --- | --- |
| **Firmware & Android APK** | Prebuilt `factory.bin`, `ota.bin`, and Android APK | [GitHub Releases](https://github.com/maodun96/breezebox/releases) |
| **iOS App** | Free companion app (iOS 17.0+) | [App Store](https://apps.apple.com/cn/app/id6834356846) |
| **PCB & Schematics** | EasyEDA Pro schematics, PCB layout, and BOM | [OSHWHub](https://oshwhub.com/maodun96/project_mkhircso) |
| **3D Printable Enclosure** | Support-free PLA `.3mf` models (CC BY-NC 4.0) | [MakerWorld](https://makerworld.com.cn/zh/models/3330566-wei-feng-he-breezebox-12v-si-zhen-pwm-feng-shan-ko#profileId-3938861) \| [Creality Cloud](https://www.crealitycloud.cn/model-detail/6b05be3bb2a2575a3c5e61fc?profileId=6b05be3bb2a2575a3c5e6202) |
| **User Manual (CN)** | Wiring, Wi-Fi setup, curves, and FAQ | [Feishu Doc](https://my.feishu.cn/docx/ZOi6dRNPao81GGx7LmCcXoj1nYg) |

### Repository Layout & Licenses

| Directory | Contents | License |
| --- | --- | --- |
| [`firmware/`](firmware/) | ESPHome / ESP-IDF firmware source, built-in offline web UI, tests, and build script | [GPLv3](LICENSE) |
| [`enclosure/`](enclosure/) | Support-free PLA `.3mf` enclosure files | CC BY-NC 4.0 |
| [`hardware/`](hardware/) | Hardware specifications, GPIO pinout, BOM-external parts, and flashing guide | Open Hardware ([OSHWHub](https://oshwhub.com/maodun96/project_mkhircso)) |

- The companion iOS / Android apps are distributed free of charge (closed source) and are not part of this repository.
- `Noto Sans SC` font is licensed under SIL OFL 1.1 ([`firmware/fonts/OFL.txt`](firmware/fonts/OFL.txt)).
- ESPHome-derived components under `firmware/components/` retain their upstream license ([`firmware/components/ESPHOME-LICENSE`](firmware/components/ESPHOME-LICENSE)).

### Key Features

- **True 12V Power Cutoff + 25 kHz PWM**: High-side load switch (`TPS22810DRVR`) cuts 12V power completely at 0% speed; rated up to 2A.
- **Automatic Fan Calibration**: Measures minimum stable duty cycle, startup kick, and RPM lookup table for reliable 1%–100% control and target RPM mode.
- **2–10 Point Temperature Curve**: Integer 0–50 °C points stored in NVS; continues operating offline without Wi-Fi.
- **Direct External BLE Sensor Support**: Polls `LYWSD03MMC` Bluetooth temperature/humidity sensors directly over BLE (no custom sensor firmware or gateway required); falls back to 100% fail-safe speed in Auto mode if no reading arrives for 3 minutes.
- **Local Multi-Client Control**: iOS / Android apps, built-in offline Web UI, native Home Assistant ESPHome API (port 6053, auto-discovered without an encryption key), and onboard 0.91" OLED + 5-way joystick.
- **Dual Wi-Fi Provisioning**: Improv BLE via app, or open fallback AP (`192.168.4.1`).

### Hardware & First-Time Flashing

- **MCU**: `ESP32-WROOM-32E-N4` (4 MB Flash)
- **Power Input**: 12V DC via DC5521 barrel jack (compatible with DC5525 plugs); do not exceed 12V
- **Fan Header**: Standard 12V PWM fan header (`KF2510-3+1P`), max 2A total load
- **Initial Serial Flash**:
  1. Download `single-fan-x.y.z.factory.bin` from [Releases](https://github.com/maodun96/breezebox/releases) (do not use `.ota.bin` for initial serial flashing).
  2. Connect a 3.3V USB-TTL adapter to the board-edge pads `R / T / G / 3V3` (`RXD / TXD / GND / 3.3V`, cross-connecting TX/RX).
  3. **Hold the 5-way joystick center button (`GPIO0`) while applying power** to enter bootloader download mode, then release.
  4. Flash `factory.bin` to address **`0x0`** with `esptool`, then power-cycle.

### Security Note

By design, the built-in web UI, OTA endpoint, and Home Assistant API have no authentication or encryption so local discovery and control work without passwords. Use only on a trusted local network.
