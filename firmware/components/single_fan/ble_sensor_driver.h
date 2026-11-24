#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <string_view>

namespace fan_core {
enum class SensorSource : uint8_t { INTERNAL, EXTERNAL };
struct ExtSensorConfig {
  bool bound{};
  std::array<char, 24> driver{};
  std::array<char, 18> mac{};
  std::array<char, 32> name{};
};
struct BleSample { float temperature{}, humidity{}; uint16_t mv{}; };
enum class BleMode { POLL_GATT, PASSIVE_ADV };
struct BleSensorDriver {
  const char *id, *model_zh, *model_en;
  BleMode mode;
  bool (*match_adv)(std::string_view name, uint16_t uuid, const uint8_t *data, size_t size);
  const char *service_uuid, *char_uuid;
  bool (*parse_payload)(const uint8_t *, size_t, BleSample &);
};
inline constexpr BleSensorDriver drivers[] = {{
  "lywsd03mmc", "米家温湿度计 2", "Mi Sensor 2", BleMode::POLL_GATT,
  [](std::string_view name, uint16_t uuid, const uint8_t *data, size_t size) {
    return name == "LYWSD03MMC" || (uuid == 0xFE95 && size >= 4 && data[2] == 0x5b && data[3] == 0x05);
  }, "ebe0ccb0-7a0a-4b0c-8a1a-6ff2997da3a6", "ebe0ccc1-7a0a-4b0c-8a1a-6ff2997da3a6",
  [](const uint8_t *b, size_t size, BleSample &out) {
    if (size != 5) return false;
    out = {int16_t(b[0] | (b[1] << 8)) / 100.f, float(b[2]), uint16_t(b[3] | (b[4] << 8))};
    return out.temperature >= -40 && out.temperature <= 85 && out.humidity <= 100;
  }
}};
inline const BleSensorDriver *driver_for(std::string_view id) {
  for (const auto &d : drivers) if (d.id == id) return &d;
  return nullptr;
}
inline bool valid_ext(const ExtSensorConfig &s) {
  if (!s.bound) return true;
  if (s.mac.back() || s.driver.back() || s.name.back() || !driver_for(s.driver.data())) return false;
  for (size_t i = 0; i < 17; ++i) {
    char c = s.mac[i];
    if (i % 3 == 2 ? c != ':' : !((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F'))) return false;
  }
  return true;
}
}
