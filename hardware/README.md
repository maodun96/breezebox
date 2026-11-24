# 微风盒（BreezeBox）硬件说明

完整嘉立创 EDA 专业版原理图、PCB 与 BOM 已发布至嘉立创开源硬件平台：

👉 **[嘉立创开源硬件 · 微风盒 BreezeBox](https://oshwhub.com/maodun96/project_mkhircso)**

DIY 复刻成本约 **30 元**（含打板、元器件与外壳）。

---

## 核心硬件规格

| 项目 | 规格 |
| --- | --- |
| **主控模组** | `ESP32-WROOM-32E-N4`（4 MB Flash，2.4 GHz Wi-Fi + BLE） |
| **供电输入** | 12V DC，DC5521 母座（兼容 DC5525 插头），严禁高于 12V |
| **3.3V 降压** | `SY8120B1ABC`（12V → 3.3V） |
| **风扇高边开关** | `TPS22810DRVR`（12V 供电通断，0% 真断电停转，额定负载 ≤ 2A） |
| **风扇接口** | `KF2510-3+1P` 弯插防呆针座，25 kHz PWM 调速 + 2 脉冲/转测速 |
| **本地交互** | 0.91 寸 OLED（SSD1306 128×32，I²C）+ 贴片五向摇杆 |
| **环境传感** | 板载温湿度传感器（I²C），另支持固件直连外置蓝牙传感器（某米的温湿度传感器 2） |
| **烧录接口** | 板边 TTL 焊盘 `R / T / G / 3V3` |

---

## GPIO 引脚定义

以 [`firmware/config.yaml`](../firmware/config.yaml) 为准：

| 功能 | GPIO | 说明 |
| --- | --- | --- |
| 风扇 PWM | `GPIO16` | 25 kHz |
| 风扇供电控制 | `GPIO21` | 控制 `TPS22810DRVR` 使能 |
| 风扇测速 | `GPIO32` | 每转 2 脉冲 |
| I²C SDA / SCL | `GPIO13` / `GPIO14` | 挂载 OLED（`0x3C`）与板载温湿度传感器（`0x44`） |
| OLED RST | `GPIO17` | 屏幕复位 |
| 五向摇杆 · 中键 | `GPIO0` | 低电平有效，同时兼作上电下载模式（BOOT）按键 |
| 五向摇杆 · 上 / 下 / 左 / 右 | `GPIO22` / `GPIO25` / `GPIO26` / `GPIO27` | 内部上拉，低电平有效 |

---

## BOM 外另购件

以下两项器件未包含在立创贴片 BOM 中，需单独采购后手工焊接（尺寸与外壳开孔匹配）：

- **0.91 寸 OLED 屏幕（I²C 4 针）**：[1688 参考链接](https://detail.1688.com/offer/977991550530.html)
- **7×7×6 贴片五向摇杆按键**：[1688 参考链接](https://detail.1688.com/offer/826441588591.html)

---

## 首次固件烧录

1. 从 [GitHub Releases](https://github.com/maodun96/breezebox/releases) 下载 `single-fan-x.y.z.factory.bin`。
2. 3.3V USB-TTL 下载器连接板边焊盘：`R → TXD`、`T → RXD`、`G → GND`、`3V3 → 3.3V`。
3. **按住五向摇杆中键（`GPIO0`）不放，再通电**，进入下载模式后松开。
4. 将 `factory.bin` 烧录至地址 **`0x0`**，断电重启即可。
