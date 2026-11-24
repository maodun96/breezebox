"""Exercise the actual HA option dispatch/localization bodies without a device."""
import ast
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
cpp = (ROOT/'components/single_fan/single_fan.cpp').read_text()
tree = ast.parse((ROOT/'components/single_fan/__init__.py').read_text())
entities = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ENTITIES' for t in n.targets))
actions = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'actions' for t in n.targets))
assert actions == dict(control_mode=1, calibrate=11, cancel=12, power=14)
assert not {'automatic', 'needs_calibration', 'manual_unit', 'rpm_setting'} & {e[0] for e in entities}
assert len(entities) == 14
assert next(e[3] for e in entities if e[0] == 'control_mode') == 'select'
assert next(e[3] for e in entities if e[0] == 'humidity') == 'sensor'

def body(start, end):
    return cpp.split(start, 1)[1].split(end, 1)[0]

labels = 'static const char *calibration_label' + body('static const char *calibration_label', 'void ControlFan::control')
control = re.search(r'void ControlSelect::control.*?\n}', cpp, re.S)[0]
translate = 'void Controller::translate()' + body('void Controller::translate()', 'void Controller::publish()')
core = (ROOT/'components/single_fan/core.h').read_text()
# Every currently emitted calibration stage/error must have a readable Chinese label.
codes = set(re.findall(r'return "([a-z_]+)"', core)) | set(re.findall(r'(?:fail|retry_step)\(\s*(?:now,\s*)?"([a-z_]+)"', core))
src = '''
#include <algorithm>
#include <cassert>
#include <cstring>
#include <initializer_list>
#include <string>
#include <vector>
bool ha_english=false;
struct Traits {
 std::vector<const char *> options;
 void set_options(std::initializer_list<const char *> v){options=v;}
 const auto &get_options()const{return options;}
};
struct Entity{Traits traits;void translate(bool){}};
struct Controller {
 struct {struct {bool english=false;} settings;} core;
 unsigned last_id=999;float last_value=-1;
 void action(unsigned id,float value){last_id=id;last_value=value;}
 void translate();
'''
src += ''.join(f' Entity {key}_storage;Entity *{key}_=&{key}_storage;\n' for key, *_ in entities)
src += '''};
struct ControlSelect{Traits traits;Controller *owner_;unsigned action_;void control(const std::string &v);};
'''+labels+control+translate
src += '''int main(){
 Controller c;
 for(bool en:{false,true}){
  c.core.settings.english=en;c.translate();
  assert(ha_english==en);
  assert(c.control_mode_->traits.options.size()==2);
  assert(std::string(c.control_mode_->traits.options[0])==(en?"Manual Speed":"手动风速"));
  assert(std::string(c.power_->traits.options[1])==(en?"Off":"保持关闭"));
  for(auto id:{1u,14u}){
   ControlSelect s{(id==1?c.control_mode_:c.power_)->traits,&c,id};
   for(unsigned i=0;i<s.traits.options.size();i++){
    s.control(s.traits.options[i]);assert(c.last_id==id&&c.last_value==i);
   }
   c.last_id=999;s.control("invalid");assert(c.last_id==999);
  }
 }
'''
for code in sorted(codes):
    src += f' assert(std::string(calibration_label("{code}",false))!="未知校准状态");\n'
src += '}\n'
with tempfile.TemporaryDirectory(prefix='fan-ha-check-') as tmp:
    p = Path(tmp)
    (p/'test.cpp').write_text(src)
    subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror',str(p/'test.cpp'),'-o',str(p/'test')], check=True)
    subprocess.run([str(p/'test')], check=True)
print('HA stable action IDs, localized option dispatch and calibration labels passed')
