"""Exercise the production scan guard without an ESP32 or saved credentials."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

header = (Path(__file__).resolve().parents[1] / 'components/wifi/wifi_component.h').read_text()
method = re.search(r'  bool provisioning_scan\(\) \{.*?\n  \}', header, re.S)[0]
source = '''#include <cassert>
#include <cstdio>
struct Probe {
  enum { WIFI_COMPONENT_STATE_STA_SCANNING=1, CONNECTED=2 };
  enum class RoamingState { IDLE, SCANNING };
  int state_=WIFI_COMPONENT_STATE_STA_SCANNING;
  RoamingState roaming_state_=RoamingState::IDLE;
  bool scan_done_=true, driver_ok=true;
  int calls=0;
  bool wifi_scan_start_(bool) { ++calls; if(driver_ok)scan_done_=false; return driver_ok; }
''' + method + '''
};
int main() {
  Probe reset; // Captive portal already received the completed boot scan.
  assert(reset.provisioning_scan() && reset.calls==1 && !reset.scan_done_);
  assert(reset.provisioning_scan() && reset.calls==1); // Reuse a genuinely active scan.
  reset.scan_done_=true;
  assert(reset.provisioning_scan() && reset.calls==2); // Refresh after completion.
  Probe active; active.scan_done_=false;
  assert(active.provisioning_scan() && active.calls==0);
  Probe online; online.state_=Probe::CONNECTED;
  assert(online.provisioning_scan() && online.calls==1);
  Probe roaming; roaming.state_=Probe::CONNECTED;
  roaming.roaming_state_=Probe::RoamingState::SCANNING; roaming.scan_done_=false;
  assert(roaming.provisioning_scan() && roaming.calls==0);
  roaming.scan_done_=true;
  assert(roaming.provisioning_scan() && roaming.calls==1);
  Probe failed; failed.driver_ok=false;
  assert(!failed.provisioning_scan() && failed.calls==1);
  std::puts("PASS scan: reset boot completed, active scan, refresh, online, roaming, driver failure");
}
'''
with tempfile.TemporaryDirectory(prefix='fan-scan-test-') as directory:
    cpp, binary = Path(directory)/'probe.cpp', Path(directory)/'probe'
    cpp.write_text(source)
    subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
