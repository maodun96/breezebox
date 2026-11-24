#pragma once
#include "ble_sensor_driver.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string_view>

namespace fan_core {
static constexpr float START_KICK_OUTPUT = 50;
static constexpr uint32_t START_KICK_MS = 1000;
enum class Unit : uint8_t { PWM, RPM };
enum class Power : uint8_t { RESTORE, OFF, AUTO };
struct Point {
  float temp{}, value{};
};
struct Calibration {
  bool valid{};
  float minimum{15}, minimum_measured{}, minimum_rpm{}, maximum{100}, auto_raised{};
  std::array<float, 11> rpm{};
  std::array<float, 51> rpm_dense{};
  uint8_t rpm_step{2};
};
inline bool valid_device_name(std::string_view s) {
  if (s.empty() || s.size() > 63 || s.front() == ' ' || s.back() == ' ')
    return false;
  unsigned count = 0;
  for (size_t i = 0; i < s.size();) {
    uint32_t c = static_cast<unsigned char>(s[i++]);
    unsigned n = 0;
    uint32_t minimum = 0;
    if (c < 0x80) {
      if (c < 0x20 || c == 0x7F)
        return false;
    } else if (c >= 0xC2 && c <= 0xDF) {
      c &= 0x1F;
      n = 1;
      minimum = 0x80;
    } else if (c >= 0xE0 && c <= 0xEF) {
      c &= 0x0F;
      n = 2;
      minimum = 0x800;
    } else if (c >= 0xF0 && c <= 0xF4) {
      c &= 7;
      n = 3;
      minimum = 0x10000;
    } else
      return false;
    while (n--) {
      if (i >= s.size())
        return false;
      unsigned b = static_cast<unsigned char>(s[i++]);
      if ((b & 0xC0) != 0x80)
        return false;
      c = (c << 6) | (b & 0x3F);
    }
    if (c < minimum || c > 0x10FFFF || (c >= 0xD800 && c <= 0xDFFF) || (c >= 0x80 && c <= 0x9F))
      return false;
    if (++count > 20)
      return false;
  }
  return true;
}
struct Settings {
  SensorSource sensor_source{SensorSource::INTERNAL};
  ExtSensorConfig ext_sensor{};
  uint16_t ext_handle{};
  std::array<char, 64> device_name{
      {'P', 'W', 'M', ' ', char(0xE9), char(0xA3), char(0x8E), char(0xE6), char(0x89), char(0x87), 0}};
  bool enabled{}, automatic{}, english{}, prompt_seen{}, resume_once{};
  Unit manual_unit{Unit::PWM}, custom_unit{Unit::PWM}, curve_unit{Unit::PWM};
  Power power{Power::RESTORE};
  float manual{30}, custom{}, last_pwm{30}, last_rpm{1000};
  uint8_t count{3}, pulses{2};
  std::array<Point, 10> points{{{30, 0}, {40, 50}, {50, 100}}};
  Calibration cal{};
};
inline bool finite_range(float x, float lo, float hi) { return std::isfinite(x) && x >= lo && x <= hi; }
inline float scale_to_output(float minimum, float value) {
  if (value <= 0)
    return 0;
  value = std::clamp(value, 1.0f, 100.0f);
  return minimum + (value - 1) * (100 - minimum) / 99;
}
inline float output_to_scale(float minimum, float output) {
  if (output <= 0)
    return 0;
  if (output <= minimum)
    return 1;
  return 1 + (output - minimum) * 99 / (100 - minimum);
}
inline bool valid_settings(const Settings &s) {
  if (!valid_ext(s.ext_sensor) || unsigned(s.sensor_source) > 1 ||
      (s.sensor_source == SensorSource::EXTERNAL && !s.ext_sensor.bound)) return false;
  const auto end = std::find(s.device_name.begin(), s.device_name.end(), '\0');
  if (end == s.device_name.end() ||
      !valid_device_name(std::string_view(s.device_name.data(), end - s.device_name.begin())))
    return false;
  if (s.count < 2 || s.count > 10 || s.pulses != 2 || unsigned(s.power) > 2 || unsigned(s.manual_unit) > 1 ||
      unsigned(s.custom_unit) > 1 || s.curve_unit != Unit::PWM)
    return false;
  if (!finite_range(s.cal.minimum, 1, 100) || !finite_range(s.cal.minimum_measured, 0, s.cal.minimum) ||
      s.cal.maximum != 100 || !finite_range(s.cal.auto_raised, 0, 85) || !finite_range(s.cal.minimum_rpm, 0, 100000))
    return false;
  float previous = 0;
  for (float r : s.cal.rpm) {
    if (!finite_range(r, previous, 100000))
      return false;
    previous = r;
  }
  if (s.cal.rpm_step != 2)
    return false;
  const unsigned last = 100 / s.cal.rpm_step;
  previous = 0;
  for (unsigned i = 0; i < s.cal.rpm_dense.size(); i++) {
    const float r = s.cal.rpm_dense[i];
    if (i > last ? r != 0 : !finite_range(r, previous, 100000))
      return false;
    previous = r;
  }
  if (s.cal.rpm_dense[last] > 0 && s.cal.rpm_dense[last] != s.cal.rpm[10])
    return false;
  if (s.cal.valid && (s.cal.rpm[10] <= 0 || s.cal.minimum_rpm > s.cal.rpm[10]))
    return false;
  if (s.manual_unit == Unit::RPM && !s.cal.valid)
    return false;
  if (s.custom_unit == Unit::RPM && !s.cal.valid)
    return false;
  if (!finite_range(s.manual, 0, s.manual_unit == Unit::PWM ? 100 : s.cal.rpm[10]) ||
      !finite_range(s.custom, 0, s.custom_unit == Unit::PWM ? 100 : s.cal.rpm[10]) ||
      (s.custom_unit == Unit::PWM && s.custom > 0 && s.custom < 1) || !finite_range(s.last_pwm, 1, 100) ||
      !finite_range(s.last_rpm, 1, 100000))
    return false;
  for (unsigned i = 0; i < s.count; i++) {
    const auto &p = s.points[i];
    if (!finite_range(p.temp, 0, 50) || p.temp != std::round(p.temp) || (i && p.temp <= s.points[i - 1].temp) ||
        !finite_range(p.value, 0, 100) || (i && p.value < s.points[i - 1].value))
      return false;
  }
  return true;
}
inline float curve(const Settings &s, float t) {
  if (t <= s.points[0].temp)
    return s.points[0].value;
  for (unsigned i = 1; i < s.count; i++)
    if (t <= s.points[i].temp) {
      const auto &a = s.points[i - 1], &b = s.points[i];
      return a.value + (b.value - a.value) * (t - a.temp) / (b.temp - a.temp);
    }
  return s.points[s.count - 1].value;
}
inline float table_rpm(const Calibration &c, float pwm) {
  const bool dense = c.rpm_dense[100 / c.rpm_step] > 0;
  const unsigned step = dense ? c.rpm_step : 10;
  pwm = std::clamp(pwm, 0.0f, 100.0f);
  unsigned i = std::min(unsigned(pwm / step), 100 / step - 1);
  const float a = dense ? c.rpm_dense[i] : c.rpm[i];
  const float b = dense ? c.rpm_dense[i + 1] : c.rpm[i + 1];
  return a + (b - a) * (pwm - i * step) / step;
}
inline float to_rpm(const Calibration &c, float pwm) {
  if (pwm <= 0)
    return 0;
  if (c.minimum_rpm > 0 && pwm < c.minimum)
    return 0;  // Below the verified range, no RPM estimate.
  float previous_pwm = c.minimum_rpm > 0 ? c.minimum : 0;
  float previous_rpm = c.minimum_rpm;
  const unsigned step = c.rpm_dense[100 / c.rpm_step] > 0 ? c.rpm_step : 10;
  for (unsigned next_pwm = step; next_pwm <= 100; next_pwm += step) {
    if (next_pwm <= previous_pwm)
      continue;
    const float next_rpm = std::max(previous_rpm, table_rpm(c, next_pwm));
    if (pwm <= next_pwm)
      return previous_rpm + (next_rpm - previous_rpm) * (pwm - previous_pwm) / (next_pwm - previous_pwm);
    previous_pwm = next_pwm;
    previous_rpm = next_rpm;
  }
  return previous_rpm;
}
inline float to_pwm(const Calibration &c, float rpm) {
  if (rpm <= 0)
    return 0;
  float previous_pwm = c.minimum_rpm > 0 ? c.minimum : 0;
  float previous_rpm = c.minimum_rpm;
  if (rpm <= previous_rpm)
    return previous_pwm;
  const unsigned step = c.rpm_dense[100 / c.rpm_step] > 0 ? c.rpm_step : 10;
  for (unsigned pwm = step; pwm <= 100; pwm += step) {
    if (pwm <= previous_pwm)
      continue;
    const float next_rpm = std::max(previous_rpm, table_rpm(c, pwm));
    if (rpm <= next_rpm && next_rpm > previous_rpm)
      return previous_pwm + (pwm - previous_pwm) * (rpm - previous_rpm) / (next_rpm - previous_rpm);
    previous_pwm = pwm;
    previous_rpm = next_rpm;
  }
  return 100;
}
class ControllerCore {
 public:
  Settings settings{};
  float temperature{NAN}, humidity{NAN}, rpm{NAN}, output{}, target{}, target_rpm{};
  bool temp_fault{}, rpm_fault{}, config_fault{}, save_fault{};
  bool dirty{}, calibration_pending_save{}, factory_requested{};
  enum class Phase { IDLE, FAILED, SIGNAL, TABLE, VERIFY };
  Phase phase{Phase::IDLE};
  unsigned progress{};
  const char *cal_error{""}, *cal_failed_stage{""};
  float cal_failed_output{};
  unsigned cal_retry() const { return verify_attempt_; }
  const std::array<float, 3> &cal_readings() const { return readings_; }
  bool calibrating() const { return phase != Phase::IDLE && phase != Phase::FAILED; }
  void boot(uint32_t now) {
    last_temp_ = now;
    last_good_rpm_ = now;
    if (settings.resume_once) {
      settings.resume_once = false;
      dirty = true;
      return;
    }
    if (settings.power == Power::OFF)
      settings.enabled = false;
    if (settings.power == Power::AUTO) {
      settings.enabled = true;
      settings.automatic = true;
    }
  }
  bool external() const { return settings.sensor_source == SensorSource::EXTERNAL; }
  void reset_temperature(uint32_t now) {
    last_temp_ = now;
    temperature = humidity = NAN;
    temp_fault = false;
    good_temp_ = 0;
  }
  void sample_external(const BleSample &s, uint32_t now) {
    if (!external() || !finite_range(s.temperature,-40,85) || !finite_range(s.humidity,0,100)) return;
    temperature = s.temperature;
    humidity = s.humidity;
    last_temp_ = now;
    temp_fault = false;
  }
  void sample_humidity(float h) { if (!external()) humidity = h; }
  void sample_temperature(float t, uint32_t now) {
    if (external()) return;
    if (std::isfinite(t)) {
      temperature = t;
      last_temp_ = now;
      if (++good_temp_ >= 2)
        temp_fault = false;
    } else
      good_temp_ = 0;
  }
  void sample_rpm(float r, uint32_t now) {
    rpm = r;
    rpm_time_ = now;
    if (std::isfinite(r) && r > 0) {
      last_good_rpm_ = now;
      if (run_ && !good_run_since_)
        good_run_since_ = now;
      if (++good_rpm_ >= 3) {
        rpm_fault = false;
        retries_ = 0;
      }
    } else
      good_rpm_ = 0;
  }
  bool enable(bool v) {
    if (!v && calibrating())
      cancel();
    if (calibrating())
      return false;
    if (v && !settings.enabled && !settings.automatic && settings.manual <= 0)
      settings.manual =
          settings.manual_unit == Unit::PWM ? settings.last_pwm : std::min(settings.last_rpm, settings.cal.rpm[10]);
    settings.enabled = v;
    dirty = true;
    if (!v) {
      output = 0;
      reset_run();
    }
    return true;
  }
  bool automatic(bool v) {
    if (calibrating())
      return false;
    settings.automatic = v;
    dirty = true;
    return true;
  }
  bool manual(float value, Unit unit) {
    if (calibrating() || (unit == Unit::RPM && !settings.cal.valid) ||
        !finite_range(value, 0, unit == Unit::PWM ? 100 : 100000))
      return false;
    if (unit == Unit::RPM && value > 0)
      value = std::clamp(value, to_rpm(settings.cal, settings.cal.minimum), settings.cal.rpm[10]);
    settings.automatic = false;
    settings.manual_unit = unit;
    settings.manual = value;
    remember();
    return enable(value > 0);
  }
  bool custom(float value, Unit unit) {
    if (calibrating() || (unit == Unit::RPM && !settings.cal.valid) ||
        !finite_range(value, 0, unit == Unit::PWM ? 100 : 100000) || (unit == Unit::PWM && value > 0 && value < 1))
      return false;
    if (unit == Unit::RPM && value > 0)
      value = std::clamp(value, to_rpm(settings.cal, settings.cal.minimum), settings.cal.rpm[10]);
    settings.custom_unit = unit;
    settings.custom = value;
    dirty = true;
    return true;
  }
  bool start_calibration(uint32_t now, bool auto_after = false) {
    if (calibrating() || calibration_pending_save)
      return false;
    snapshot_ = settings;
    snapshot_dirty_ = dirty;
    auto_after_ = auto_after;
    candidate_ = Calibration{};
    cal_error = cal_failed_stage = "";
    cal_failed_output = 0;
    progress = 0;
    step_index_ = 0;
    verify_attempt_ = 0;
    verify_hold_ = false;
    cal_since_ = cal_sample_at_ = now;
    enter(now, Phase::SIGNAL, 100);
    return true;
  }
  void cancel() {
    if (calibrating()) {
      settings = snapshot_;
      dirty = snapshot_dirty_;
      phase = Phase::IDLE;
      output = 0;
      reset_run();
      progress = 0;
    }
  }
  void calibration_save_result(bool ok) {
    save_fault = !ok;
    if (!ok)
      fail("save_failed");
    else
      calibration_pending_save = false;
  }
  void tick(uint32_t now) {
    if (external() ? uint32_t(now - last_temp_) > 180000 : uint32_t(now - last_temp_) >= 10000) {
      temp_fault = true;
      good_temp_ = 0;
      temperature = humidity = NAN;
    }
    if (uint32_t(now - rpm_time_) >= 5000)
      rpm = NAN;
    if (calibrating()) {
      cal_tick(now);
      return;
    }
    if (!settings.enabled) {
      output = target = target_rpm = 0;
      reset_run();
      return;
    }
    if (settings.automatic && !temp_fault && !std::isfinite(temperature)) {
      output = 0;
      return;
    }
    Unit unit = settings.automatic ? Unit::PWM : settings.manual_unit;
    target = settings.automatic ? curve(settings, temperature) : settings.manual;
    if (settings.automatic && temp_fault) {
      unit = Unit::PWM;
      target = 100;
    }
    if (unit == Unit::RPM && target > 0)
      target = std::max(target, to_rpm(settings.cal, settings.cal.minimum));
    float base = unit == Unit::PWM ? scale_to_output(settings.cal.minimum, target)
                                   : std::max(target > 0 ? settings.cal.minimum : 0.0f, to_pwm(settings.cal, target));
    target_rpm = unit == Unit::RPM ? target : (settings.cal.valid ? to_rpm(settings.cal, base) : 0);
    if (base <= 0) {
      output = 0;
      reset_run();
      return;
    }
    if (!run_) {
      run_ = true;
      run_start_ = now;
      last_good_rpm_ = now;
      good_run_since_ = 0;
    }
    if (uint32_t(now - run_start_) < START_KICK_MS) {
      output = std::max(START_KICK_OUTPUT, base);
      return;
    }
    if (uint32_t(now - last_good_rpm_) >= 4000 && (!rpm_fault || uint32_t(now - fault_retry_at_) >= 60000)) {
      if (good_run_since_ && uint32_t(now - good_run_since_) >= 10000 && base <= settings.cal.minimum + 5) {
        if (++low_stalls_ >= 2) {
          if (settings.cal.minimum < 60) {
            settings.cal.minimum = std::min(settings.cal.minimum + 2, 60.0f);
            settings.cal.auto_raised += 2;
            dirty = true;
          }
          low_stalls_ = 0;
        }
      }
      good_run_since_ = 0;
      last_good_rpm_ = now;
      if (retries_ < 3) {
        ++retries_;
        run_start_ = now;
        output = std::max(START_KICK_OUTPUT, base);
        return;
      }
      if (!rpm_fault) {
        rpm_fault = true;
        fault_retry_at_ = now;
      } else {
        fault_retry_at_ = now;
        run_start_ = now;
        output = std::max(START_KICK_OUTPUT, base);
        return;
      }
    }
    output = base;
  }
  const char *cal_stage() const {
    switch (phase) {
      case Phase::SIGNAL:
        return "signal";
      case Phase::TABLE:
        return "rpm_table";
      case Phase::VERIFY:
        return "verify";
      default:
        return "";
    }
  }
  uint32_t cal_wait_seconds(uint32_t now) const { return calibrating() ? (now - step_since_) / 1000 : 0; }
  float display_percent() const {
    if (!settings.enabled)
      return 0;
    if (settings.automatic)
      return std::clamp(target, 0.0f, 100.0f);
    return settings.manual_unit == Unit::PWM
               ? settings.manual
               : output_to_scale(settings.cal.minimum, to_pwm(settings.cal, settings.manual));
  }

