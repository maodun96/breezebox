# 微风盒 BreezeBox 固件

[English](#english) · 中文

微风盒是一款给 4 针 PWM 机箱风扇用的小型控制器，基于 ESP32 和 ESPHome。它用温度自动调速，也能手动调速，可以在手机、网页和 Home Assistant 里控制。

这个仓库是控制器的固件源码，对应手机 App「微风盒」内置的固件，当前版本 **1.3.1**。

## 配套 App

微风盒 iPhone App（iOS 17 及以上）是使用这台控制器的主要方式，目前准备上架 App Store。App 不在这个仓库里。

- **蓝牙配网**：自动发现待配网的控制器，把 Wi-Fi 信息发给它。
- **局域网控制**：自动发现同一网络里的控制器，开关、手动和自动、调速、温度曲线、风扇校准都能在 App 里做。
- **多台设备**：每台按硬件 MAC 识别，改名、移除互不影响。
- **固件升级**：App 内置本仓库对应版本的固件，选择升级后通过局域网上传。
- **快捷指令**：可在 iOS 快捷指令里开关风扇、切换模式、设定风速。
- 不需要账号，不使用云服务，控制只在局域网内进行。

不装 App 也能用：设备自带网页，也能接入 Home Assistant。

## 功能

- **手动和自动**：手动设置风速，或按温度曲线自动调速。关闭风扇时，温控不会把它打开。
- **温度曲线**：2 到 10 个点，温度 0 到 50 ℃，风速随温度只升不降。
- **风扇校准**：自动测出风扇的最低稳转点、启动点和转速表，之后可以按转速（RPM）设定。
- **网页控制**：设备自带网页，无需联网，适配手机和电脑，有深色模式。
- **OLED 和按键**：128×32 小屏显示状态，五个按键可开关、调速、切换模式和恢复出厂。
- **Home Assistant**：通过 ESPHome 原生接口接入，提供风扇、控制模式、温湿度、转速和校准等实体。
- **蓝牙配网**：用 App 通过蓝牙（Improv 协议）把设备接入 Wi-Fi；没有 App 时，设备也会开热点，用网页配网。
- **保护**：温湿度传感器失联时，自动模式下风扇满速并报警；断网不影响本地控制。
- **升级**：支持网页和 App 上传固件，升级失败会自动回滚。

## 硬件

主控 ESP32（`esp32dev`，4 MB Flash）。引脚如下，以 `config.yaml` 为准。

| 用途 | 引脚 | 说明 |
| --- | --- | --- |
| 风扇 PWM | GPIO16 | 25 kHz |
| 风扇供电开关 | GPIO21 | |
| 风扇测速 | GPIO32 | 每转 2 个脉冲 |
| 温湿度传感器 SHT3x | GPIO13 (SDA)、GPIO14 (SCL) | I²C 地址 0x44 |
| OLED SSD1306 128×32 | GPIO13 (SDA)、GPIO14 (SCL)、GPIO17 (RST) | I²C 地址 0x3C |
| 中键 | GPIO0 | 低电平触发 |
| 上键 | GPIO22 | 低电平触发 |
| 下键 | GPIO25 | 低电平触发 |
| 左键 | GPIO26 | 低电平触发 |
| 右键 | GPIO27 | 低电平触发 |

## 首次使用

通电后有两种方式把控制器接入 Wi-Fi。

**用 App（推荐）**

1. 给控制器通电。
2. 打开 App，点“添加风扇”，选择待配网的设备，选择 Wi-Fi 并输入密码。
3. 配网完成后，App 会自动发现并添加这台风扇。

**不用 App**

1. 给控制器通电，手机连接设备热点 `breezebox-` 加 MAC 后六位，打开 `192.168.4.1`，选择 Wi-Fi 配网。热点没有密码。
2. 联网后，在局域网内用浏览器打开 `breezebox-xxxxxx.local`，或在 Home Assistant 里添加。

OLED 上左右键翻页：主页、控制模式、网络信息、恢复出厂。恢复出厂需要在恢复页长按中键，松开后再短按一次确认。

## 构建

需要 Python 3.11 以上、`clang++`（支持 C++17）和 Node.js。固定使用 ESPHome 2026.10.1 和 ESP-IDF。下载依赖需要联网。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python build.py check    # 运行本地检查
.venv/bin/python build.py build    # 编译并打包
```

产物在 `dist/`：

| 文件 | 用途 |
| --- | --- |
| `single-fan-1.3.1.ota.bin` | 升级用，网页或 App 上传 |
| `single-fan-1.3.1.factory.bin` | 首次通过串口刷写的完整镜像，不用于网页升级 |
| `single-fan-1.3.1-source.tar.gz` | 对应源码 |
| `manifest.json` | 文件大小、SHA-256、ESPHome 版本 |

构建时间会写进二进制，同一份源码在不同时间编出的文件，校验值可能不同。

目录说明：`components/` 是本项目的 ESPHome 组件，`web/` 是设备网页，`tests/` 是本地检查，`fonts/` 是 OLED 字体。

## 安全说明

这是有意的设计：设备面向家庭局域网，网页、固件升级和 Home Assistant 接口不设密码，也不加密，这样 App 配对不需要输入密码。请只在可信的网络里使用，并只给自己的设备配网。

## 许可

本项目以 GPLv3 发布，全文见 [LICENSE](LICENSE)。

- `components/` 里的 `wifi`、`esp32_ble_server`、`improv_ble`、`captive_portal` 源自 ESPHome，改动说明见 [components/IMPROV-PATCHES.md](components/IMPROV-PATCHES.md)，ESPHome 的许可见 [components/ESPHOME-LICENSE](components/ESPHOME-LICENSE)。
- 字体 Noto Sans SC 使用 SIL OFL 1.1，见 [fonts/OFL.txt](fonts/OFL.txt)。
- 配套的 iPhone App 不在这个仓库里。

[TEST_REPORT.md](TEST_REPORT.md) 是开发期间的测试记录，保留作参考，其中的早期版本号不代表当前版本。

---

## English

BreezeBox is a small controller for 4-pin PWM PC case fans, built on an ESP32 and ESPHome. It sets fan speed from temperature or by hand, and you can control it from a phone, a web page or Home Assistant.

This repository is the controller's firmware source. It matches the firmware bundled in the BreezeBox iPhone app. Current version: **1.3.1**.

### Companion app

The BreezeBox iPhone app (iOS 17 or later) is the main way to use this controller. It is being prepared for the App Store and is not in this repository.

- **Bluetooth setup.** Finds a controller that needs Wi-Fi and sends the network details to it.
- **Local control.** Finds controllers on the same network. Power, manual and automatic mode, speed, temperature curve and calibration are all in the app.
- **Several devices.** Each one is identified by its hardware MAC, so renaming or removing one does not affect another.
- **Firmware update.** The app bundles the firmware that matches this repository and uploads it over the local network.
- **Shortcuts.** Turn the fan on or off, change mode or set speed from iOS Shortcuts.
- No account and no cloud service. Control stays on your local network.

You can also use the controller without the app, through its built-in web page or Home Assistant.

### Features

- **Manual and automatic modes.** Automatic mode follows a temperature curve and never turns on a fan that you switched off.
- **Temperature curve.** 2 to 10 points, 0 to 50 °C. Speed can only stay the same or rise as temperature rises.
- **Fan calibration.** Measures the lowest stable speed, the start point and an RPM table, so you can also set speed in RPM.
- **Built-in web page.** Works without internet, on phone and desktop, with dark mode.
- **OLED and buttons.** A 128×32 display and five buttons for power, speed, mode and factory reset.
- **Home Assistant.** Native ESPHome API with fan, mode, temperature, humidity, RPM and calibration entities.
- **Bluetooth setup.** The app sends Wi-Fi details over Bluetooth (Improv). Without the app, the device opens a hotspot and a web setup page.
- **Protection.** If the temperature sensor stops reporting, an automatic-mode fan runs at full speed and raises an alert. Losing the network does not stop local control.
- **Updates.** Upload firmware from the web page or the app. A failed update rolls back.

### Hardware

ESP32 (`esp32dev`, 4 MB flash). See the pin table above or `config.yaml`.

### First use

There are two ways to put the controller on Wi-Fi after you power it.

**With the app (recommended):** open the app, tap Add Fan, pick the controller, choose your Wi-Fi and enter the password. The app then finds and adds the fan.

**Without the app:** join the hotspot `breezebox-` plus the last six digits of the MAC, open `192.168.4.1` and pick a network. The hotspot has no password. After it joins Wi-Fi, open `breezebox-xxxxxx.local` in a browser or add it in Home Assistant.

### Build

Needs Python 3.11 or newer, `clang++` with C++17 and Node.js. ESPHome 2026.10.1 with ESP-IDF is pinned. Network access is needed to download dependencies.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python build.py check
.venv/bin/python build.py build
```

Outputs are in `dist/`: the OTA image, the factory image for the first serial flash, the source archive and a manifest with SHA-256 values. The build time is embedded in the binary, so two builds of the same source can differ.

### Security

By design, the web page, firmware update and Home Assistant API have no password and no encryption, so the app can pair without one. Use it only on a network you trust.

### License

GPLv3, see [LICENSE](LICENSE). Parts of `components/` come from ESPHome (see `components/ESPHOME-LICENSE`). The font is Noto Sans SC under SIL OFL 1.1. The iPhone app is not in this repository.
