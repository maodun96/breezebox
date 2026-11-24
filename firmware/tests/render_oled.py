"""Run the actual OLED draw() against a trace display and render its compiled 1-bit font."""
import argparse, json, re, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('generated_main',type=Path)
parser.add_argument('--out',type=Path,default=ROOT.parent/'preview/oled')
args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
main=args.generated_main.read_text()
bitmap=bytes(int(v,16) for v in re.search(r'uint8_t_id\[\] PROGMEM = \{([^}]+)',main)[1].split(',') if v.strip())
glyphs={int(c):tuple(map(int,(offset,advance,x,y,w,h))) for c,offset,advance,x,y,w,h in re.findall(r'\{(\d+), \(uint8_t_id \+ (\d+)\), (\d+), (-?\d+), (-?\d+), (\d+), (\d+)\}',main)}
body=(ROOT/'components/single_fan/single_fan.cpp').read_text().split('void Controller::draw(unsigned page) {',1)[1].rsplit('}',1)[0]
harness=r'''
#include "core.h"
#include <iostream>
#include <cstdio>
#include <cstring>
uint32_t millis(){return 400;}
namespace display {enum class TextAlign {TOP_RIGHT};}
namespace improv {enum State {STATE_PROVISIONING, STATE_AUTHORIZED};}
namespace improv_ble {struct Component {improv::State get_improv_state(){return improv::STATE_AUTHORIZED;}};
Component instance;Component *global_improv_component=&instance;}
namespace network {constexpr int IP_ADDRESS_BUFFER_SIZE=64;}
namespace wifi {
struct IP {const char* str_to(char *b){std::strcpy(b,"192.168.10.193");return b;}};
struct WiFi {bool connected=true,ap=false;bool is_connected(){return connected;}bool is_ap_active(){return ap;}std::array<IP,1> get_ip_addresses(){return {};} IP wifi_soft_ap_ip(){return {};}};
WiFi instance;WiFi* global_wifi_component=&instance;
}
struct Display {
void clear(){}
void print(int x,int y,int*,const char*s){std::cout<<"T|"<<x<<"|"<<y<<"|0|"<<s<<"\n";}
void print(int x,int y,int*,display::TextAlign,const char*s){std::cout<<"T|"<<x<<"|"<<y<<"|1|"<<s<<"\n";}
template<class... A> void printf(int x,int y,int*f,const char*fmt,A...a){char s[160];std::snprintf(s,sizeof(s),fmt,a...);print(x,y,f,s);}
template<class... A> void printf(int x,int y,int*f,display::TextAlign align,const char*fmt,A...a){char s[160];std::snprintf(s,sizeof(s),fmt,a...);print(x,y,f,align,s);}
void line(int a,int b,int c,int d){std::cout<<"L|"<<a<<"|"<<b<<"|"<<c<<"|"<<d<<"\n";}
void rectangle(int a,int b,int c,int d){std::cout<<"R|"<<a<<"|"<<b<<"|"<<c<<"|"<<d<<"\n";}
void filled_rectangle(int a,int b,int c,int d){std::cout<<"F|"<<a<<"|"<<b<<"|"<<c<<"|"<<d<<"\n";}
void circle(int a,int b,int c){std::cout<<"C|"<<a<<"|"<<b<<"|"<<c<<"\n";}
void filled_circle(int a,int b,int c){std::cout<<"D|"<<a<<"|"<<b<<"|"<<c<<"\n";}
};
struct Controller {using ControllerCore=fan_core::ControllerCore;ControllerCore core;Display screen;Display *screen_=&screen;int font=0;int *font_=&font;void draw(unsigned page);};
void Controller::draw(unsigned page) {
'''+body+r'''
int main(){
for(int i=0;i<16;i++){
 Controller c;unsigned page=0;auto &s=c.core;c.core.temperature=39.5;c.core.humidity=31;c.core.rpm=1200;c.core.output=50;c.core.target=50;c.core.settings.manual=50;c.core.settings.enabled=true;
 wifi::instance.connected=true;wifi::instance.ap=false;
 switch(i){
 case 1:s.settings.automatic=true;break;
 case 2:s.settings.automatic=true;s.output=0;s.target=0;s.rpm=0;break;
 case 3:s.settings.enabled=false;s.output=0;s.target=0;s.rpm=0;break;
 case 4:page=1;break;
 case 5:page=1;s.settings.automatic=true;break;
 case 6:page=2;break;
 case 7:page=2;wifi::instance.connected=false;wifi::instance.ap=true;break;
 case 8:page=2;wifi::instance.connected=false;break;
 case 9:page=3;break;
 case 10:page=4;break;
 case 11:s.phase=Controller::ControllerCore::Phase::TABLE;break;
 case 12:s.phase=Controller::ControllerCore::Phase::FAILED;break;
 case 13:s.temp_fault=true;s.settings.automatic=true;s.output=100;s.target=100;break;
 case 14:s.rpm_fault=true;s.rpm=NAN;break;
 case 15:s.config_fault=true;s.settings.enabled=false;s.output=0;s.target=0;s.rpm=0;break;
 }
 std::cout<<"SCREEN|"<<i<<"\n";c.draw(page);
}
}
'''
with tempfile.TemporaryDirectory(prefix='oled-render-') as tmp:
    cpp=Path(tmp)/'draw.cpp';exe=Path(tmp)/'draw';cpp.write_text(harness)
    subprocess.run(['clang++','-std=c++17','-I',str(ROOT/'components/single_fan'),str(cpp),'-o',str(exe)],check=True)
    trace=subprocess.check_output([str(exe)],text=True)

