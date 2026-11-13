#include "esphome/components/improv_ble/improv_ble_component.h"
#include "single_fan.h"
#include "esphome/core/application.h"
#include "esphome/core/log.h"
#include "esphome/components/wifi/wifi_component.h"
#include "esphome/components/captive_portal/captive_portal.h"
#include <esp_ota_ops.h>
#include <esp_netif.h>
#include <nvs.h>
#include "esphome/core/helpers.h"
#include <cstring>
#include <memory>
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

namespace esphome::single_fan {
bool ha_english = false;
extern const unsigned char WEB_PAGE[];
extern const size_t WEB_PAGE_SIZE;
static constexpr uint32_t CONFIG_KEY = 0x53464E20;
// ESPHome load() returns false for both absent keys and unreadable records.
// Initialize defaults only when NVS explicitly confirms both keys are absent.
static bool config_storage_empty() {
  nvs_handle_t handle;
  const auto opened = nvs_open("esphome", NVS_READONLY, &handle);
  if (opened == ESP_ERR_NVS_NOT_FOUND)
    return true;
  if (opened != ESP_OK)
    return false;
  bool empty = true;
  for (unsigned i = 0; i < 2; i++) {
    const auto key = std::to_string(CONFIG_KEY + i);
    size_t size = 0;
    if (nvs_get_blob(handle, key.c_str(), nullptr, &size) != ESP_ERR_NVS_NOT_FOUND)
      empty = false;
  }
  nvs_close(handle);
  return empty;
}
static const char *calibration_label(const char *code, bool english) {
  struct Label {
    const char *code, *en, *zh;
  };
  static constexpr Label labels[] = {
      {"signal", "Checking speed signal", "检查转速信号"},
      {"rpm_table", "Measuring RPM table", "测量转速表"},
      {"verify", "Verifying minimum", "复核最低档"},
      {"saving", "Saving", "保存结果"},
      {"no_rpm", "No speed signal. Check the wiring.", "没有转速信号，请检查接线"},
      {"save_failed", "Save failed. Try again.", "保存失败，请重试"},
      {"calibration_timeout", "Calibration timed out. Try again.", "校准超时，请重试"},
      {"invalid_calibration", "Invalid result. Previous settings kept.", "校准结果无效，已保留原设置"},
  };
  for (const auto &label : labels)
    if (std::strcmp(code, label.code) == 0)
      return english ? label.en : label.zh;
  return english ? "Unknown calibration state" : "未知校准状态";
}
void ControlFan::control(const fan::FanCall &call) {
  if (call.get_state().has_value() && !*call.get_state()) {
    owner_->action(102);
    return;
  }
  if (call.get_speed().has_value())
    owner_->action(100, *call.get_speed());
  if (call.get_state().has_value())
    owner_->action(*call.get_state() ? 101 : 102);
}
void ControlButton::press_action() { owner_->action(action_); }
void ControlSelect::control(const std::string &v) {
  const auto &options = this->traits.get_options();
  auto option = std::find(options.begin(), options.end(), v);
  if (option != options.end())
    owner_->action(action_, std::distance(options.begin(), option));
}
void Controller::reset_timer(bool start) {
  if (start)
    set_timeout("ui_reset", fan_ui::RESET_HOLD_MS, [this] { ui_.reset_timeout(*this, center_button_->state); });
  else
    cancel_timeout("ui_reset");
}
void Controller::menu_timer() {
  set_timeout("ui_menu", fan_ui::MENU_TIMEOUT_MS, [this] { ui_.menu_timeout(*this); });
}
void Controller::log_press(fan_ui::Button b) {
  switch (b) {
    case fan_ui::Button::UP:
      ESP_LOGI("joystick", "up pressed");
      break;
    case fan_ui::Button::DOWN:
      ESP_LOGI("joystick", "down pressed");
      break;
    case fan_ui::Button::LEFT:
      ESP_LOGI("joystick", "left pressed");
      break;
    case fan_ui::Button::RIGHT:
      ESP_LOGI("joystick", "right pressed");
      break;
    default:
      break;
  }
}
void Controller::log_click() { ESP_LOGI("joystick", "center click"); }
void Controller::setup() {
  center_button_->add_on_state_callback([this](bool pressed) { ui_.center_state(*this, pressed, millis()); });
  up_button_->add_on_state_callback([this](bool pressed) {
    if (pressed)
      ui_press(fan_ui::Button::UP);
  });
  down_button_->add_on_state_callback([this](bool pressed) {
    if (pressed)
      ui_press(fan_ui::Button::DOWN);
  });
  left_button_->add_on_state_callback([this](bool pressed) {
    if (pressed)
      ui_press(fan_ui::Button::LEFT);
  });
  right_button_->add_on_state_callback([this](bool pressed) {
    if (pressed)
      ui_press(fan_ui::Button::RIGHT);
  });
  set_interval("ui_poll", fan_ui::POLL_MS, [this] {
    ui_poll(center_button_->state, up_button_->state, down_button_->state, left_button_->state, right_button_->state);
  });
  power_output_->turn_off();
  pwm_output_->set_level(0);
  Settings chosen;
  bool found = false;
  for (unsigned i = 0; i < 2; i++) {
    slots_[i] = global_preferences->make_preference<Record>(CONFIG_KEY + i, true);
    Record record{};
    if (!slots_[i].load(&record))
      continue;
    if (record.json[sizeof(record.json) - 1] != 0)
      continue;
    Settings candidate;
    if (json::parse_json(std::string(record.json), [&](JsonObject obj) { return read_config(obj, candidate, true); }) &&
        (!found || int32_t(record.seq - sequence_) > 0)) {
      chosen = candidate;
      sequence_ = record.seq;
      found = true;
    }
  }
  const bool initialize = !found && config_storage_empty();
  core.settings = chosen;
  core.config_fault = !found && !initialize;
  core.boot(millis());
  if (initialize)
    save();
  temperature_source_->add_on_state_callback([this](float v) { core.sample_temperature(v, millis()); });
  humidity_source_->add_on_state_callback([this](float v) { core.humidity = v; });
  rpm_source_->add_on_state_callback([this](float v) { core.sample_rpm(v / 2.0f, millis()); });
  translate();
  // The native portal must precede our root page, including when AP starts later.
  web_server_base_id_->add_handler_without_auth(captive_portal::global_captive_portal);
  web_server_base_id_->init();
  web_server_base_id_->add_handler(this);
  booted_ = true;
  publish();
}
void Controller::on_shutdown() {
  if (booted_ && core.dirty && !core.calibrating())
    save();
}
void Controller::loop() {
  uint32_t now = millis();
  if (uint32_t(now - last_tick_) >= 50) {
    last_tick_ = now;
    core.tick(now);
    if (core.calibration_pending_save) {
      core.calibration_save_result(save());
      core.dirty = false;
    }
    apply_output();
    if (core.factory_requested) {
      factory_reset();
      return;
    }
  }
  if (core.dirty && !save_at_)
    save_at_ = now ? now : 1;
  if (save_at_ && uint32_t(now - save_at_) >= 5000 && !core.calibrating()) {
    save();
    save_at_ = 0;
  }
  if (uint32_t(now - last_publish_) >= 1000) {
    publish();
    last_publish_ = now;
  }
}
void Controller::apply_output() {
  float pwm = std::clamp(core.output, 0.0f, 100.0f);
  if (pwm > 0) {
    zero_at_ = 0;
    if (!powered_) {
      power_output_->turn_on();
      powered_ = true;
    }
    pwm_output_->set_level(pwm / 100);
  } else {
    pwm_output_->set_level(0);
    if (powered_) {
      if (!zero_at_)
        zero_at_ = millis() ? millis() : 1;
      if (uint32_t(millis() - zero_at_) >= 300) {
        power_output_->turn_off();
        powered_ = false;
        zero_at_ = 0;
      }
    }
  }
}
void Controller::action(unsigned id, float value) {
  bool ok = true;
  switch (id) {
    case 1:
      ok = core.automatic(value != 0);
      break;
    case 11:
      ok = core.start_calibration(millis());
      break;
    case 12:
      core.cancel();
      break;
    case 14:
      if (core.calibrating()) {
        ok = false;
        break;
      }
      core.settings.power = Power(unsigned(value));
      core.dirty = true;
      break;
    case 100:
      ok = core.manual(value, Unit::PWM);
      break;
    case 101:
      ok = core.enable(true);
      break;
    case 102:
      ok = core.enable(false);
      break;
    default:
      ok = false;
  }
  if (core.dirty)
    save_at_ = millis() ? millis() : 1;
  last_error_ = ok ? "" : "command_rejected";
  core.tick(millis());
  apply_output();
  publish();
}
void Controller::translate() {
  ha_english = core.settings.english;
  // API clients derive identity from entity names: keep the configured names stable.
  control_mode_->traits.set_options(core.settings.english
                                        ? std::initializer_list<const char *>{"Manual Speed", "Automatic Temperature"}
                                        : std::initializer_list<const char *>{"手动风速", "自动温控"});
  power_->traits.set_options(
      core.settings.english ? std::initializer_list<const char *>{"Restore Previous", "Off", "Automatic Temperature"}
                            : std::initializer_list<const char *>{"恢复上次状态", "保持关闭", "自动温控"});
}
void Controller::publish() {
  unsigned faults = core.temp_fault | (core.rpm_fault << 1) | (core.save_fault << 2) | (core.config_fault << 3);
  if (faults != last_faults_) {
    if (faults)
      ESP_LOGW("single_fan", "Faults: temperature=%d rpm=%d save=%d config=%d", core.temp_fault, core.rpm_fault,
               core.save_fault, core.config_fault);
    else
      ESP_LOGI("single_fan", "Faults cleared");
    last_faults_ = faults;
  }
  if (core.phase != last_phase_) {
    if (core.phase == ControllerCore::Phase::FAILED)
      ESP_LOGW("single_fan", "Calibration failed: %s stage=%s output=%.0f%% retry=%u RPM=[%.0f,%.0f,%.0f]",
               core.cal_error, core.cal_failed_stage, core.cal_failed_output, core.cal_retry(), core.cal_readings()[0],
               core.cal_readings()[1], core.cal_readings()[2]);
    else if (core.calibrating())
      ESP_LOGI("single_fan", "Calibration stage: %s", core.cal_stage());
    else if (core.phase == ControllerCore::Phase::IDLE)
      ESP_LOGI("single_fan", "Calibration ended");
    last_phase_ = core.phase;
  }
  fan_->state = core.settings.enabled;
  fan_->speed =
      core.settings.enabled ? int(std::round(core.display_percent())) : int(std::max(1.0f, core.settings.last_pwm));
  fan_->publish_state();
  control_mode_->publish_state(control_mode_->traits.get_options()[core.settings.automatic ? 1 : 0]);
  temperature_->publish_state(core.temperature);
  humidity_->publish_state(core.humidity);
  rpm_->publish_state(core.rpm);
  target_rpm_->publish_state(core.settings.cal.valid ? core.target_rpm : NAN);
  pwm_->publish_state(core.output);
  progress_->publish_state(core.progress);
  const bool en = core.settings.english;
  fault_->publish_state(core.config_fault ? (en ? "Configuration invalid" : "配置错误")
                        : core.save_fault ? (en ? "Save failed" : "保存失败")
                        : core.temp_fault ? (en ? "Temperature sensor lost" : "温度失联")
                        : core.rpm_fault  ? (en ? "RPM feedback lost" : "转速异常")
                                          : (en ? "Normal" : "正常"));
  calibration_->publish_state(core.calibrating()                            ? calibration_label(core.cal_stage(), en)
                              : core.phase == ControllerCore::Phase::FAILED ? calibration_label(core.cal_error, en)
                              : core.settings.cal.valid                     ? (en ? "Calibrated" : "已校准")
                                                                            : (en ? "Not calibrated" : "未校准"));
  power_->publish_state(power_->traits.get_options()[static_cast<unsigned>(core.settings.power)]);
  firmware_version_->publish_state(ESPHOME_PROJECT_VERSION);
}
void Controller::config_json(JsonObject o, const Settings &s) {
  o["name"] = s.device_name.data();
  o["enabled"] = s.enabled;
  o["automatic"] = s.automatic;
  o["english"] = s.english;
  o["prompt_seen"] = s.prompt_seen;
  o["resume_once"] = s.resume_once;
  o["manual_unit"] = unsigned(s.manual_unit);
  o["custom_unit"] = unsigned(s.custom_unit);
  o["curve_unit"] = unsigned(s.curve_unit);
  o["power"] = unsigned(s.power);
  o["manual"] = s.manual;
  o["custom"] = s.custom;
  o["last_pwm"] = s.last_pwm;
  o["last_rpm"] = s.last_rpm;
  o["pulses"] = s.pulses;
  auto points = o["points"].to<JsonArray>();
  for (unsigned i = 0; i < s.count; i++) {
    auto p = points.add<JsonArray>();
    p.add(s.points[i].temp);
    p.add(s.points[i].value);
  }
  auto c = o["cal"].to<JsonObject>();
  c["valid"] = s.cal.valid;
  c["minimum"] = s.cal.minimum;
  c["minimum_measured"] = s.cal.minimum_measured;
  c["maximum"] = s.cal.maximum;
  c["minimum_rpm"] = s.cal.minimum_rpm;
  c["auto_raised"] = s.cal.auto_raised;
  auto table = c["rpm"].to<JsonArray>();
  for (float r : s.cal.rpm)
    table.add(r);
  c["rpm_step"] = s.cal.rpm_step;
  auto dense = c["rpm_dense"].to<JsonArray>();
  for (unsigned i = 0; i < 51; i++)
    dense.add(s.cal.rpm_dense[i]);
}
bool Controller::read_config(JsonObject o, Settings &s, bool full) {
  if (full) {
    const char *required[] = {"enabled", "automatic", "english",  "prompt_seen", "manual_unit", "curve_unit", "power",
                              "manual",  "last_pwm",  "last_rpm", "pulses",      "points",      "cal"};
    for (auto key : required)
      if (o[key].isNull())
        return false;
  }
  auto integer = [&](const char *key, unsigned max, unsigned &result) {
    if (!o[key].is<unsigned>() || o[key].as<unsigned>() > max)
      return false;
    result = o[key].as<unsigned>();
    return true;
  };
  for (auto pair : {std::pair<const char *, bool *>{"enabled", &s.enabled},
                    {"automatic", &s.automatic},
                    {"english", &s.english},
                    {"prompt_seen", &s.prompt_seen},
                    {"resume_once", &s.resume_once}}) {
    if (!o[pair.first].isNull()) {
      if (!o[pair.first].is<bool>())
        return false;
      *pair.second = o[pair.first].as<bool>();
    }
  }
  if (!o["name"].isNull()) {
    if (!o["name"].is<const char *>())
      return false;
    const std::string name = o["name"].as<std::string>();
    if (!::fan_core::valid_device_name(name))
      return false;
    s.device_name.fill(0);
    std::copy(name.begin(), name.end(), s.device_name.begin());
  }
  unsigned v;
  if (!o["manual_unit"].isNull()) {
    if (!integer("manual_unit", 1, v))
      return false;
    s.manual_unit = Unit(v);
  }
  if (!o["custom_unit"].isNull()) {
    if (!integer("custom_unit", 1, v))
      return false;
    s.custom_unit = Unit(v);
  }
  if (!o["curve_unit"].isNull()) {
    if (!integer("curve_unit", 1, v))
      return false;
    s.curve_unit = Unit(v);
  }
  if (!o["power"].isNull()) {
    if (!integer("power", 2, v))
      return false;
    s.power = Power(v);
  }
  if (!o["pulses"].isNull()) {
    if (!integer("pulses", 2, v) || v != 2)
      return false;
    s.pulses = v;
  }
  for (auto pair : {std::pair<const char *, float *>{"manual", &s.manual},
                    {"custom", &s.custom},
                    {"last_pwm", &s.last_pwm},
                    {"last_rpm", &s.last_rpm}})
    if (!o[pair.first].isNull()) {
      if (!o[pair.first].is<float>())
        return false;
      *pair.second = o[pair.first].as<float>();
    }
  if (!o["points"].isNull()) {
    if (!o["points"].is<JsonArray>())
      return false;
    auto points = o["points"].as<JsonArray>();
    if (points.size() < 2 || points.size() > 10)
      return false;
    s.count = points.size();
    unsigned i = 0;
    for (JsonVariant p : points) {
      if (!p.is<JsonArray>() || p.size() != 2 || !p[0].is<float>() || !p[1].is<float>())
        return false;
      s.points[i++] = {p[0].as<float>(), p[1].as<float>()};
    }
  }
  if (!o["cal"].isNull()) {
    auto c = o["cal"].as<JsonObject>();
    if (c.isNull() || !c["minimum"].is<float>())
      return false;
    s.cal.minimum = c["minimum"].as<float>();
    s.cal.minimum_measured = 0;
    s.cal.minimum_rpm = 0;
    s.cal.auto_raised = 0;
    s.cal.rpm_dense.fill(0);
    s.cal.rpm_step = 2;
    if (!c["rpm_step"].isNull()) {
      if (!c["rpm_step"].is<unsigned>() || c["rpm_step"].as<unsigned>() != 2)
        return false;
      s.cal.rpm_step = c["rpm_step"].as<unsigned>();
    }
    if (!c["rpm_dense"].isNull()) {
      if (!c["rpm_dense"].is<JsonArray>() || c["rpm_dense"].size() != 100 / s.cal.rpm_step + 1)
        return false;
      for (unsigned i = 0; i <= 100 / s.cal.rpm_step; i++) {
        if (!c["rpm_dense"][i].is<float>())
          return false;
        s.cal.rpm_dense[i] = c["rpm_dense"][i].as<float>();
      }
    }
    for (auto pair : {std::pair<const char *, float *>{"maximum", &s.cal.maximum},
                      {"minimum_measured", &s.cal.minimum_measured},
                      {"minimum_rpm", &s.cal.minimum_rpm},
                      {"auto_raised", &s.cal.auto_raised}}) {
      if (!c[pair.first].isNull()) {
        if (!c[pair.first].is<float>())
          return false;
        *pair.second = c[pair.first].as<float>();
      }
    }
    {
      if (!c["valid"].is<bool>() || !c["rpm"].is<JsonArray>() || c["rpm"].size() != 11)
        return false;
      s.cal.valid = c["valid"].as<bool>();
      unsigned i = 0;
      for (JsonVariant r : c["rpm"].as<JsonArray>()) {
        if (!r.is<float>())
          return false;
        s.cal.rpm[i++] = r.as<float>();
      }
    }
  }
  return ::fan_core::valid_settings(s);
}
bool Controller::save() {
  if (!::fan_core::valid_settings(core.settings)) {
    core.save_fault = true;
    return false;
  }
  auto record = std::make_unique<Record>();
  auto &rec = *record;
  rec.seq = sequence_ + 1;
  std::string data = json::build_json([&](JsonObject o) { config_json(o, core.settings); });
  if (data.size() >= sizeof(rec.json)) {
    core.save_fault = true;
    return false;
  }
  std::memcpy(rec.json, data.c_str(), data.size() + 1);
  unsigned slot = rec.seq % 2;
  bool queued = slots_[slot].save(&rec);
  const bool flushed = global_preferences->sync();
  auto verify = std::make_unique<Record>();
  bool ok = queued && flushed && slots_[slot].load(verify.get()) && verify->seq == rec.seq &&
            std::memcmp(verify.get(), &rec, sizeof(rec)) == 0;
  core.save_fault = !ok;
  if (ok) {
    sequence_ = rec.seq;
    core.dirty = false;
    core.config_fault = false;
  }
  return ok;
}
std::string Controller::status() {
  return json::build_json([&](JsonObject o) {
    config_json(o["config"].to<JsonObject>(), core.settings);
    o["name"] = core.settings.device_name.data();
    o["name_editable"] = true;
    o["reset_pending"] = reset_pending_;
    o["hostname"] = App.get_name() + ".local";
    o["project"] = "local.single_fan";
    o["hardware"] = "esp32dev";
    o["protocol"] = 1;
    o["ble_state"] = static_cast<unsigned>(improv_ble::global_improv_component->get_improv_state());
    if (std::isfinite(core.temperature))
      o["temperature"] = core.temperature;
    else
      o["temperature"] = nullptr;
    if (std::isfinite(core.humidity))
      o["humidity"] = core.humidity;
    else
      o["humidity"] = nullptr;
    if (std::isfinite(core.rpm))
      o["rpm"] = core.rpm;
    else
      o["rpm"] = nullptr;
    o["output"] = core.output;
    o["target"] = core.target;
    o["target_rpm"] = core.target_rpm;
    o["calibrating"] = core.calibrating();
    o["progress"] = core.progress;
    o["cal_error"] = core.cal_error;
    o["cal_stage"] = core.cal_stage();
    o["cal_wait"] = core.cal_wait_seconds(millis());
    o["cal_retry"] = core.cal_retry();
    o["cal_failed_stage"] = core.cal_failed_stage;
    o["cal_failed_output"] = core.cal_failed_output;
    auto readings = o["cal_readings"].to<JsonArray>();
    for (float r : core.cal_readings()) {
      if (std::isfinite(r))
        readings.add(r);
      else
        readings.add(nullptr);
    }
    o["temp_fault"] = core.temp_fault;
    o["rpm_fault"] = core.rpm_fault;
    o["save_fault"] = core.save_fault;
    o["config_fault"] = core.config_fault;
    o["error"] = last_error_;
    o["version"] = ESPHOME_PROJECT_VERSION;
    o["uptime"] = millis() / 1000;
    o["free_heap"] = esp_get_free_heap_size();
    auto *w = wifi::global_wifi_component;
    const bool connected = w->is_connected();
    o["wifi"] = connected;
    o["ap_active"] = w->is_ap_active();
    char ip[network::IP_ADDRESS_BUFFER_SIZE], ssid[wifi::SSID_BUFFER_SIZE], mac[MAC_ADDRESS_PRETTY_BUFFER_SIZE];
    o["ip"] = connected           ? w->get_ip_addresses()[0].str_to(ip)
              : w->is_ap_active() ? w->wifi_soft_ap_ip().str_to(ip)
                                  : "";
    o["ssid"] = w->wifi_ssid_to(ssid);
    o["mac"] = get_mac_address_pretty_into_buffer(mac);
    if (connected)
      o["rssi"] = w->wifi_rssi();
    else
      o["rssi"] = nullptr;
    esp_netif_ip_info_t info{};
    auto *netif = esp_netif_get_handle_from_ifkey(connected ? "WIFI_STA_DEF" : "WIFI_AP_DEF");
    if (netif && esp_netif_get_ip_info(netif, &info) == ESP_OK) {
      char gateway[16];
      esp_ip4addr_ntoa(&info.gw, gateway, sizeof(gateway));
      o["gateway"] = gateway;
    } else
      o["gateway"] = nullptr;
  });
}
bool Controller::command(JsonObject o) {
  if (reset_pending_)
    return false;
  if (!o["op"].is<const char *>())
    return false;
  std::string op = o["op"].as<const char *>();

  if (op == "provision_cancel") {
    auto *pairing = improv_ble::global_improv_component;
    // Do not abort credentials already accepted, or disable offline recovery.
    if (wifi::global_wifi_component->is_connected() && pairing->get_improv_state() == improv::STATE_AUTHORIZED)
      pairing->cancel_pairing();
    return true;
  }
  if (op == "provision") {
    if (core.calibrating())
      return false;
    improv_ble::global_improv_component->start();
    return true;
  }
  if (op == "enable") {
    if (!o["value"].is<bool>())
      return false;
    return core.enable(o["value"].as<bool>());
  }
  if (op == "cancel") {
    core.cancel();
    return true;
  }
  if (op == "calibrate")
    return core.start_calibration(millis(), o["auto_after"].as<bool>());
  if (core.calibrating())
    return false;
  if (op == "auto") {
    if (!o["value"].is<bool>())
      return false;
    return core.automatic(o["value"].as<bool>());
  }
  if (op == "manual") {
    if (!o["value"].is<float>() || !o["unit"].is<unsigned>() || o["unit"].as<unsigned>() > 1)
      return false;
    return core.manual(o["value"].as<float>(), Unit(o["unit"].as<unsigned>()));
  }
  if (op == "custom") {
    if (!o["value"].is<float>() || !o["unit"].is<unsigned>() || o["unit"].as<unsigned>() > 1)
      return false;
    Settings before = core.settings;
    bool was_dirty = core.dirty;
    if (!core.custom(o["value"].as<float>(), Unit(o["unit"].as<unsigned>())))
      return false;
    if (!save()) {
      core.settings = before;
      core.dirty = was_dirty;
      return false;
    }
    return true;
  }
  if (op == "factory_reset") {
    char mac[MAC_ADDRESS_PRETTY_BUFFER_SIZE];
    if (!o["confirm"].is<const char *>() || o["confirm"].as<std::string>() != get_mac_address_pretty_into_buffer(mac))
      return false;
    reset_pending_ = true;
    // Reply before erasing Wi-Fi credentials; use the same reset as the physical menu.
    set_timeout("factory_reset", 1500, [this] { factory_reset(); });
    return true;
  }
  if (op == "rename") {
    if (!o["name"].is<const char *>())
      return false;
    const std::string name = o["name"].as<std::string>();
    if (!::fan_core::valid_device_name(name))
      return false;
    const auto before = core.settings.device_name;
    core.settings.device_name.fill(0);
    std::copy(name.begin(), name.end(), core.settings.device_name.begin());
    if (!save()) {
      core.settings.device_name = before;
      return false;
    }
    return true;
  }
  if (op == "prompt") {
    core.settings.prompt_seen = true;
    core.dirty = true;
    return save();
  }
  if (op == "config") {
    auto obj = o["config"].as<JsonObject>();
    if (obj.isNull())
      return false;
    // Configuration writes cannot bypass command semantics or manufacture calibration results.
    for (JsonPair pair : obj) {
      std::string key = pair.key().c_str();
      if (key != "points" && key != "curve_unit" && key != "power" && key != "english")
        return false;
    }
    Settings before = core.settings, candidate = before;
    if (!read_config(obj, candidate, false))
      return false;
    if (before.english != candidate.english)
      candidate.resume_once = true;
    core.settings = candidate;
    core.dirty = true;
    if (!save()) {
      core.settings = before;
      core.dirty = false;
      return false;
    }
    if (before.english != candidate.english) {
      // Restart refreshes native API static entity info. Hashes are fixed by codegen.
      set_timeout("language", 1000, [] { App.safe_reboot(); });
    }
    return true;
  }
  return false;
}
bool Controller::canHandle(AsyncWebServerRequest *r) const {
  char url_buf[AsyncWebServerRequest::URL_BUF_SIZE];
  const auto url = r->url_to(url_buf);
  return (url == "/" && r->method() == HTTP_GET) || url == "/control";
}
void Controller::handleRequest(AsyncWebServerRequest *r) {
  char url_buf[AsyncWebServerRequest::URL_BUF_SIZE];
  if (r->url_to(url_buf) == "/") {
    auto *response = r->beginResponse(200, "text/html; charset=utf-8", WEB_PAGE, WEB_PAGE_SIZE);
    response->addHeader("Content-Encoding", "gzip");
    response->addHeader("Cache-Control", "no-store");
    r->send(response);
    return;
  }
  if (r->method() != HTTP_GET && r->method() != HTTP_POST) {
    r->send(405);
    return;
  }
  const bool post = r->method() == HTTP_POST;
  std::string payload;
  if (post) {
    if (!r->hasHeader("X-Fan-Request")) {
      r->send(403);
      return;
    }
    auto *p = r->getParam("data");
    if (!p || p->value().size() > 2048) {
      r->send(400);
      return;
    }
    payload = p->value();
  }
  // HTTP runs in another FreeRTOS task. All commands and snapshots execute on the ESPHome loop.
  struct Job {
    SemaphoreHandle_t ready{xSemaphoreCreateBinary()};
    std::atomic<bool> expired{false};
    bool ok{true};
    std::string result;
    ~Job() {
      if (ready)
        vSemaphoreDelete(ready);
    }
  };
  auto job = std::make_shared<Job>();
  if (!job->ready) {
    r->send(503);
    return;
  }
  this->defer([this, job, payload, post] {
    if (job->expired)
      return;
    if (post) {
      job->ok = json::parse_json(payload, [&](JsonObject o) { return command(o); });
      if (core.dirty)
        save_at_ = millis() ? millis() : 1;
      last_error_ = job->ok ? "" : "invalid_or_busy";
      core.tick(millis());
      apply_output();
      publish();
    }
    job->result = status();
    xSemaphoreGive(job->ready);
  });
  if (xSemaphoreTake(job->ready, pdMS_TO_TICKS(5000)) != pdTRUE) {
    job->expired = true;
    r->send(503);
    return;
  }
  auto *response = r->beginResponse(job->ok ? 200 : 400, "application/json", job->result);
  response->addHeader("Cache-Control", "no-store");
  r->send(response);
}
void Controller::factory_reset() {
  core.factory_requested = false;
  core.enable(false);
  pwm_output_->set_level(0);
  power_output_->turn_off();
  powered_ = false;
  esp_ota_mark_app_valid_cancel_rollback();
  // ESPHome preferences and saved Wi-Fi credentials share NVS. No home SSID is compiled in.
  if (!global_preferences->reset()) {
    reset_pending_ = false;
    last_error_ = "factory_reset_failed";
    core.save_fault = true;
    return;
  }
  core.dirty = false;
  booted_ = false;
  App.safe_reboot();
}
void Controller::draw(unsigned page) {
  auto &d = *screen_;
  auto *f = font_;
  d.clear();
  if (core.calibrating()) {
    d.print(42, 8, f, "校准中");
    return;
  }
  if (page == 5) {
    d.print(20, 0, f, "已识别长按");
    d.print(20, 16, f, "请松开中键");
    return;
  }
  if (page == 4) {
    d.print(0, 0, f, "单击中键确认恢复");
    d.print(20, 16, f, "其他键取消");
    return;
  }
  if (page == 0) {
    if (core.temp_fault || core.rpm_fault || core.save_fault || core.config_fault)
      d.print(7, 0, f,
              core.temp_fault   ? "温度失联"
              : core.rpm_fault  ? "转速异常"
              : core.save_fault ? "保存失败"
                                : "配置错误");
    else {
      if (std::isfinite(core.temperature))
        d.printf(7, 0, f, "温%.0f°C", core.temperature);
      else
        d.print(7, 0, f, "温--°C");
      if (std::isfinite(core.humidity))
        d.printf(56, 0, f, "湿%.0f%%", core.humidity);
      else
        d.print(56, 0, f, "湿--%");
    }
    d.print(101, 0, f, core.settings.automatic ? "自动" : "手动");
    const int cx = 15, cy = 24;
    d.circle(cx, cy, 7);
    const int phase = core.settings.enabled ? (millis() / 200) % 3 : 0;
    for (int i = 0; i < 3; i++) {
      float a = (phase * 40 + i * 120) * 3.14159f / 180;
      int x = cx + std::lround(4 * std::cos(a)), y = cy + std::lround(4 * std::sin(a));
      d.filled_circle(x, y, 2);
      d.line(cx, cy, x, y);
      d.line(cx + std::lround(2 * std::cos(a + 0.5f)), cy + std::lround(2 * std::sin(a + 0.5f)), x, y);
    }
    d.filled_circle(cx, cy, 1);
    if (std::isfinite(core.rpm))
      d.printf(25, 14, f, "%.0f转", core.rpm);
    else
      d.print(25, 14, f, "--转");
    float percent = core.display_percent();
    if (core.settings.enabled)
      d.printf(121, 14, f, display::TextAlign::TOP_RIGHT, "%.0f%%", percent);
    else
      d.print(83, 14, f, "已关");
    d.rectangle(70, 28, 51, 4);
    d.filled_rectangle(71, 29, 49 * percent / 100, 2);
  } else if (page == 1) {
    if (core.settings.automatic) {
      d.print(8, 0, f, "控制模式");
      d.print(99, 0, f, "自动");
      d.print(20, 16, f, "请到网页配置温控");
    } else {
      d.print(42, 0, f, "控制模式");
      d.print(53, 16, f, "手动");
    }
  } else if (page == 2) {
    auto *w = wifi::global_wifi_component;
    char ip[network::IP_ADDRESS_BUFFER_SIZE];
    auto state = improv_ble::global_improv_component->get_improv_state();
    d.print(12, 0, f,
            state == improv::STATE_PROVISIONING ? "正在连接网络"
            : state == improv::STATE_AUTHORIZED ? "蓝牙配网已开启"
                                                : "单击开启蓝牙配网");
    if (w->is_connected())
      d.print(7, 16, f, w->get_ip_addresses()[0].str_to(ip));
    else if (w->is_ap_active())
      d.print(7, 16, f, w->wifi_soft_ap_ip().str_to(ip));
    else
      d.print(53, 16, f, "--");
  } else if (page == 3) {
    d.print(42, 0, f, "恢复出厂");
    d.print(8, 16, f, "长按中键后松开");
  }
  for (int i = 0; i < 5; i++) {
    d.line(i, 16 - i, i, 16 + i);
    d.line(127 - i, 16 - i, 127 - i, 16 + i);
  }
}
}  // namespace esphome::single_fan
