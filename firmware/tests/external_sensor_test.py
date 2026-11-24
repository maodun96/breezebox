"""Exercise the shipped bilingual sensor dialog and check its command wiring."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
page = (root / 'web/index.html').read_text()
helpers = page[page.index('const X='):page.index('const A={')]
spec = r'''
const assert=require('node:assert/strict');
let lang='zh', state={temperature:24.3,humidity:50.5,config:{sensor_source:0},ext_status:{supported:true,scanning:false,binding:false,scan_id:0,scan_end_reason:'',scan_results:[]}},
 commandsPending=0,dl={external:true},online=true,html='',toasts=[],closed=0;
const live=()=>online,esc=String,t=k=>k,ic=()=>'',opt=(l,a,b,v,s)=>l+s,
 bn=(k,i,b,s)=>k+':'+b+s,toast=(m,e,d)=>toasts.push([m,e,d]),setH=(_,s)=>html=s,
 $=()=>({querySelectorAll:()=>[]}),dlg=o=>dl=o,closeDlg=()=>{dl=null;closed++;},
 send=()=>Promise.resolve(true);
'''
checks = r'''
assert.equal(extRow().includes('内置传感器'),true);
state.ext_status.supported=false;assert.equal(extRow(),'');
state.ext_status.supported=1;assert.equal(extRow(),'');
state.ext_status.supported='true';assert.equal(extRow(),'');
state.ext_status.supported=true;
renderExt();assert(html.includes('未绑定，请先在下方搜索添加')&&!html.includes('未发现支持'));

// Stale completed scan on fresh open must NOT show empty hint.
const x=state.ext_status,c=state.config;
x.scan_id=2;x.scan_end_reason='completed';x.scan_results=[];x.bind_error='timeout';
openExt();assert(!html.includes('未发现支持')&&!html.includes('连接超时'));

// Observing scanning=true then natural completed -> shows empty hint; new scanning=true clears it.
x.scanning=true;x.scan_id=3;x.scan_end_reason='';renderExt();
assert(!html.includes('未发现支持'));
x.scanning=false;x.scan_end_reason='completed';renderExt();
assert(html.includes('未发现支持的传感器'));
x.scanning=true;x.scan_id=4;x.scan_end_reason='';renderExt();
assert(!html.includes('未发现支持'));
// Early stop (scan_end_reason === 'stopped') must NOT show empty hint.
x.scanning=false;x.scan_end_reason='stopped';renderExt();
assert(!html.includes('未发现支持'));

// Stopped by this client suppresses empty hint even if reason were completed.
x.scanning=true;x.scan_id=5;x.scan_end_reason='';renderExt();
extUI.stoppedByThisClient=true;x.scanning=false;x.scan_end_reason='completed';renderExt();
assert(!html.includes('未发现支持'));

// Bound state, ok subtitle (null battery -> '--', never '--%'; half-up humidity 50.5 -> 51%).
c.ext_sensor={driver:'lywsd03mmc',mac:' a4:c1:38:46:6b:6f '};
c.sensor_source=1;x.state='ok';x.battery_pct=null;x.age_s=12;x.bind_error='';
openExt();
assert(html.includes('24.3°C · 51% · 电量 -- · 12秒前')&&!html.includes('--%'));
assert(html.includes('A4:C1:38:46:6B:6F'));
lang='en';renderExt();
assert(html.includes('24.3°C · 51% · Battery -- · 12s ago')&&!html.includes('--%'));

// Blank MAC / unknown model fall back to '--'.
c.ext_sensor={driver:'unknown',mac:'   ',name:'   '};renderExt();
assert(html.includes('>--<'));

// Built-in selected: paired tail shown, low battery warning suppressed.
lang='zh';c.sensor_source=0;c.ext_sensor={driver:'lywsd03mmc',mac:'A4:C1:38:46:6B:6F'};
x.battery_pct=20;x.state='lost';renderExt();
assert(html.includes('已绑定 · 尾号 6B:6F')&&!html.includes('请尽快更换'));

// Lost banner switches copy by enabled && automatic and uses danger ('err') style.
c.sensor_source=1;c.enabled=false;c.automatic=true;renderExt();
assert(html.includes('err:外置传感器已失联超过 3 分钟')&&html.includes('开启自动模式时将满速')&&!html.includes('自动模式已满速 100%'));
c.enabled=true;c.automatic=true;renderExt();
assert(html.includes('自动模式已满速 100%'));
lang='en';renderExt();assert(html.includes('Auto mode is running at 100% for safety.'));
x.state='stale';x.age_s=66;renderExt();assert(html.includes('Weak signal (66s ago)'));

// Signal strength thresholds.
assert.equal(signal(-65),'Strong');assert.equal(signal(-66),'Fair');assert.equal(signal(-80),'Fair');assert.equal(signal(-81),'Weak');

// Error mapping for all 5 bind_error codes, ble_busy, HTTP 400 fallback, and non-400 network fallback.
for(const code of ['ble_busy','save_failed','connect_failed','unsupported','timeout'])
 assert.equal(extError({ext_status:{bind_error:code}},400),code);
assert.equal(extError({ext_status:{bind_error:'busy'}},400),'busy');
assert.equal(extError({error:'ble_busy'},400),'ble_busy');
assert.equal(extError({},400),'busy');
assert.equal(extError({},503),'network');

// Binding progress + 2500ms success toast.
lang='zh';x.binding=true;extUI.target='A4:C1:38:46:6B:6F';extUI.bindPending=false;renderExt();
assert(html.includes('正在连接并验证传感器（约需 5~10 秒）'));
x.binding=false;x.bind_error='';renderExt();
assert.deepEqual(toasts.at(-1),['已绑定并切换为外置传感器',false,2500]);

// Binding error observed across true -> false transition displays error.
x.binding=true;renderExt();
x.binding=false;x.bind_error='connect_failed';renderExt();
assert(html.includes('蓝牙连接失败'));

// Auto-close dialog when supported becomes false.
x.supported=false;renderExt();assert.equal(closed,1);
'''
subprocess.run(['node','-e',spec+helpers+checks],check=True)
hub = (root/'components/single_fan/ble_sensor_hub.cpp').read_text()
for op in ['ext_bind','ext_scan_start','ext_scan_stop','ext_source','ext_unbind']:
    assert op in hub and op in page
for key in ['"scan_id"', '"scan_end_reason"', '"completed"', '"stopped"']:
    assert key in hub, key
assert 'class="ext-tag"' in page
assert "bn('err','alert',t('tempFault'),t('tempFaultS'))" in page
print('PASS external sensor dialog, scan_end_reason, bilingual errors, signal thresholds and command wiring')