def text(image,x,y,right,value):
    entries=[glyphs[ord(c)] for c in value]
    if right:x-=sum(g[1] for g in entries)
    for offset,advance,dx,dy,w,h in entries:
        for yy in range(h):
            for xx in range(w):
                bit=yy*w+xx;px=x+dx+xx;py=y+dy+yy
                if bitmap[offset+bit//8] & (128>>(bit%8)) and 0<=px<128 and 0<=py<32:image.putpixel((px,py),255)
        x+=advance

def circle(draw,x,y,r,filled):
    # Same midpoint algorithm as ESPHome's display primitives.
    dx=-r;dy=0;err=2-2*r
    while True:
        for px,py in [(x-dx,y+dy),(x+dx,y+dy),(x+dx,y-dy),(x-dx,y-dy)]:draw.point((px,py),fill=255)
        if filled:
            draw.line((x+dx,y+dy,x-dx,y+dy),fill=255);draw.line((x+dx,y-dy,x-dx,y-dy),fill=255)
        e2=err
        if e2<dy:
            dy+=1;err+=dy*2+1
            if -dx==dy and e2<=dx:e2=0
        if e2>dx:dx+=1;err+=dx*2+1
        if dx>0:break

screens=[]
for line in trace.splitlines():
    parts=line.split('|');op=parts[0]
    if op=='SCREEN':
        image=Image.new('L',(128,32));draw=ImageDraw.Draw(image);screens.append(image);continue
    if op=='T':text(image,int(parts[1]),int(parts[2]),int(parts[3]),parts[4]);continue
    v=list(map(int,parts[1:]))
    if op=='L':draw.line(v,fill=255)
    elif op in ('R','F'):
        x,y,w,h=v
        if w>0 and h>0:draw.rectangle((x,y,x+w-1,y+h-1),outline=255,fill=255 if op=='F' else None)
    else:circle(draw,*v,op=='D')
labels=['主页 · 手动运行','主页 · 自动运行','主页 · 自动输出0%','主页 · 用户关闭','控制模式 · 手动','控制模式 · 自动','网络信息 · 已连接','网络信息 · 配网热点（无密码）','网络信息 · 连接中','恢复出厂 · 入口','恢复出厂 · 二次确认','校准中','校准结束后主页','温度失联 · 自动满速','转速反馈异常','配置错误 · 保持关闭']
font=ImageFont.truetype(str(ROOT/'fonts/NotoSansSC-Regular.otf'),18)
board=Image.new('RGB',(1100,8*190+80),'#121b28');bd=ImageDraw.Draw(board)
bd.text((22,10),'OLED 页面预览 · 128×32 像素放大4倍',font=font,fill='white')
bd.text((22,38),'实际绘制代码和固件字库生成；示例数据，非实物拍摄。',font=font,fill='#b3c2d4')
cards=[]
for i,(img,label) in enumerate(zip(screens,labels)):
    name=f'{i:02d}.png';img.save(args.out/name)
    x=22+(i%2)*550;y=85+(i//2)*190
    bd.text((x,y),label,font=font,fill='#c9d9eb')
    board.paste(img.resize((512,128),Image.Resampling.NEAREST).convert('RGB'),(x,y+32))
    cards.append(f'<article><h2>{label}</h2><img src="{name}" alt="{label}"></article>')
board.save(args.out/'overview.png')
(args.out/'index.html').write_text('''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OLED 各页面预览</title><style>body{margin:24px;background:#121b28;color:#ecf3fc;font:16px system-ui}h1{font-size:24px}h2{font-size:17px}p{color:#b3c2d4}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:24px;max-width:1100px}img{width:100%;max-width:512px;image-rendering:pixelated;border:8px solid #293545;border-radius:5px}article{min-width:0}</style><h1>小屏幕各页面</h1><p>128×32 像素，来自当前绘制代码与编译字库。示例数据，非实物拍摄。</p><p>左右翻页：主页 → 控制模式 → 网络信息 → 恢复出厂。普通页面10秒无操作返回主页。</p><div class="grid">'''+''.join(cards)+'</div>')
print(args.out/'overview.png')
