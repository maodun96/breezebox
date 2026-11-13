"""Run with the firmware's ESPHome environment; checks real name generation."""
from pathlib import Path
import subprocess
import tempfile

import esphome
from esphome.core.config import make_app_name_cpp
from esphome.yaml_util import load_yaml

root = Path(__file__).resolve().parents[1]
config = load_yaml(root / "config.yaml")
assert config["esphome"]["name_add_mac_suffix"] is True
assert "ssid" not in config["wifi"]["ap"]  # Native AP naming uses App.get_name().
lib = Path(esphome.__file__).parent
header = (lib / "core/application.h").read_text()
method = "void pre_setup(char *name" + header.split("void pre_setup(char *name", 1)[1].split("\n#else", 1)[0]
declarations = []
lengths = []
for key, var, separator in [("name", "name", "-"), ("friendly_name", "friendly", " ")]:
    _, declaration, length = make_app_name_cpp(config["esphome"][key], var, separator, add_mac_suffix=True)
    declarations.append(declaration)
    lengths.append(length)
source = r'''
#include <cassert>
#include <cstring>
#include <string>
using StringRef = std::string;
constexpr size_t MAC_ADDRESS_BUFFER_SIZE = 13;
const char *mac;
void arch_init() {}
void get_mac_address_into_buffer(char *out) { std::strcpy(out, mac); }
struct App {
 bool name_add_mac_suffix_ = false;
 std::string name_, friendly_name_;
''' + method + "\n};\nint main() {\n" + "\n".join(declarations) + f'''
 App app;
 std::string first;
 for (const char *device_mac : {{"aabbcca09058", "aabbcca09059", "aabbcca09058"}}) {{
   mac = device_mac;
   app.pre_setup(name, {lengths[0]}, friendly, {lengths[1]});
   assert(app.name_add_mac_suffix_);
   assert(app.name_ == std::string("{config['esphome']['name']}-") + (mac + 6));
   assert(app.friendly_name_ == std::string("{config['esphome']['friendly_name']} ") + (mac + 6));
   assert(app.name_.size() <= 32); // Native AP SSID fits without truncation.
   if (first.empty()) first = app.name_;
   else assert((first == app.name_) == (std::string(mac) == "aabbcca09058"));
 }}
}}
'''
with tempfile.TemporaryDirectory() as directory:
    cpp = Path(directory) / "identity.cpp"
    binary = Path(directory) / "identity"
    cpp.write_text(source)
    subprocess.run(["c++", "-std=c++17", str(cpp), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("Device identity: distinct MAC names and stable restart names passed")
