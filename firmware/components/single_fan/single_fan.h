#pragma once
#include "core.h"
#include "ble_sensor_hub.h"
#include "ui.h"
#include "esphome/components/ssd1306_base/ssd1306_base.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/improv_ble/improv_ble_component.h"
#include "esphome/core/component.h"
#include "esphome/core/preferences.h"
#include "esphome/components/fan/fan.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/button/button.h"
#include "esphome/components/select/select.h"
#include "esphome/components/output/float_output.h"
#include "esphome/components/output/binary_output.h"
#include "esphome/components/display/display.h"
#include "esphome/components/font/font.h"
#include "esphome/components/web_server_base/web_server_base.h"
#include "esphome/components/json/json_util.h"

namespace esphome::single_fan {
using ::fan_core::Unit;
using ::fan_core::Power;
using ::fan_core::Settings;
using ::fan_core::ControllerCore;
class Controller;
template<class T> class Named : public T {
 public:
  void bind(Controller *owner, unsigned action) {
    owner_ = owner;
    action_ = action;
  }

 protected:
  Controller *owner_{};
  unsigned action_{};
};
class ControlFan : public Named<fan::Fan> {
 public:
  fan::FanTraits get_traits() override { return fan::FanTraits(false, true, false, 100); }

 protected:
  void control(const fan::FanCall &call) override;
};
class LocalSensor : public sensor::Sensor {};
class LocalText : public text_sensor::TextSensor {};
class ControlButton : public Named<button::Button> {
 protected:
  void press_action() override;
};
class ControlSelect : public Named<select::Select> {
 protected:
  void control(const std::string &value) override;
};
class Controller : public Component, public AsyncWebHandler {
 public:
  ControllerCore core;
  BleSensorHub hub{this};
  void set_sensor_client(ble_client::BLEClient *client) { client->register_ble_node(&hub); }
  void ota_active(bool active) { hub.ota = active; if (active) hub.pause("connect_failed"); }
  bool provisioning_busy() const;
  friend class BleSensorHub;
  void setup() override;
  void loop() override;
  void on_shutdown() override;
  float get_setup_priority() const override { return setup_priority::WIFI - 0.5f; }
  bool canHandle(AsyncWebServerRequest *request) const override;
  void handleRequest(AsyncWebServerRequest *request) override;
  void action(unsigned id, float value = 0);
  void draw(unsigned page);
  void ui_press(fan_ui::Button b) { ui_.press(*this, b, millis()); }
  void ui_click() { ui_.click(*this, millis()); }
  void ui_release() { ui_.release(*this, millis()); }
  void ui_poll(bool center, bool up, bool down, bool left, bool right) {
    ui_.poll(*this, millis(), center, up, down, left, right);
  }
  fan_ui::Page page() const { return page_; }
  void draw_current() { draw(static_cast<unsigned>(page_)); }
  void show(fan_ui::Page page) { page_ = page; }
  void screen_power(bool on) {
    if (on)
      screen_->turn_on();
    else
      screen_->turn_off();
  }
  void update() { screen_->update(); }
  void reset_timer(bool start);
  void menu_timer();
  void log_press(fan_ui::Button button);
  void log_click();
  bool calibrating() const { return core.calibrating(); }
  bool automatic() const { return core.settings.automatic; }
  bool fan_on() const { return fan_->state; }
  int speed() const { return int(core.display_percent()); }
  void toggle_mode() { action(1, !core.settings.automatic); }
  void toggle_fan() {
    auto call = fan_->toggle();
    call.perform();
  }
  void set_speed(int speed) {
    auto call = fan_->turn_on();
    call.set_speed(speed);
    call.perform();
  }
  void fan_off() {
    auto call = fan_->turn_off();
    call.perform();
  }
  void authorize() { hub.pause("ble_busy"); provisioning_->authorize(); }
  void request_reset() { core.factory_requested = true; }
#define FC_SET(name, type) \
  void set_##name(type *p) { name##_ = p; } \
  type *name##_{};
  FC_SET(pwm_output, output::FloatOutput)
 FC_SET(power_output, output::BinaryOutput)
 FC_SET(temperature_source, sensor::Sensor) FC_SET(humidity_source, sensor::Sensor) FC_SET(rpm_source, sensor::Sensor)
     FC_SET(screen, ssd1306_base::SSD1306) FC_SET(font, font::Font)
         FC_SET(web_server_base_id, web_server_base::WebServerBase) FC_SET(center_button, binary_sensor::BinarySensor)
             FC_SET(up_button, binary_sensor::BinarySensor) FC_SET(down_button, binary_sensor::BinarySensor)
                 FC_SET(left_button, binary_sensor::BinarySensor) FC_SET(right_button, binary_sensor::BinarySensor)
                     FC_SET(provisioning, improv_ble::ImprovBLEComponent) FC_SET(fan, ControlFan)
                         FC_SET(control_mode, ControlSelect) FC_SET(temperature, LocalSensor)
                             FC_SET(humidity, LocalSensor) FC_SET(rpm, LocalSensor) FC_SET(target_rpm, LocalSensor)
                                 FC_SET(pwm, LocalSensor) FC_SET(progress, LocalSensor) FC_SET(fault, LocalText)
                                     FC_SET(calibration, LocalText) FC_SET(firmware_version, LocalText)
                                         FC_SET(calibrate, ControlButton) FC_SET(cancel, ControlButton)
                                             FC_SET(power, ControlSelect)
#undef FC_SET
                                                 private : fan_ui::UI ui_;
  fan_ui::Page page_{fan_ui::Page::MAIN};
  struct Record {
    uint32_t seq{};
    char json[2048]{};
  };
  ESPPreferenceObject slots_[2];
  uint32_t sequence_{}, last_tick_{}, last_publish_{}, save_at_{}, zero_at_{};
  unsigned last_faults_{};
  ControllerCore::Phase last_phase_{ControllerCore::Phase::IDLE};
  bool powered_{}, booted_{}, reset_pending_{};
  std::string last_error_;
  void publish();
  void apply_output();
  void translate();
  bool save();
  void factory_reset();
  bool read_config(JsonObject obj, Settings &out, bool full);
  void config_json(JsonObject obj, const Settings &s);
  std::string status();
  bool command(JsonObject obj);
};
}  // namespace esphome::single_fan
