#include "captive_portal.h"
#ifdef USE_CAPTIVE_PORTAL
#include "esphome/core/log.h"
#include "esphome/core/application.h"
#include "esphome/core/helpers.h"
#include "esphome/core/string_ref.h"
#include "esphome/components/wifi/scan_list.h"
#include "esphome/components/wifi/wifi_component.h"
#ifdef USE_PROVISIONING
#include "esphome/components/provisioning/provisioning.h"
#endif
#include "esphome/components/json/json_util.h"

namespace esphome::captive_portal {

static const char *const TAG = "captive_portal";
extern const unsigned char INDEX_GZ[];
extern const size_t INDEX_GZ_SIZE;

void CaptivePortal::handle_config(AsyncWebServerRequest *request) {
  auto data = json::build_json([](JsonObject root) {
    root["mac"] = get_mac_address_pretty();
    root["name"] = App.get_name().c_str();
    auto aps = root["aps"].to<JsonArray>();
    aps.add<JsonObject>();  // Retain the upstream response shape.
    wifi::ScanResultsLock lock(wifi::global_wifi_component);
    for (const auto &scan : wifi::global_wifi_component->get_scan_result()) {
      if (scan.get_is_hidden()) continue;
      auto ap = aps.add<JsonObject>();
      ap["ssid"] = scan.get_ssid().c_str();
      ap["rssi"] = scan.get_rssi();
      ap["lock"] = scan.get_with_auth();
    }
  });
  auto *response = request->beginResponse(200, "application/json", data.c_str());
  response->addHeader("Cache-Control", "no-store");
  request->send(response);
}
void CaptivePortal::handle_wifisave(AsyncWebServerRequest *request) {
  const auto &ssid = request->arg("ssid");
  const auto &psk = request->arg("psk");
  if (ssid.find('\0') != std::string::npos || psk.find('\0') != std::string::npos || ssid.empty() || ssid.size() > 32 || psk.size() > 64 || (psk.size() > 0 && psk.size() < 8) ||
      (psk.size() == 64 && psk.find_first_not_of("0123456789abcdefABCDEF") != std::string::npos)) {
    request->send(400, "text/plain", "Check the network name and password.");
    return;
  }
  ESP_LOGI(TAG, "Received Wi-Fi settings from captive portal");
#ifdef USE_ESP8266
  // ESP8266 is single-threaded, call directly
  wifi::global_wifi_component->save_wifi_sta(ssid.c_str(), psk.c_str());
#else
  // Defer save to main loop thread to avoid NVS operations from HTTP thread
  this->defer([ssid, psk]() { wifi::global_wifi_component->save_wifi_sta(ssid.c_str(), psk.c_str()); });
#endif
  request->send(200, ESPHOME_F("text/plain"), ESPHOME_F("Saved. Connecting..."));
}

void CaptivePortal::setup() {
  // Disable loop by default - will be enabled when captive portal starts
  this->disable_loop();
#ifdef USE_PROVISIONING
  // The captive portal is a provisioning surface: once the provisioning window
  // has closed, stop serving it. WiFi's own closed-callback shuts down the
  // access point the portal runs on, and the gated fallback in WiFiComponent's
  // loop() ensures neither is started again afterwards.
  if (provisioning::global_provisioning_manager != nullptr) {
    provisioning::global_provisioning_manager->add_on_closed_callback([this]() {
      if (this->active_) {
        ESP_LOGD(TAG, "Provisioning window closed; stopping captive portal");
        this->end();
      }
    });
  }
#endif
}
void CaptivePortal::start() {
  this->base_->init();
  if (!this->initialized_) {
    this->base_->add_handler_without_auth(this);
  }

  network::IPAddress ip = wifi::global_wifi_component->wifi_soft_ap_ip();

#if defined(USE_ESP32)
  // Create DNS server instance for ESP-IDF
  this->dns_server_ = make_unique<DNSServer>();
  this->dns_server_->start(ip);
#elif defined(USE_ARDUINO)
  this->dns_server_ = make_unique<DNSServer>();
  this->dns_server_->setErrorReplyCode(DNSReplyCode::NoError);
  this->dns_server_->start(53, ESPHOME_F("*"), ip);
#endif

  this->initialized_ = true;
  this->active_ = true;

  // Enable loop() now that captive portal is active
  this->enable_loop();

  ESP_LOGV(TAG, "Captive portal started");
}

void CaptivePortal::handleRequest(AsyncWebServerRequest *req) {
#ifdef USE_ESP32
  char url_buf[AsyncWebServerRequest::URL_BUF_SIZE];
  StringRef url = req->url_to(url_buf);
#else
  const auto &url = req->url();
#endif
  if (url == ESPHOME_F("/wifisave") && req->method() != HTTP_POST) { req->send(405, "text/plain", "Use POST"); return; }
  if (url == ESPHOME_F("/captive-portal-api")) {
    auto data = json::build_json([](JsonObject root) {
      char ip_buf[network::IP_ADDRESS_BUFFER_SIZE];
      root["captive"] = true;
      root["user-portal-url"] = std::string("http://") + wifi::global_wifi_component->wifi_soft_ap_ip().str_to(ip_buf) + "/";
    });
    auto *response = req->beginResponse(200, "application/captive+json", data.c_str());
    response->addHeader("Cache-Control", "private");
    req->send(response);
    return;
  }
  if (url == ESPHOME_F("/config.json")) {
    this->handle_config(req);
    return;
  } else if (url == ESPHOME_F("/wifisave")) {
    this->handle_wifisave(req);
    return;
  }

  // All other requests get the captive portal page
  // This includes OS captive portal detection endpoints which will trigger
  // the captive portal when they don't receive their expected responses
#ifndef USE_ESP8266
  auto *response = req->beginResponse(200, ESPHOME_F("text/html"), INDEX_GZ, INDEX_GZ_SIZE);
#else
  auto *response = req->beginResponse_P(200, ESPHOME_F("text/html"), INDEX_GZ, INDEX_GZ_SIZE);
#endif
#ifdef USE_CAPTIVE_PORTAL_GZIP
  response->addHeader(ESPHOME_F("Content-Encoding"), ESPHOME_F("gzip"));
#else
  response->addHeader(ESPHOME_F("Content-Encoding"), ESPHOME_F("br"));
#endif
  req->send(response);
}

CaptivePortal::CaptivePortal(web_server_base::WebServerBase *base) : base_(base) { global_captive_portal = this; }
float CaptivePortal::get_setup_priority() const {
  // Before WiFi
  return setup_priority::WIFI + 1.0f;
}
void CaptivePortal::dump_config() { ESP_LOGCONFIG(TAG, "Captive Portal:"); }

CaptivePortal *global_captive_portal = nullptr;  // NOLINT(cppcoreguidelines-avoid-non-const-global-variables)

}  // namespace esphome::captive_portal

#endif
