#include "single_fan.h"
#include "esphome/core/log.h"
#include "esp_system.h"

namespace esphome::single_fan {
using namespace fan_core;
namespace bt = esp32_ble_tracker;
static const char *const TAG = "ble_sensor";
template<size_t N> static bool copy_field(JsonVariant value, std::array<char,N> &dest) {
  if (!value.is<const char *>()) return false;
  auto str = value.as<JsonString>();
  if (str.size() >= N || strlen(str.c_str()) != str.size()) return false;
  dest.fill(0);
  std::copy_n(str.c_str(),str.size(),dest.begin());
  return true;
}
bool BleSensorHub::parse_config(JsonObject o, ExtSensorConfig &out) {
  out.bound = true;
  return copy_field(o["driver"], out.driver) && copy_field(o["mac"], out.mac) &&
         copy_field(o["name"], out.name) && valid_ext(out);
}
void BleSensorHub::advertisement(const bt::ESPBTDevice &device) {
  if (!scanning_) return;
  auto name = device.get_name().str();
  for (const auto &d : drivers) {
    bool match = d.match_adv(name, 0, nullptr, 0);
    for (const auto &sd : device.get_service_datas()) {
      auto uuid = sd.uuid.get_uuid();
      if (uuid.len == ESP_UUID_LEN_16)
        match |= d.match_adv(name, uuid.uuid.uuid16, sd.data.data(), sd.data.size());
    }
    if (!match) continue;
    Result r{};
    r.config.bound = true;
    device.address_str_to(r.config.mac.data());
    snprintf(r.config.driver.data(), r.config.driver.size(), "%s", d.id);
    snprintf(r.config.name.data(), r.config.name.size(), "%s", name.empty() ? d.model_en : name.c_str());
    r.rssi = device.get_rssi();
    auto it = std::find_if(results_.begin(), results_.end(), [&](auto &entry) { return entry.config.mac == r.config.mac; });
    if (it == results_.end()) results_.push_back(r);
    else *it = r;
    std::sort(results_.begin(), results_.end(), [](auto &a, auto &b) { return a.rssi > b.rssi; });
    if (results_.size() > 12) results_.resize(12);
    break;
  }
}
void BleSensorHub::stop_scan(const char *reason) {
  if (scanning_) {
    bt::global_esp32_ble_tracker->stop_scan();
    scan_end_reason_ = reason;
  }
  scanning_ = false;
}
void BleSensorHub::finish(const char *error) {
  if (binding_) error_ = error;
  if (started_) parent()->disconnect();
  binding_ = polling_ = started_ = reading_ = false;
}
void BleSensorHub::pause(const char *reason) {
  stop_scan("stopped");
  finish(reason);
}
bool BleSensorHub::allow_calibration() {
  if (binding_) return false;
  error_ = "";
  pause("");
  return true;
}
bool BleSensorHub::command(const std::string &op, JsonObject o) {
  auto &core = owner_->core;
  auto &s = core.settings;
  uint32_t now = millis();
  if (ota || core.calibrating()) return false;
  if (op == "ext_scan_stop") { stop_scan("stopped"); return true; }
  if (binding_) return false;
  error_ = "";
  if (op == "ext_scan_start" || op == "ext_bind") {
    if (owner_->provisioning_busy()) { error_ = "ble_busy"; return false; }
    if (op == "ext_scan_start") {
      if (scanning_) bt::global_esp32_ble_tracker->stop_scan();
      finish("");
      results_.clear();
      scan_id_++;
      scan_end_reason_ = "";
      scan_at_ = now;
      scanning_ = true;
      return true;
    }
    ExtSensorConfig cfg{};
    if (!parse_config(o,cfg)) return false;
    pause("");
    binding_ = true;
    attempt_ = now;
    target_ = cfg;
    return true;
  }
  if (op != "ext_source" && op != "ext_unbind") return false;
  bool unbind = op == "ext_unbind";
  if (!unbind && (!o["source"].is<unsigned>() || o["source"].as<unsigned>() > 1)) return false;
  bool external = !unbind && o["source"].as<unsigned>() == 1;
  if (external && !s.ext_sensor.bound) return false;
  if (!unbind && external == core.external()) return true;
  auto before = s;
  s.sensor_source = external ? SensorSource::EXTERNAL : SensorSource::INTERNAL;
  if (unbind) { s.ext_sensor = {}; s.ext_handle = 0; }
  if (!owner_->save()) { s = before; error_ = "save_failed"; return false; }
  pause("");
  core.reset_temperature(now);
  source_since_ = next_ = now;
  if (unbind) { has_sample_ = false; failures_ = 0; rssi_ = -128; }
  if (external && has_sample_ && now - sample_at_ <= 180000) core.sample_external(sample_, now);
  return true;
}
void BleSensorHub::update(uint32_t now) {
  auto &core = owner_->core;
  if (ota || owner_->provisioning_busy() || core.calibrating()) { pause("ble_busy"); return; }
  if (scanning_) {
    if (now - scan_at_ >= 10000) stop_scan("completed");
    else if (parent()->state() == bt::ClientState::IDLE) bt::global_esp32_ble_tracker->start_scan_if_idle();
    return;
  }
  if (!binding_ && core.external() && int32_t(now-next_) >= 0) {
    next_ = now + 30000;
    if (!polling_) { target_ = core.settings.ext_sensor; attempt_ = now; polling_ = true; }
  }
  if (!binding_ && !polling_) return;
  if (now - attempt_ >= (binding_ ? 15000U : 12000U)) { if (reading_) read_failed("timeout"); else finish("timeout"); return; }
  if (started_ || parent()->state() != bt::ClientState::IDLE || bt::global_esp32_ble_tracker->scan_running()) return;
  handle_ = binding_ ? 0 : core.settings.ext_handle;
  cached_ = handle_ != 0;
  uint64_t addr = 0;
  for (char c : target_.mac) if (c && c != ':') addr = (addr << 4) | (c <= '9' ? c-'0' : c-'A'+10);
  parent()->set_address(addr);
  parent()->set_remote_addr_type(BLE_ADDR_TYPE_PUBLIC);
  parent()->set_connection_type(cached_ ? bt::ConnectionType::V3_WITH_CACHE : bt::ConnectionType::V1);
  started_ = true;
  parent()->connect();
}
void BleSensorHub::read() {
  reading_ = true;
  read_at_ = millis();
  if (esp_ble_gattc_read_char(parent()->get_gattc_if(), parent()->get_conn_id(), handle_, ESP_GATT_AUTH_REQ_NONE) != ESP_OK)
    read_failed();
}
void BleSensorHub::read_failed(const char *error) {
  if (cached_ && ++failures_ >= 2) {
    owner_->core.settings.ext_handle = 0;
    owner_->core.dirty = true;
    esp_ble_gattc_cache_clean(parent()->get_remote_bda());
    failures_ = 0;
  }
  finish(error);
}
void BleSensorHub::accept(const BleSample &sample) {
  auto &core = owner_->core;
  auto &s = core.settings;
  uint32_t now = millis();
  bool paired = binding_;
  finish("");
  if (paired) {
    auto before = s;
    s.ext_sensor = target_;
    s.sensor_source = SensorSource::EXTERNAL;
    s.ext_handle = handle_;
    if (!owner_->save()) { s = before; error_ = "save_failed"; return; }
    core.reset_temperature(now);
    rssi_ = -128;
    for (auto &r : results_) if (r.config.mac == target_.mac) rssi_ = r.rssi;
    next_ = now + 30000;
  } else if (handle_ != s.ext_handle) { s.ext_handle = handle_; core.dirty = true; }
  has_sample_ = true;
  failures_ = 0;
  sample_ = sample;
  source_since_ = sample_at_ = now;
  core.sample_external(sample, now);
  ESP_LOGI(TAG, "%s handle=%04x cached=%d read=%ums total=%ums T=%.2f H=%.0f mv=%u heap=%u",
    target_.mac.data(), handle_, cached_, unsigned(now-read_at_), unsigned(now-attempt_),
    sample.temperature, sample.humidity, sample.mv, unsigned(esp_get_free_heap_size()));
}
void BleSensorHub::gattc_event_handler(esp_gattc_cb_event_t ev, esp_gatt_if_t, esp_ble_gattc_cb_param_t *p) {
  if (!started_) return;
  if (ev == ESP_GATTC_OPEN_EVT) {
    if (p->open.status != ESP_GATT_OK) finish("connect_failed");
    else if (cached_) read();
  } else if (ev == ESP_GATTC_SEARCH_CMPL_EVT && !cached_) {
    auto *d = driver_for(target_.driver.data());
    auto *c = parent()->get_characteristic(bt::ESPBTUUID::from_raw(d->service_uuid), bt::ESPBTUUID::from_raw(d->char_uuid));
    if (!c) { finish("unsupported"); return; }
    handle_ = c->handle;
    read();
  } else if (ev == ESP_GATTC_READ_CHAR_EVT && reading_ && p->read.handle == handle_) {
    BleSample sample;
    if (p->read.status == ESP_GATT_OK && driver_for(target_.driver.data())->parse_payload(p->read.value,p->read.value_len,sample))
      accept(sample);
    else read_failed();
  } else if (ev == ESP_GATTC_DISCONNECT_EVT || ev == ESP_GATTC_CLOSE_EVT) {
    if (reading_) read_failed("connect_failed"); else finish("connect_failed");
  }
}
void BleSensorHub::status(JsonObject o) {
  uint32_t now = millis();
  auto &core = owner_->core;
  o["supported"] = true;
  o["scanning"] = scanning_;
  o["scan_remaining"] = scanning_ ? (10000 - std::min<uint32_t>(10000,now-scan_at_) + 999)/1000 : 0;
  o["scan_id"] = scan_id_;
  o["scan_end_reason"] = scan_end_reason_;
  auto list = o["scan_results"].to<JsonArray>();
  for (auto &r : results_) {
    auto item = list.add<JsonObject>();
    auto *d = driver_for(r.config.driver.data());
    item["driver"] = d->id; item["model_zh"] = d->model_zh; item["model_en"] = d->model_en;
    item["mac"] = r.config.mac.data(); item["name"] = r.config.name.data(); item["rssi"] = r.rssi;
  }
  o["binding"] = binding_; o["bind_error"] = error_;
  bool fresh_session = int32_t(sample_at_ - source_since_) >= 0;
  o["state"] = !core.settings.ext_sensor.bound ? "unbound" :
    core.external() && (core.temp_fault || now-source_since_ > 180000) ? "lost" :
    !has_sample_ || (!fresh_session && now-sample_at_ > 180000) ? "connecting" :
    now-sample_at_ > 180000 ? "lost" : now-sample_at_ > 60000 ? "stale" : "ok";
  o["battery_mv"] = nullptr; o["battery_pct"] = nullptr; o["age_s"] = nullptr; o["rssi"] = nullptr;
  if (has_sample_) {
    o["battery_mv"] = sample_.mv;
    o["battery_pct"] = std::clamp((int(sample_.mv)-2200)*100/900,0,100);
    o["age_s"] = (now-sample_at_)/1000;
    if (rssi_ != -128) o["rssi"] = rssi_;
  }
}
}
