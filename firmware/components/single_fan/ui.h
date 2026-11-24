#pragma once
#include <cstdint>

namespace fan_ui {
enum class Button { CENTER, UP, DOWN, LEFT, RIGHT };
enum class Page { MAIN, MODE, NETWORK, RESET, CONFIRM, RELEASE };
constexpr uint32_t SLEEP_MS = 30000, RESET_HOLD_MS = 1500, MENU_TIMEOUT_MS = 10000, POLL_MS = 100, CLICK_MIN_MS = 50,
                   CLICK_MAX_MS = 500;
constexpr int SLOW_TICKS = 5, MEDIUM_TICKS = 15, FAST_TICKS = 30;
constexpr int SLOW_PERIOD = 3, MEDIUM_PERIOD = 2, SINGLE_STEP = 1, FAST_STEP = 2, MAX_STEP = 5;
inline int acceleration(int tick) {
  if (tick > FAST_TICKS)
    return MAX_STEP;
  if (tick > MEDIUM_TICKS)
    return FAST_STEP;
  if (tick > SLOW_TICKS)
    return tick % MEDIUM_PERIOD == 0 ? SINGLE_STEP : 0;
  return tick == 1 || tick % SLOW_PERIOD == 0 ? SINGLE_STEP : 0;
}

// Host supplies display, timers, logging and fan operations; this state has no hardware dependencies.
class UI {
 public:
  template<class H> void center_state(H &h, bool pressed, uint32_t now) {
    if (pressed) {
      center_pressed_at = now;
      press(h, Button::CENTER, now);
    } else {
      uint32_t length = now - center_pressed_at;
      if (length >= CLICK_MIN_MS && length <= CLICK_MAX_MS)
        click(h, now);
      release(h, now);
    }
  }
  template<class H> void press(H &h, Button button, uint32_t now) {
    if (screen_off) {
      h.screen_power(true);
      screen_off = false;
      swallow = true;
      last_input = now;
      return;
    }
    swallow = false;
    last_input = now;
    if (button == Button::CENTER) {
      if (h.page() == Page::RESET && !h.calibrating())
        h.reset_timer(true);
      return;
    }
    h.reset_timer(false);
    hold_ticks = 0;
    h.log_press(button);
    if (h.calibrating())
      return;
    auto page = h.page();
    if (page == Page::CONFIRM || page == Page::RELEASE)
      h.show(Page::RESET);
    else if (button == Button::UP || button == Button::DOWN) {
      if (page == Page::MODE)
        h.toggle_mode();
    } else {
      int index = static_cast<int>(page);
      int direction = button == Button::LEFT ? -1 : 1;
      h.show(static_cast<Page>((index + direction + 4) % 4));
    }
    h.menu_timer();
    h.update();
  }
  template<class H> void click(H &h, uint32_t now) {
    if (swallow)
      return;
    last_input = now;
    h.log_click();
    if (h.calibrating())
      return;
    auto page = h.page();
    if (page == Page::MAIN)
      h.toggle_fan();
    else {
      h.menu_timer();
      if (page == Page::MODE)
        h.toggle_mode();
      else if (page == Page::NETWORK)
        h.authorize();
      else if (page == Page::CONFIRM)
        h.request_reset();
    }
    h.update();
  }
  template<class H> void release(H &h, uint32_t now) {
    if (swallow)
      return;
    last_input = now;
    h.reset_timer(false);
    if (h.page() == Page::RELEASE) {
      h.show(Page::CONFIRM);
      h.menu_timer();
      h.update();
    }
  }
  template<class H> void reset_timeout(H &h, bool center_pressed) {
    if (center_pressed && h.page() == Page::RESET && !h.calibrating()) {
      h.show(Page::RELEASE);
      h.update();
    }
  }
  template<class H> void menu_timeout(H &h) {
    h.show(Page::MAIN);
    h.update();
  }
  template<class H> void poll(H &h, uint32_t now, bool center, bool up, bool down, bool left, bool right) {
    bool any = up || down || left || right;
    if (any || center) {
      last_input = now;
      if (!swallow)
        h.menu_timer();
    }
    if (!screen_off && uint32_t(now - last_input) >= SLEEP_MS) {
      h.screen_power(false);
      screen_off = true;
    }
    if (swallow || !any) {
      hold_ticks = 0;
      return;
    }
    int accel = acceleration(++hold_ticks);
    if (!accel)
      return;
    if (h.page() == Page::MAIN && !h.automatic() && !h.calibrating()) {
      if (up) {
        if (!h.fan_on())
          h.set_speed(1);
        else {
          int cur = h.speed();
          if (cur + accel <= 100)
            h.set_speed(cur + accel);
        }
        h.update();
      } else if (down) {
        if (h.fan_on()) {
          int cur = h.speed();
          if (cur - accel > 0)
            h.set_speed(cur - accel);
          else
            h.fan_off();
        }
        h.update();
      }
    }
  }
  int hold_ticks{};
  uint32_t last_input{}, center_pressed_at{};
  bool screen_off{}, swallow{};
};
}  // namespace fan_ui
