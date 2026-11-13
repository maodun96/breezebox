#include "../components/single_fan/core.h"
#include "../components/single_fan/ui.h"
#include <cassert>
#include <cmath>
#include <iostream>
using namespace fan_core;
static bool near(float a,float b){return std::fabs(a-b)<0.02f;}
static void sample(ControllerCore &c,uint32_t t,float r){c.sample_rpm(r,t);c.tick(t);}
static void scale_runtime(){
  assert(scale_to_output(20,0)==0 && scale_to_output(20,1)==20);
  assert(near(scale_to_output(20,50),59.59596f) && scale_to_output(20,100)==100);
  assert(output_to_scale(20,0)==0 && output_to_scale(20,20)==1);
  assert(near(output_to_scale(20,scale_to_output(20,50)),50));
  ControllerCore c;c.settings.enabled=true;c.settings.manual=50;c.settings.cal.minimum=20;
  c.tick(0);assert(near(c.output,59.59596f) && c.target==50 && c.display_percent()==50);
  c.settings.manual=30;c.tick(999);assert(c.output==50);
  c.tick(1000);assert(near(c.output,scale_to_output(20,30)));
  c.settings.manual=50;
  c.tick(2000);assert(near(c.output,59.59596f));
  c.settings.manual=100;c.tick(2100);assert(c.output==100);
  c.settings.manual=1;c.tick(2200);assert(c.output==20);
  c.settings.manual=0;c.tick(2300);assert(c.output==0);
  c.settings.manual=50;c.tick(2400);assert(near(c.output,59.59596f));
  c.enable(false);c.tick(2500);assert(c.output==0 && !c.rpm_fault);
}
static void stall(){
  ControllerCore c;c.settings.enabled=true;c.settings.manual=50;c.settings.cal.minimum=20;
  c.tick(0);c.tick(2000);
  for(unsigned i=1;i<=3;i++){uint32_t t=i*4000;c.tick(t);assert(near(c.output,59.59596f) && !c.rpm_fault);c.tick(t+1000);assert(near(c.output,59.59596f));}
  c.tick(16000);assert(c.rpm_fault && near(c.output,59.59596f));
  c.tick(75999);assert(near(c.output,59.59596f));c.tick(76000);assert(near(c.output,59.59596f));
  sample(c,76500,500);sample(c,77000,500);sample(c,77500,500);assert(!c.rpm_fault);
  ControllerCore low;low.settings.enabled=true;low.settings.manual=1;low.settings.cal.minimum=20;
  low.tick(0);low.tick(2000);
  for(uint32_t t=2500;t<=12500;t+=1000)sample(low,t,400);
  low.tick(16500);assert(low.output==50 && low.settings.cal.minimum==20);
  low.tick(17499);assert(low.output==50);low.tick(17500);assert(low.output==20);
  low.tick(18500);for(uint32_t t=19000;t<=29000;t+=1000)sample(low,t,400);
  low.tick(33000);assert(low.settings.cal.minimum==22 && low.settings.cal.auto_raised==2 && low.dirty);
}
static void rpm_open_loop(){
  ControllerCore c;c.settings.cal.valid=true;c.settings.cal.minimum=20;c.settings.cal.minimum_rpm=800;
  for(unsigned i=0;i<=50;i++)c.settings.cal.rpm_dense[i]=i*80;
  for(unsigned i=0;i<=10;i++)c.settings.cal.rpm[i]=i*400;
  assert(valid_settings(c.settings) && c.manual(2000,Unit::RPM));
  const float expected=to_pwm(c.settings.cal,c.settings.manual);
  c.tick(0);assert(c.output==50);
  for(uint32_t t=1000;t<=60000;t+=1000){sample(c,t,1700);if(t>=1000)assert(near(c.output,expected));}

  ControllerCore gap;gap.settings.cal.valid=true;gap.settings.cal.minimum=20;
  for(unsigned i=0;i<50;i++)gap.settings.cal.rpm_dense[i]=3000.0f*i/49;
  gap.settings.cal.rpm_dense[50]=3750;
  gap.settings.cal.minimum_rpm=gap.settings.cal.rpm_dense[10];
  for(unsigned i=0;i<=10;i++)gap.settings.cal.rpm[i]=gap.settings.cal.rpm_dense[i*5];
  assert(valid_settings(gap.settings) && gap.manual(3300,Unit::RPM));
  const float gap_output=to_pwm(gap.settings.cal,gap.settings.manual);
  assert(near(gap_output,98.8f));
  gap.tick(0);assert(near(gap.output,gap_output));
  for(uint32_t t=1000;t<=60000;t+=1000){sample(gap,t,3000);if(t>=1000)assert(near(gap.output,gap_output));}
}
struct Fan {float floor{20};bool twitch{},never_stop{},flat{},fail_verify{};unsigned n{};
  float read(const ControllerCore &c){++n;
    if(fail_verify && c.phase==ControllerCore::Phase::VERIFY && c.output<100)return 0;
    if(twitch && c.phase==ControllerCore::Phase::TABLE && c.output<floor)return n%3==0?0:n%3==1?30:60;
    if(!never_stop && c.output<floor)return 0;
    if(flat && c.output<=20)return 300;
    return c.output*20;
  }
};
struct SmoothFan {float read(const ControllerCore &c){return c.output*50;}};
template<class Model=Fan> static uint32_t calibrate(ControllerCore &c,Model fan={},uint32_t start=0){
  assert(c.start_calibration(start));
  for(uint32_t t=start+1000;t<start+600000;t+=1000){sample(c,t,fan.read(c));if(!c.calibrating())return t;}
  assert(false);return 0;
}
struct RecordedFan {Calibration table;float *verified_output{};
  float read(const ControllerCore &c){
    if(verified_output && c.phase==ControllerCore::Phase::VERIFY && c.output<100)*verified_output=c.output;
    return table_rpm(table,c.output);
  }
};
static void consecutive_calibrations(){
  RecordedFan case_fan,blower;
  const std::array<float,21> floor{{0,388,388,388,388,388,388,388,477,510,570,629,686,748,780,810,857,903,950,996,1043}};
  std::copy(floor.begin(),floor.end(),case_fan.table.rpm_dense.begin());
  for(unsigned i=21;i<=50;i++)case_fan.table.rpm_dense[i]=1043+(1974-1043)*(i-20)/30.0f;
  // The reported 40-90% plateau lost the raw values; use rising synthetic values with the observed 90% dip.
  blower.table.rpm={{0,210,779,1290,1710,2000,2250,2500,2800,1758,3054}};
  ControllerCore reused,fresh;
  auto t=calibrate(reused,case_fan);assert(reused.calibration_pending_save);reused.calibration_save_result(true);
  t=calibrate(reused,blower,t+1000);assert(reused.calibration_pending_save);
  auto blower_result=reused.settings.cal;reused.calibration_save_result(true);
  float verified=0;case_fan.verified_output=&verified;
  calibrate(reused,case_fan,t+1000);calibrate(fresh,case_fan,t+1000);
  assert(reused.calibration_pending_save && fresh.calibration_pending_save);
  const auto &a=reused.settings.cal,&b=fresh.settings.cal;
  assert(a.valid==b.valid && a.minimum==b.minimum && a.minimum_measured==b.minimum_measured);
  assert(a.minimum_rpm==b.minimum_rpm && a.maximum==b.maximum && a.auto_raised==b.auto_raised);
  assert(a.rpm_step==b.rpm_step && a.rpm==b.rpm && a.rpm_dense==b.rpm_dense);
  std::cout<<"case -> blower -> case equals fresh case calibration; minimum="<<a.minimum<<", blower 80%="<<blower_result.rpm[8]<<std::endl;
  assert(a.minimum_measured==2 && a.minimum==2 && verified==2 && a.minimum_rpm==388);
  assert(a.rpm_dense[50]==1974);
  for(unsigned i=0;i<floor.size();i++)assert(std::fabs(floor[i]-a.rpm_dense[i])<1);
  const std::array<float,11> expected{{0,210,779,1290,1710,2000,2250,2500,2800,2800,3054}};
  assert(blower_result.rpm==expected && valid_settings(reused.settings));
  assert(near(blower_result.rpm_dense[23],1884));
  ControllerCore overspeed;blower.table.rpm[8]=3400;calibrate(overspeed,blower);
  assert(overspeed.calibration_pending_save && overspeed.settings.cal.rpm[8]==3054 && overspeed.settings.cal.rpm[10]==3054);
}
struct TransientFan {RecordedFan fan;bool decay{},unstable{};float last_output{-1},state{};unsigned samples{};
  float read(const ControllerCore &c){
    if(c.output!=last_output){last_output=c.output;samples=0;}
    ++samples;float steady=fan.read(c);
    if(decay){state=steady+(state-steady)*std::exp(-0.5f);return state;}
    if(unstable)return steady+(samples%2?0:200);
    return samples<=2?steady*0.6f:steady;
  }
};
static void settling_calibration(){
  RecordedFan blower,case_fan;
  blower.table.rpm={{0,210,779,1290,1710,2000,2250,2500,2800,2930,3054}};
  for(unsigned i=1;i<=50;i++)case_fan.table.rpm_dense[i]=300+34*i;
  ControllerCore undershoot,decay,unstable;
  auto blower_time=calibrate(undershoot,TransientFan{blower});
  assert(blower_time<300000 && undershoot.calibration_pending_save && undershoot.settings.cal.rpm==blower.table.rpm);
  auto case_time=calibrate(decay,TransientFan{case_fan,true});
  assert(case_time<300000 && decay.calibration_pending_save && decay.settings.cal.minimum==2);
  assert(std::fabs(decay.settings.cal.minimum_rpm-334)<30);
  for(unsigned i=2;i<=15;i++)assert(decay.settings.cal.rpm_dense[i]>decay.settings.cal.rpm_dense[i-1]);
  auto unstable_time=calibrate(unstable,TransientFan{blower,false,true});
  assert(unstable_time==452000 && unstable.calibration_pending_save && valid_settings(unstable.settings));
  std::cout<<"settling: boost-fan undershoot="<<blower_time/1000<<"s, decay="<<case_time/1000
    <<"s, minimum_rpm="<<decay.settings.cal.minimum_rpm<<" (steady 334), unstable="<<unstable_time/1000<<"s\n";
  ControllerCore twitch;assert(twitch.start_calibration(0));
  uint32_t t=0;
  while(twitch.phase!=ControllerCore::Phase::TABLE || twitch.output!=18){t+=1000;sample(twitch,t,twitch.output*20);assert(t<180000);}
  sample(twitch,t+1000,30);assert(twitch.phase==ControllerCore::Phase::TABLE);
  sample(twitch,t+2000,0);assert(twitch.phase==ControllerCore::Phase::VERIFY);
  sample(twitch,t+4000,2000);assert(twitch.output==22);
  sample(twitch,t+4500,0);assert(twitch.cal_retry()==1 && twitch.output==100);
  std::cout<<"twitch stop="<<(t+2000)/1000<<"s, first retry="<<(t+4500)/1000.0f<<"s\n";
  ControllerCore gap;assert(gap.start_calibration(0));
  for(uint32_t at=1000;at<=4000;at+=1000)sample(gap,at,2000);
  for(uint32_t at=6000;at<=9000;at+=1000){sample(gap,at,2000);assert(gap.phase==ControllerCore::Phase::SIGNAL);}
  sample(gap,10000,2000);assert(gap.phase==ControllerCore::Phase::TABLE);
  ControllerCore timeout;assert(timeout.start_calibration(0));sample(timeout,600000,2000);
  assert(timeout.phase==ControllerCore::Phase::FAILED && std::string_view(timeout.cal_error)=="calibration_timeout");
}
struct WorstFan {float last_output{-1};unsigned samples{};
  float read(const ControllerCore &c){
    if(c.output!=last_output){last_output=c.output;samples=0;}
    ++samples;
    if(c.phase==ControllerCore::Phase::VERIFY && c.output<100)return samples%4==1?c.output*50:NAN;
    return c.output*50+(samples%2?0:400);
  }
};
static void dense_grid(){
  ControllerCore smooth;auto smooth_time=calibrate(smooth,SmoothFan{});
  assert(smooth.calibration_pending_save && valid_settings(smooth.settings));
  for(unsigned i=0;i<=50;i++)assert(std::fabs(smooth.settings.cal.rpm_dense[i]-i*100)<40);
  for(unsigned pwm:{94u,96u,86u,76u})assert(std::fabs(smooth.settings.cal.rpm_dense[pwm/2]-pwm*50)<40);
  ControllerCore stop;auto stop_time=calibrate(stop,Fan{33});
  assert(stop.calibration_pending_save && stop.settings.cal.minimum_measured==35 && stop.settings.cal.minimum==37);
  for(unsigned i=0;i<=15;i++)assert(stop.settings.cal.rpm_dense[i]==0);
  ControllerCore worst;auto worst_time=calibrate(worst,WorstFan{});
  assert(worst_time==486000 && worst_time<600000 && worst.cal_retry()==3 && worst.calibration_pending_save);
  std::cout<<"dense grid="<<smooth_time/1000<<"s, stop at 33%="<<stop_time/1000
    <<"s, all-unstable with three verify retries="<<worst_time/1000<<"s\n";
}
static void calibration(){
  ControllerCore c;auto t=calibrate(c);assert(t<180000 && c.calibration_pending_save);
  assert(c.settings.cal.valid && c.settings.cal.minimum_measured==20 && c.settings.cal.minimum==22);
  assert(c.settings.cal.rpm_step==2 && c.settings.cal.rpm_dense[10]>0 && c.settings.cal.rpm_dense[9]==0);
  assert(c.settings.cal.rpm[10]==c.settings.cal.rpm_dense[50] && valid_settings(c.settings));
  c.calibration_save_result(true);assert(!c.calibration_pending_save);
  c=ControllerCore{};calibrate(c,Fan{20,true});assert(c.settings.cal.valid && c.settings.cal.minimum==22);
  c=ControllerCore{};calibrate(c,Fan{2,false,true});assert(c.settings.cal.valid && c.settings.cal.minimum==2);
  c=ControllerCore{};calibrate(c,Fan{2,false,true,true});assert(c.settings.cal.minimum_measured==2 && c.settings.cal.minimum==2);
  c=ControllerCore{};t=calibrate(c,Fan{20,false,false,false,true});assert(c.settings.cal.valid && c.settings.cal.minimum==28);
  c.calibration_save_result(true);
  assert(c.start_calibration(t+1000));
  for(uint32_t at=t+2000;at<t+301000;at+=1000){
    sample(c,at,c.phase==ControllerCore::Phase::TABLE && c.output<9?0:300+17*c.output);
    if(!c.calibrating())break;
  }
  assert(c.calibration_pending_save && c.settings.cal.minimum==12);
  c=ControllerCore{};assert(c.start_calibration(0));for(uint32_t t=1000;t<=5000;t+=1000)sample(c,t,0);
  assert(c.phase==ControllerCore::Phase::FAILED && std::string_view(c.cal_error)=="no_rpm");
  c=ControllerCore{};c.sample_rpm(2000,99000);assert(c.start_calibration(100000));c.tick(104999);assert(c.calibrating());
  c.tick(105000);assert(c.phase==ControllerCore::Phase::FAILED && std::string_view(c.cal_error)=="no_rpm");
  c=ControllerCore{};assert(c.start_calibration(0));
  Fan fan;
  for(uint32_t at=1000;at<=30000;at+=1000)sample(c,at,fan.read(c));
  assert(c.phase==ControllerCore::Phase::TABLE);
  c.tick(34999);assert(c.calibrating());c.tick(35000);
  assert(c.phase==ControllerCore::Phase::FAILED && std::string_view(c.cal_error)=="no_rpm" && !c.calibration_pending_save);
  c=ControllerCore{};c.settings.cal.minimum=32;c.settings.manual=40;
  assert(c.start_calibration(0));sample(c,1000,2000);c.cancel();
  assert(c.phase==ControllerCore::Phase::IDLE && c.settings.cal.minimum==32 && c.settings.manual==40);
}
static void custom_preset(){
  ControllerCore c;
  assert(c.settings.custom==0 && c.settings.custom_unit==Unit::PWM && valid_settings(c.settings));
  assert(c.custom(35,Unit::PWM) && c.settings.custom==35 && c.settings.custom_unit==Unit::PWM);
  assert(c.settings.manual==30 && !c.settings.enabled && c.dirty && valid_settings(c.settings));
  c.dirty=false;
  assert(!c.custom(1200,Unit::RPM) && c.settings.custom==35 && !c.dirty);
  for(float invalid:{-1.0f,0.5f,101.0f,NAN})assert(!c.custom(invalid,Unit::PWM) && c.settings.custom==35);
  c.settings.cal.valid=true;c.settings.cal.minimum=20;c.settings.cal.minimum_rpm=300;
  c.settings.cal.rpm[10]=4000;c.settings.cal.rpm_dense[50]=4000;
  assert(c.custom(100,Unit::RPM) && c.settings.custom==300);
  assert(c.custom(5000,Unit::RPM) && c.settings.custom==4000 && valid_settings(c.settings));
  assert(!c.custom(100001,Unit::RPM) && c.settings.custom==4000);
  assert(c.custom(3500,Unit::RPM));
  assert(c.start_calibration(0));
  assert(!c.custom(35,Unit::PWM) && c.settings.custom==3500);
  c.cancel();
  calibrate(c);
  assert(c.settings.custom_unit==Unit::RPM && c.settings.custom==c.settings.cal.rpm[10]);
  assert(c.settings.custom==2000 && valid_settings(c.settings));
  c.settings.custom_unit=Unit::PWM;c.settings.custom=0.5f;assert(!valid_settings(c.settings));
  c.settings.custom=0;c.settings.custom_unit=Unit::RPM;c.settings.cal.valid=false;assert(!valid_settings(c.settings));
}
struct UIHost {
  int value=40; bool on=true,screen=true; int updates=0;
  void menu_timer(){} void screen_power(bool enabled){screen=enabled;}
  fan_ui::Page page(){return fan_ui::Page::MAIN;} bool automatic(){return false;} bool calibrating(){return false;}
  bool fan_on(){return on;} int speed(){return value;} void set_speed(int speed){value=speed;on=true;}
  void fan_off(){on=false;} void update(){++updates;}
};
static void ui_integration(){
  for(int tick=1;tick<=35;tick++) {
    int expected=tick>30?5:tick>15?2:tick>5?(tick%2==0?1:0):tick>1?(tick%3==0?1:0):1;
    assert(fan_ui::acceleration(tick)==expected);
  }
  fan_ui::UI ui;UIHost host;
  for(unsigned i=1;i<=31;i++)ui.poll(host,i*100,false,true,false,false,false);
  assert(host.value==82 && host.updates==23);
  ui.poll(host,33000,false,false,false,false,false);assert(ui.hold_ticks==0);
  ui.poll(host,63000,false,false,false,false,false);assert(!host.screen);
}
int main(){ui_integration();scale_runtime();stall();rpm_open_loop();consecutive_calibrations();settling_calibration();dense_grid();calibration();custom_preset();std::cout<<"core tests passed\n";}