 private:
  static constexpr std::array<unsigned, 28> STEPS{
      {95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 28, 26, 24, 22, 20, 18, 16, 14, 12, 10, 8, 6, 4, 2}};
  static constexpr uint32_t STABLE_SPAN_MS = 3800, SAMPLE_GAP_MS = 1500, STEP_TIMEOUT_MS = 15000;
  static constexpr float STABLE_RANGE_RPM = 60, STABLE_RANGE_RATIO = 0.05f;
  static constexpr float STABLE_TREND_RPM = 30, STABLE_TREND_RATIO = 0.02f;
  uint32_t last_temp_{}, rpm_time_{}, last_good_rpm_{}, run_start_{}, fault_retry_at_{}, good_run_since_{};
  uint32_t step_since_{}, sample_seen_{}, cal_since_{}, cal_sample_at_{};
  unsigned good_temp_{}, good_rpm_{}, retries_{}, low_stalls_{}, window_count_{}, step_index_{}, verify_attempt_{};
  bool run_{}, auto_after_{}, snapshot_dirty_{}, verify_hold_{};
  std::array<float, 5> window_{};
  std::array<uint32_t, 5> window_times_{};
  float full_speed_rpm_{}, lowest_running_{};
  std::array<float, 3> readings_{{NAN, NAN, NAN}};
  Settings snapshot_{};
  Calibration candidate_{};
  void reset_run() {
    run_ = false;
    rpm_fault = false;
    good_rpm_ = retries_ = low_stalls_ = 0;
    good_run_since_ = 0;
  }
  void remember() {
    if (settings.manual > 0) {
      if (settings.manual_unit == Unit::PWM)
        settings.last_pwm = settings.manual;
      else
        settings.last_rpm = settings.manual;
    }
  }
  void enter(uint32_t now, Phase next, float pwm) {
    phase = next;
    output = pwm;
    step_since_ = now;
    sample_seen_ = rpm_time_;
    window_count_ = 0;
    readings_.fill(NAN);
  }
  float median() const {
    auto values = window_;
    std::sort(values.begin(), values.begin() + window_count_);
    return values[window_count_ / 2];
  }
  // Zero and running share the window but never qualify as the same stable state.
  bool stable_sample(float &median) const {
    if (window_count_ < window_.size() || uint32_t(window_times_.back() - window_times_.front()) < STABLE_SPAN_MS)
      return false;
    auto sorted = window_;
    std::sort(sorted.begin(), sorted.end());
    median = sorted[sorted.size() / 2];
    if (sorted.back() == 0)
      return true;
    if (sorted.front() <= 0)
      return false;
    const float range = std::max(STABLE_RANGE_RPM, median * STABLE_RANGE_RATIO);
    const float trend = std::max(STABLE_TREND_RPM, median * STABLE_TREND_RATIO);
    return sorted.back() - sorted.front() <= range &&
           std::fabs((window_[3] + window_[4] - window_[0] - window_[1]) / 2) <= trend;
  }
  void fail(const char *reason) {
    cal_failed_stage = calibration_pending_save ? "saving" : cal_stage();
    cal_failed_output = output;
    settings = snapshot_;
    dirty = snapshot_dirty_;
    phase = Phase::FAILED;
    cal_error = reason;
    output = 0;
    reset_run();
    calibration_pending_save = false;
  }
  void finish_calibration() {
    for (unsigned i = 0; i < 11; i++)
      candidate_.rpm[i] = candidate_.rpm_dense[i * 5];
    candidate_.auto_raised = 0;
    candidate_.valid = true;
    Settings result = snapshot_;
    result.cal = candidate_;
    result.last_rpm = std::min(result.last_rpm, candidate_.rpm[10]);
    if (result.manual_unit == Unit::RPM)
      result.manual = std::min(result.manual, candidate_.rpm[10]);
    if (result.custom_unit == Unit::RPM)
      result.custom = std::min(result.custom, candidate_.rpm[10]);
    if (!valid_settings(result)) {
      fail("invalid_calibration");
      return;
    }
    settings = result;
    if (auto_after_)
      settings.automatic = true;
    settings.prompt_seen = true;
    dirty = true;
    calibration_pending_save = true;
    phase = Phase::IDLE;
    progress = 100;
    output = 0;
    reset_run();
  }
  void build_table() {
    candidate_.rpm_dense.fill(0);
    std::array<unsigned, STEPS.size() + 1> outputs{};
    std::array<float, STEPS.size() + 1> rpms{};
    outputs[0] = 100;
    rpms[0] = candidate_.rpm_dense[50] = full_speed_rpm_;
    unsigned count = 1;
    for (unsigned i = 0; i < step_index_; i++) {
      unsigned pwm = STEPS[i];
      float value = measured_[i];
      outputs[count] = pwm;
      rpms[count++] = std::min(value, full_speed_rpm_);
    }
    for (unsigned i = count - 1; i > 0; i--)
      rpms[i - 1] = std::max(rpms[i - 1], rpms[i]);
    for (unsigned i = 1; i < count; i++) {
      unsigned high = outputs[i - 1], low = outputs[i];
      for (unsigned pwm = low + low % 2; pwm <= high; pwm += 2)
        candidate_.rpm_dense[pwm / 2] = rpms[i] + (rpms[i - 1] - rpms[i]) * (pwm - low) / (high - low);
    }
    candidate_.rpm_dense[0] = 0;
    candidate_.minimum_measured = lowest_running_;
    candidate_.minimum = std::min(lowest_running_ + (measured_[step_index_ - 1] == 0 ? 2 : 0), 100.0f);
  }
  std::array<float, STEPS.size()> measured_{};
  void next_table(uint32_t now) {
    if (step_index_ < STEPS.size()) {
      enter(now, Phase::TABLE, STEPS[step_index_]);
      progress = 5 + step_index_ * 80 / STEPS.size();
    } else {
      build_table();
      verify_attempt_ = 0;
      enter(now, Phase::VERIFY, 100);
      progress = 85;
    }
  }
  void cal_tick(uint32_t now) {
    if (uint32_t(now - cal_since_) >= 600000) {
      fail("calibration_timeout");
      return;
    }
    bool stopped = false;
    if (rpm_time_ != sample_seen_) {
      cal_sample_at_ = sample_seen_ = rpm_time_;
      readings_[0] = readings_[1];
      readings_[1] = readings_[2];
      readings_[2] = rpm;
      if (phase == Phase::VERIFY && verify_hold_ && rpm == 0)
        stopped = true;
      if (uint32_t(rpm_time_ - step_since_) >= 1000 && std::isfinite(rpm) && (phase != Phase::VERIFY || verify_hold_)) {
        stopped = rpm == 0;
        if (window_count_ && uint32_t(rpm_time_ - window_times_[window_count_ - 1]) > SAMPLE_GAP_MS)
          window_count_ = 0;
        if (window_count_ == window_.size()) {
          for (unsigned i = 1; i < window_.size(); i++) {
            window_[i - 1] = window_[i];
            window_times_[i - 1] = window_times_[i];
          }
          --window_count_;
        }
        window_[window_count_] = rpm;
        window_times_[window_count_++] = rpm_time_;
      }
    }
    if (uint32_t(now - cal_sample_at_) >= 5000) {
      fail("no_rpm");
      return;
    }
    float value = 0;
    const bool stable = stable_sample(value);
    if (phase == Phase::SIGNAL) {
      if (uint32_t(now - step_since_) < 5000 || (uint32_t(now - step_since_) < STEP_TIMEOUT_MS && !stable))
        return;
      bool any = false;
      for (unsigned i = 0; i < window_count_; i++)
        if (window_[i] > 0)
          any = true;
      if (!any) {
        fail("no_rpm");
        return;
      }
      full_speed_rpm_ = median();
      lowest_running_ = 100;
      step_index_ = 0;
      next_table(now);
      return;
    }
    if (phase == Phase::TABLE) {
      unsigned dwell = output >= 30 ? 4000 : 3000;
      if (!stopped &&
          (uint32_t(now - step_since_) < dwell || (uint32_t(now - step_since_) < STEP_TIMEOUT_MS && !stable)))
        return;
      value = stopped ? 0 : median();
      if (stopped) {
        measured_[step_index_] = 0;
        ++step_index_;
        build_table();
        verify_attempt_ = 0;
        enter(now, Phase::VERIFY, 100);
        progress = 85;
        return;
      }
      measured_[step_index_] = value;
      lowest_running_ = output;
      ++step_index_;
      next_table(now);
      return;
    }
    if (phase == Phase::VERIFY) {
      if (!verify_hold_) {
        if (uint32_t(now - step_since_) < 2000)
          return;
        verify_hold_ = true;
        enter(now, Phase::VERIFY, candidate_.minimum);
        return;
      }
      if (!stopped && !stable && uint32_t(now - step_since_) < STEP_TIMEOUT_MS)
        return;
      if (!stopped && window_count_ == window_.size()) {
        candidate_.minimum_rpm = median();
        finish_calibration();
        return;
      }
      candidate_.minimum = std::min(candidate_.minimum + 2, 100.0f);
      if (++verify_attempt_ >= 3) {
        candidate_.minimum_rpm = table_rpm(candidate_, candidate_.minimum);
        finish_calibration();
        return;
      }
      enter(now, Phase::VERIFY, 100);
      verify_hold_ = false;
      progress = 85 + verify_attempt_ * 4;
    }
  }
};
}  // namespace fan_core
