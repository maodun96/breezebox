"""Execute production boot selection with simulated NVS absence/read errors."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

root = Path(__file__).parents[1]
source = (root/'components/single_fan/single_fan.cpp').read_text()
read_config = source.split('bool Controller::read_config(')[1].split('bool Controller::save()')[0]
required = re.search(r'const char \*required\[\]\s*=\s*\{(.*?)\};', read_config, re.S)[1]
legacy_record = {'enabled', 'automatic', 'english', 'prompt_seen', 'manual_unit',
                 'curve_unit', 'power', 'manual', 'last_pwm', 'last_rpm',
                 'pulses', 'points', 'cal'}
assert {key.strip().strip('"') for key in required.split(',')} <= legacy_record
compact = re.sub(r'\s+', '', read_config)
assert 'if(!o["custom_unit"].isNull())' in compact and '{"custom",&s.custom}' in compact
probe = source.split('static constexpr uint32_t CONFIG_KEY')[1].split('static const char *calibration_label')[0]
setup = '  power_output_' + source.split('void Controller::setup() {')[1].split('  power_output_',1)[1].split('  temperature_source_')[0]
code = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <iostream>
constexpr int ESP_OK=0, ESP_ERR_NVS_NOT_FOUND=1, NVS_READONLY=0;
using nvs_handle_t=int;
int open_error=0, blob_error[2]={1,1}, closes=0, probes=0;
bool readable[2]={false,false}, valid[2]={false,false}, save_ok=true;
int nvs_open(const char*,int,nvs_handle_t* h){*h=1;return open_error;}
int nvs_get_blob(nvs_handle_t,const char* key,void*,size_t*) {++probes;return blob_error[std::stoul(key)-0x53464E20];}
void nvs_close(nvs_handle_t){++closes;}
unsigned millis(){return 0;}
using JsonObject=int;
namespace json {template<class F> bool parse_json(const std::string& s,F f){return f(s[0]-'0');}}
struct Settings {int id=-1;};
struct Record {uint32_t seq{};char json[2048]{};};
struct Preference {
 unsigned i;
 bool load(Record* r){if(!readable[i])return false;r->seq=i+1;r->json[0]='0'+i;return true;}
};
struct Preferences {template<class T> Preference make_preference(unsigned key,bool){return {key-0x53464E20};}} preferences;
auto* global_preferences=&preferences;
struct Core {Settings settings;bool config_fault=false,save_fault=false;void boot(unsigned){}};
struct Output {void turn_off(){} void set_level(float){}} output;
struct Controller {
 Core core;Preference slots_[2];uint32_t sequence_=0;int saves=0;
 Output *power_output_=&output,*pwm_output_=&output;
 bool read_config(JsonObject obj,Settings& s,bool){s.id=obj;return valid[obj];}
 bool save(){++saves;core.save_fault=!save_ok;if(save_ok)core.config_fault=false;return save_ok;}
 void setup();
};
'''
code += '\nstatic constexpr uint32_t CONFIG_KEY' + probe
code += '\nvoid Controller::setup() {' + setup + '\n}\n'
code += r'''
void reset(){open_error=0;closes=probes=0;save_ok=true;for(int i=0;i<2;i++){blob_error[i]=1;readable[i]=valid[i]=false;}}
int main(){
 assert(CONFIG_KEY==0x53464E20);
 reset();Controller first;first.setup();assert(!first.core.config_fault && first.saves==1 && first.core.settings.id==-1 && closes==1 && probes==2);
 reset();Controller factory_reset;factory_reset.setup();assert(!factory_reset.core.config_fault && factory_reset.saves==1);
 reset();readable[0]=valid[0]=true;blob_error[0]=0;Controller reboot;reboot.setup();assert(!reboot.core.config_fault && reboot.saves==0 && reboot.core.settings.id==0 && probes==0);
 reset();readable[0]=true;blob_error[0]=0;Controller corrupt;corrupt.setup();assert(corrupt.core.config_fault && corrupt.saves==0);
 reset();blob_error[1]=0;Controller wrong_length;wrong_length.setup();assert(wrong_length.core.config_fault && wrong_length.saves==0);
 reset();blob_error[0]=2;Controller io_error;io_error.setup();assert(io_error.core.config_fault && io_error.saves==0 && closes==1);
 reset();open_error=2;Controller open_failed;open_failed.setup();assert(open_failed.core.config_fault && open_failed.saves==0 && closes==0);
 reset();open_error=1;Controller no_namespace;no_namespace.setup();assert(!no_namespace.core.config_fault && no_namespace.saves==1);
 reset();save_ok=false;Controller write_failed;write_failed.setup();assert(!write_failed.core.config_fault && write_failed.core.save_fault && write_failed.saves==1);
 reset();readable[0]=readable[1]=true;valid[0]=true;blob_error[0]=blob_error[1]=0;Controller backup;backup.setup();assert(!backup.core.config_fault && backup.saves==0 && backup.core.settings.id==0);
 reset();readable[0]=readable[1]=valid[0]=valid[1]=true;Controller newest;newest.setup();assert(newest.core.settings.id==1 && newest.saves==0);
 std::cout << "PASS config boot: fresh/reset initialization, valid backup, newest record, damaged/incorrect length/read errors preserved, initialization save failure\n";
}
'''
with tempfile.TemporaryDirectory(prefix='fan-config-boot-') as tmp:
    cpp = Path(tmp)/'test.cpp'; binary = Path(tmp)/'test'
    cpp.write_text(code)
    subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
