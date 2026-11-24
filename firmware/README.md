# 微风盒（BreezeBox）固件源码

当前版本：**`1.4.0`** · 许可证：**GPLv3**

本目录包含微风盒 12V PWM 风扇控制器的完整 ESPHome / ESP-IDF 固件源码、内置离线网页与自动化测试脚本。

## 目录结构

- `config.yaml`：ESPHome 硬件引脚与组件配置（目标板 `esp32dev`，4 MB Flash，对应主控 `ESP32-WROOM-32E-N4`）
- `partitions.csv`：双 OTA 分区表（支持升级失败自动回滚）
- `components/single_fan/`：核心控制逻辑、风扇校准、自动温控曲线、OLED/五向摇杆 UI、HTTP `/control` 接口与外置蓝牙温湿度传感器驱动（支持**某米的温湿度传感器 2**）
- `components/{wifi,esp32_ble_server,improv_ble,captive_portal}/`：源自 ESPHome 的网络与 Improv 蓝牙配网组件（补丁见 `components/IMPROV-PATCHES.md`）
- `web/`：内置离线控制网页（`index.html`）与热点配网页面（`captive.html`）
- `fonts/`：OLED 显示字体 Noto Sans SC（SIL OFL 1.1，见 `fonts/OFL.txt`）
- `tests/`：C++ 核心单测、网页控制/曲线测试、外置传感器测试与配置校验
- `build.py`：一键检查、编译与打包脚本

## 编译与检查

需要 Python 3.11+、`clang++`（C++17）和 Node.js，固定使用 ESPHome 2026.10.1 与 ESP-IDF。首次构建需要联网拉取依赖。

```sh
cd firmware
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python build.py check    # 运行本地单测与静态检查
.venv/bin/python build.py build    # 编译并生成 dist/ 产物
```

编译产物输出至 `firmware/dist/`：

| 文件 | 用途 |
| --- | --- |
| `single-fan-1.4.0.factory.bin` | 首次串口烧录完整镜像（含 Bootloader / 分区表 / 固件），**切勿用于网页 OTA** |
| `single-fan-1.4.0.ota.bin` | 无线升级镜像，用于设备网页「关于设备」手动上传或 App 内置升级 |
| `single-fan-1.4.0-source.tar.gz` | 对应版本源码归档 |
| `manifest.json` | 产物字节数、SHA-256 与 ESPHome 版本信息 |

## 串口首次烧录

1. 用 3.3V USB-TTL 模块接主板边缘焊盘：`R / T / G / 3V3`（`RXD / TXD / GND / 3.3V`，`TX/RX` 交叉连接）。
2. **按住五向摇杆中键（`GPIO0`）不放，再上电**进入下载模式，随后松开按键。
3. 将 `single-fan-1.4.0.factory.bin` 烧录至地址 **`0x0`**：

```sh
esptool.py --chip esp32 --baud 460800 write_flash -z 0x0 single-fan-1.4.0.factory.bin
```

4. 断电重新上电即可运行。

## OTA 升级

- **App 升级**：iOS / Android App 已内置对应版本 `.ota.bin`，在「设置 → 固件更新」中一键局域网升级。
- **网页升级**：打开设备网页「关于设备」，上传 `.ota.bin` 文件即可。
