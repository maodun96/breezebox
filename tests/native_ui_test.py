"""Check GPIO wiring and exercise the hardware-free UI against the original scenarios."""
from pathlib import Path
import subprocess, tempfile, re
ROOT=Path(__file__).resolve().parents[1]
yaml=(ROOT/'config.yaml').read_text()
def block(source,name):
    return source.split('  - platform: gpio\n    id: button_'+name+'\n',1)[1].split('\n  - platform:',1)[0].split('\ninterval:',1)[0]
for name in ['push','up','down','left','right']:
    now=block(yaml,name)
    assert 'number: '+{'push':'GPIO0','up':'GPIO22','down':'GPIO25','left':'GPIO26','right':'GPIO27'}[name] in now
    assert 'input: true' in now and 'pullup: true' in now and 'inverted: true' in now
    if name=='push':assert 'ignore_strapping_warning: true' in now
    assert '    on_' not in now
    assert ('center' if name=='push' else name)+'_button: button_'+name in yaml
assert '\ninterval:' not in yaml
ui=re.sub(r'\s+', '', (ROOT/'components/single_fan/ui.h').read_text())
assert 'CLICK_MIN_MS=50' in ui and 'CLICK_MAX_MS=500' in ui and 'POLL_MS=100' in ui
src=r'''
#include "core.h"
#include "ui.h"
#include <cassert>
#include <cstdio>
using namespace fan_ui;
struct PageMarker{};PageMarker pages[6];auto *page_main=&pages[0],*page_mode=&pages[1],*page_network=&pages[2],*page_reset=&pages[3],*page_confirm=&pages[4],*page_release=&pages[5];
struct Provisioning {int calls=0;void authorize(){calls++;}} fan_provisioning;
struct Screen {PageMarker *page=page_main;bool on=true;} oled;
struct Pin{bool state=false;} button_push,button_left,button_right,button_up,button_down;
uint32_t now_ms=0;
struct Timer {bool running=false;void execute(){running=true;}void stop(){running=false;}} menu_timeout_check,reset_hold;
struct Fan {
 fan_core::ControllerCore *core;bool state=false;
 struct Call{Fan*f;bool on;int speed=-1;void set_speed(int s){speed=s;}void perform(){if(speed>=0)f->core->manual(speed,fan_core::Unit::PWM);f->core->enable(on);f->state=f->core->settings.enabled;}};
 Call toggle(){return {this,!state};}Call turn_on(){return {this,true};}Call turn_off(){return {this,false};}
};
struct Controller {fan_core::ControllerCore core;Fan fan{&core};Fan *fan_=&fan;
 void action(unsigned,float value){core.automatic(value);}
} controller;
UI ui;
struct Host {
 Page page(){return static_cast<Page>(oled.page-pages);}
 void show(Page p){oled.page=&pages[static_cast<unsigned>(p)];}
 void screen_power(bool on){oled.on=on;}void update(){}
 void reset_timer(bool on){if(on)reset_hold.execute();else reset_hold.stop();}
 void menu_timer(){menu_timeout_check.execute();}void log_press(Button){}void log_click(){}
 bool calibrating(){return controller.core.calibrating();}bool automatic(){return controller.core.settings.automatic;}
 bool fan_on(){return controller.fan.state;}int speed(){return int(controller.core.display_percent());}
 void toggle_mode(){controller.action(1,!automatic());}
 void toggle_fan(){auto c=controller.fan.toggle();c.perform();}
 void set_speed(int speed){auto c=controller.fan.turn_on();c.set_speed(speed);c.perform();}
 void fan_off(){auto c=controller.fan.turn_off();c.perform();}
 void authorize(){fan_provisioning.authorize();}void request_reset(){controller.core.factory_requested=true;}
} host;
void center_click(){ui.click(host,now_ms);}void center_press(){ui.press(host,Button::CENTER,now_ms);}
void center_release(){ui.release(host,now_ms);}void hold_timeout(){ui.reset_timeout(host,button_push.state);}
void up_press(){ui.press(host,Button::UP,now_ms);}void down_press(){ui.press(host,Button::DOWN,now_ms);}
void left_press(){ui.press(host,Button::LEFT,now_ms);}void right_press(){ui.press(host,Button::RIGHT,now_ms);}
void poll(){ui.poll(host,now_ms,button_push.state,button_up.state,button_down.state,button_left.state,button_right.state);}
void clean(){controller.core=fan_core::ControllerCore{};controller.fan.state=false;oled.page=page_main;oled.on=true;button_push.state=button_left.state=button_right.state=button_up.state=button_down.state=false;ui.hold_ticks=0;ui.last_input=now_ms=0;ui.screen_off=ui.swallow=false;reset_hold.stop();menu_timeout_check.stop();}
// ESPHome invokes on_release and click callbacks on the same release. Exercise both orders.
void gesture(unsigned ms,bool click_first=false){
 button_push.state=true;center_press();
 for(unsigned t=100;t<=ms;t+=100){now_ms+=100;poll();if(t==1500 && reset_hold.running)hold_timeout();}
 if(ms>=1500 && oled.page==page_release){assert(!controller.core.factory_requested);poll();assert(oled.page==page_release);}
 button_push.state=false;
 if(click_first && ms>=50 && ms<=500)center_click();
 center_release();
 if(!click_first && ms>=50 && ms<=500)center_click();
}
int main(){
 for(unsigned duration:{49u,50u,500u,501u}) {
  clean();ui.center_state(host,true,1000);ui.center_state(host,false,1000+duration);
  assert(controller.core.settings.enabled==(duration>=50 && duration<=500));
 }
 clean();now_ms=29900;poll();assert(oled.on);now_ms=30000;poll();assert(!oled.on&&ui.screen_off);
 for(bool order:{false,true}){
  clean();now_ms=30000;poll();gesture(100,order);assert(oled.on&&!controller.core.settings.enabled&&ui.swallow);
  gesture(100,order);assert(controller.core.settings.enabled);
 }
 for(auto f:{up_press,down_press,left_press,right_press}){
  clean();now_ms=30000;poll();f();assert(oled.on&&oled.page==page_main&&!controller.core.settings.enabled);
 }
 clean();oled.page=page_reset;now_ms=30000;poll();gesture(15000);assert(oled.on&&oled.page==page_reset&&!reset_hold.running&&!controller.core.factory_requested);
 gesture(1500);assert(oled.page==page_confirm);
 clean();controller.core.manual(40,fan_core::Unit::PWM);controller.fan.state=true;now_ms=30000;poll();button_up.state=true;up_press();
 for(int i=0;i<40;i++){now_ms+=100;poll();}assert(controller.core.settings.manual==40&&ui.hold_ticks==0);
 button_up.state=false;poll();button_up.state=true;up_press();now_ms+=100;poll();assert(controller.core.settings.manual==41);
 for(bool order:{false,true}){
  for(unsigned ms:{49u,100u,500u,501u,800u,1000u,1499u}){clean();oled.page=page_reset;gesture(ms,order);assert(oled.page==page_reset&&!controller.core.factory_requested);assert(!reset_hold.running);}
  for(unsigned ms:{1500u,1501u,3000u,3001u,15000u}){clean();oled.page=page_reset;gesture(ms,order);assert(oled.page==page_confirm&&!controller.core.factory_requested);gesture(100,order);assert(controller.core.factory_requested);}
 }
 for(auto *p:{page_main,page_mode,page_network}){clean();oled.page=p;gesture(1000);assert(oled.page==p&&!controller.core.factory_requested);}
 // Feedback appears while held, cancellation cannot re-arm until a fresh press.
 for(auto f:{up_press,down_press,left_press,right_press}){
  for(bool recognized:{false,true}){
   clean();oled.page=page_reset;button_push.state=true;center_press();
   if(recognized){hold_timeout();assert(oled.page==page_release);}
   f();assert(!reset_hold.running);poll();button_push.state=false;center_release();
   assert(oled.page!=page_confirm&&!controller.core.factory_requested);
  }
 }
 clean();oled.page=page_reset;gesture(4000);gesture(15000);assert(oled.page==page_confirm&&!controller.core.factory_requested);
 clean();controller.core.start_calibration(0);oled.page=page_reset;gesture(4000);assert(oled.page==page_reset&&!controller.core.factory_requested);
 // A delayed callback after release cannot arm the confirmation.
 clean();oled.page=page_reset;gesture(100);hold_timeout();assert(oled.page==page_reset);
 // Confirmation timeout returns home, where a click never resets.
 clean();oled.page=page_reset;gesture(4000);assert(menu_timeout_check.running);
 ui.menu_timeout(host);assert(oled.page==page_main);gesture(100);assert(!controller.core.factory_requested);
 for(int p=0;p<4;p++){clean();oled.page=&pages[p];center_click();assert(oled.page==&pages[p]&&!controller.core.factory_requested);assert(controller.core.settings.enabled==(p==0));assert(controller.core.settings.automatic==(p==1));}
 clean();oled.page=page_network;int previous=fan_provisioning.calls;center_click();assert(fan_provisioning.calls==previous+1);
 clean();for(int i=1;i<=4;i++){right_press();assert(oled.page==&pages[i%4]);}left_press();assert(oled.page==page_reset);
 gesture(1500);assert(oled.page==page_confirm&&!controller.core.factory_requested);
 assert(!controller.core.factory_requested);center_click();assert(controller.core.factory_requested);
 for(auto f:{up_press,down_press,left_press,right_press}){clean();oled.page=page_confirm;f();assert(oled.page==page_reset&&!controller.core.factory_requested);}
 clean();oled.page=page_mode;up_press();assert(controller.core.settings.automatic);down_press();assert(!controller.core.settings.automatic);
 clean();controller.core.manual(40,fan_core::Unit::PWM);controller.fan.state=true;button_up.state=true;up_press();for(int i=0;i<31;i++)poll();assert(controller.core.settings.manual==82);
 controller.core.manual(99,fan_core::Unit::PWM);ui.hold_ticks=31;poll();assert(controller.core.settings.manual==99);
 clean();button_up.state=true;up_press();poll();assert(controller.core.settings.manual==1&&controller.core.settings.enabled);
 clean();controller.core.automatic(true);button_up.state=true;up_press();poll();assert(controller.core.settings.manual==30);
 clean();controller.core.start_calibration(0);center_click();left_press();assert(oled.page==page_main&&controller.core.calibrating());
 for(int tick=1;tick<=35;tick++){
  clean();controller.core.manual(40,fan_core::Unit::PWM);controller.fan.state=true;button_up.state=true;
  ui.hold_ticks=tick-1;poll();
  int change=tick>30?5:tick>15?2:tick>5?(tick%2==0?1:0):tick>1?(tick%3==0?1:0):1;
  assert(controller.core.settings.manual==40+change);
 }
 puts("Pin/short-click/acceleration, OLED sleep/wake and reset gesture UI checks passed");
}
'''
with tempfile.TemporaryDirectory(prefix='native-ui-check-') as tmp:
    p=Path(tmp);(p/'test.cpp').write_text(src)
    subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'components/single_fan'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
