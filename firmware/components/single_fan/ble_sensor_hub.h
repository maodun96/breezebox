#pragma once
#include "ble_sensor_driver.h"
#include "esphome/components/ble_client/ble_client.h"
#include "esphome/components/json/json_util.h"

namespace esphome::single_fan {
class Controller;
class BleSensorHub : public ble_client::BLEClientNode {
 public:
  explicit BleSensorHub(Controller *owner) : owner_(owner) {}
  void boot(uint32_t now) { next_ = now + 15000; source_since_ = now; }
  void update(uint32_t now);
  void advertisement(const esp32_ble_tracker::ESPBTDevice &device);
  void gattc_event_handler(esp_gattc_cb_event_t event, esp_gatt_if_t, esp_ble_gattc_cb_param_t *p) override;
  void pause(const char *reason);
  bool allow_calibration();
  bool command(const std::string &op, JsonObject o);
  void status(JsonObject o);
  static bool parse_config(JsonObject o, fan_core::ExtSensorConfig &out);
  bool ota{};
 private:
  struct Result { fan_core::ExtSensorConfig config; int rssi; };
  Controller *owner_;
  std::vector<Result> results_;
  fan_core::ExtSensorConfig target_{};
  fan_core::BleSample sample_{};
  bool scanning_{}, binding_{}, polling_{}, started_{}, reading_{}, cached_{}, has_sample_{};
  uint32_t scan_at_{}, attempt_{}, read_at_{}, next_{}, sample_at_{}, source_since_{}, scan_id_{};
  uint16_t handle_{};
  int failures_{}, rssi_{-128};
  const char *error_{""}, *scan_end_reason_{""};
  void stop_scan(const char *reason);
  void finish(const char *error);
  void read();
  void read_failed(const char *error = "unsupported");
  void accept(const fan_core::BleSample &sample);
};
}
