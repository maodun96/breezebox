# ESPHome provisioning patches

`wifi/`, `esp32_ble_server/` and `improv_ble/` originate from ESPHome 2026.10.1. C/C++ runtime files are GPLv3; Python files are MIT (ESPHOME-LICENSE).
The local override retains the upstream Wi-Fi driver and BLE service.

Changes: retain IDF auth-mode byte in scan results; expose on-demand scan and RAM-only profile backup/restore; add Improv device-info and bounded Wi-Fi list; validate packet bounds before upstream parsing; remove credential logs; automatically authorize provisioning; online sessions expire after three minutes, offline devices stay available; preserve old Wi-Fi until successful connection; restore on connection failure/cancel; keep an accepted Wi-Fi attempt running across BLE disconnections; return a local URL with stable Wi-Fi MAC fragment; retain BLE memory for subsequent sessions. BLE protocol authorization is not encryption or account binding.

Single-fan changes: network-page center click remains an optional shortcut; `/control` provision opens/renews a usable pairing window without physical authorization, existing control/reset/calibration semantics retained.

BLE server patch: upstream 2026.10.1 supplies correct long-read offsets and chunks; no local long-read patch remains. The override is still needed for per-connection negotiated ATT MTU tracking and notification truncation to MTU - 3, plus `BLEService::is_stopped()` for restarting pairing without reboot. Hardware provisioning remains the acceptance check.

Restart fix: Improv starts both CREATED and STOPPED GATT services, allowing a new pairing window without reboot after cancellation/timeout/completion.

Wi-Fi reconnect no longer independently stops Improv: completion/window expiry are owned by Improv, preserving retries after failed network changes.

`provision_cancel` closes an idle online pairing session; it never aborts an accepted Wi-Fi attempt or disables offline recovery. The three-minute online timer is the fallback when App cleanup cannot reach the device.

On-demand scan checks the actual completion flag before reusing a connection scan. With no saved credentials, the boot scan can finish while connection state remains STA_SCANNING; a later BLE request must start a new scan instead of waiting for an event that already happened.

`captive_portal/` also originates from ESPHome 2026.10.1 (C/C++ GPLv3, Python MIT). DNS now immediately echoes standard non-A/IN questions with an authoritative NOERROR empty answer, avoiding client timeouts for AAAA and HTTPS/SVCB queries. OTA handling remains upstream. `/captive-portal-api` returns `application/captive+json` with `captive: true`, the AP user-portal URL and `Cache-Control: private` (RFC 8908). Its page is generated from `web/captive.html` as deterministic gzip at build time: Chinese/English network selection (English default, top-right toggle, plain white background), separate password entry, secondary device information and firmware upload. Credentials use POST with bounds checks and no credential logging. `/config.json` uses the existing JSON serializer so SSIDs containing quotes and backslashes remain valid; the legacy `aps` shape is retained. No new scan or connection protocol is introduced; submitted Wi-Fi is not presented as confirmed success.


Migration constraints: the configuration explicitly loads local `improv_ble`, avoiding the old `esp32_improv` alias silently selecting upstream. `build.py check` generates the real configuration and compares every generated Improv C++ file with the override, including RPC 3 (device information) and RPC 4 (Wi-Fi list). Upstream provisioning-manager hooks are retained, but `provisioning:` is not enabled; the existing online three-minute window and offline recovery remain owned by Improv.

Wi-Fi advertises `/captive-portal-api` in DHCP option 114 (RFC 8910), because this URI identifies the captive JSON API rather than the HTML page.

Wi-Fi remains an override because Improv needs the authentication byte, an on-demand scan (including empty completion), and RAM-only profile backup/restore. Captive portal remains an override because the upstream page is not our bilingual page; upstream JSON escaping and network deduplication are used while retaining the legacy `aps` response shape and our credential checks. The page itself is unchanged.

Single-fan API adaptations: use the renamed Improv namespace; the generated Home Assistant API name patch now targets 2026.10.1 and runs from `build.py` after source generation, because native ESP-IDF does not execute PlatformIO pre-scripts. Build through `build.py build` to retain translated display names and legacy object IDs. No fan-control or calibration behavior is changed.
