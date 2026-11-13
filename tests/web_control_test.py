"""Check the shipped control queue and calibrated low-speed conversion."""
from pathlib import Path
import json
import re
import subprocess

page = (Path(__file__).parents[1] / 'web/index.html').read_text()
assert 'id="setManual"' not in page
assert 'id="automatic"' not in page
# Power is a single button; the dial commits one manual command when released.
assert 'id="pwr" data-a="power"' in page
assert "power:()=>{if(live())send({op:'enable',value:!state.config.enabled})}" in page
assert 'const end=()=>{if(!dragging)return;dragging=false;applyManual()}' in page
# Switching manual/auto never changes the power switch.
assert 'if(a===c.automatic)return;' in page
assert not re.search(r"op:'auto',value:a\}\)[^;]*op:'enable'", page)
# A dropped connection after a sent OTA upload is reported as unconfirmed, never as success.
assert "sent?(uploading=false,dl&&(dl.lock=false),closeDlg(true),beginReboot('unconfirmed'))" in page
assert 'xhr.status===200&&/Successful/.test(xhr.responseText)' in page
assert 'stopHold=()=>{' in page and 'if(hDirty===1)applyManual()' in page
assert 'grid-template-columns:repeat(4,1fr)' in page and "data-a=\"custom\"" in page
assert "custom:()=>{if(customHeld){customHeld=false;return}" in page
assert "send({op:'manual',value:c.custom,unit:c.custom_unit})" in page
assert "send({op:'custom',value:save?manual.value:0,unit:save?effUnit():0})" in page
assert "toast(t('customHint'))" in page and "toast(t('customOff'))" in page and "toast(t(save?'customSaved':'customCleared'))" in page
assert '},600)' in page and '.pre[data-a=custom]{-webkit-touch-callout:none;user-select:none}' in page
assert 'customCleared:\'已清除自定义|Custom cleared\'' in page
hold = next(line for line in page.splitlines() if line.startswith("document.addEventListener('pointerdown',e=>{if(e.button!==0||!e.target.closest('[data-a=custom]'))"))
subprocess.run(['node', '-e', 'const assert=require("node:assert/strict");\n' +
    'let handler,timer,on=false,state={config:{custom:0}},manual={value:0,unit:0},calls=[],toasts=[];\n' +
    'const document={addEventListener:(_,fn)=>handler=fn},setTimeout=(fn,ms)=>{assert.equal(ms,600);timer=fn},busyGuard=()=>false,enabledNow=()=>on,effUnit=()=>manual.unit,t=k=>k,toast=k=>toasts.push(k),send=c=>{calls.push(c);state.config.custom=c.value;return Promise.resolve(true)};\n' +
    'eval(' + json.dumps(hold) + ');\n' +
    '(async()=>{const press=async()=>{handler({button:0,target:{closest:()=>true}});timer();await Promise.resolve()};\n' +
    'on=true;manual={value:35,unit:1};await press();assert.deepEqual(calls.pop(),{op:"custom",value:35,unit:1});assert.equal(toasts.pop(),"customSaved");\n' +
    'on=false;await press();assert.deepEqual(calls.pop(),{op:"custom",value:0,unit:0});assert.equal(toasts.pop(),"customCleared");assert.equal(state.config.custom,0);\n' +
    'await press();assert.equal(calls.length,0);assert.equal(toasts.pop(),"customOff");\n' +
    'on=true;manual.value=0;state.config.custom=35;await press();assert.deepEqual(calls.pop(),{op:"custom",value:0,unit:0});assert.equal(toasts.pop(),"customCleared")})().catch(e=>{console.error(e);process.exitCode=1});'], check=True)
assert 'if(first&&(Math.hypot(dx,dy)<95||Math.hypot(dx,dy)>170))return false' in page
assert 'touchstart' in page and '{passive:false}' in page and 'touch-action:none' not in re.search(r'^\.dial-wrap\{.*$',page,re.M).group()
assert '.livechips{display:grid;grid-template-columns:repeat(2,max-content);justify-content:center;gap:6px;margin-bottom:14px}' in page
assert '.dial-wrap{position:relative;width:420px;height:420px;flex:none;transition:opacity .3s}' in page
assert '.dial-wrap{width:336px;height:336px;zoom:calc(clamp(220px,calc(100svh - 348px - env(safe-area-inset-bottom)),336px)/336px)}' in page
assert '--dial-unit' not in page
assert 'function dUnit(){return state.calibrating||!valid()?0:!enabledNow()?ui.unit:manualMode()?manual.unit:ui.unit}' in page
assert "txt=t('fanOff');sub=valid()?`<b>0</b> ${u?'RPM':'%'}${ic('swap',14)}`:t('calPending')" in page
assert "if(!state.config.enabled){ui.unit=ui.unit?0:1;dkey='';paint();return}" in page
assert "calPending:'待校准|Not calibrated'" in page
assert 'offHint:' not in page
# No prototype harness or simulation may ship in the firmware page.
for banned in ('demoBtn', 'PROTOTYPE', 'Math.random', 'dSet(', 'simulated device'):
    assert banned not in page, banned
# Every displayed value must come from the device; commands go through send().
assert page.count("fetch(") == 1 and "fetch('/control'" in page
helpers = '\n'.join(re.search(r'function ' + name + r'\(.*?(?=\nfunction |\n\$|\nconst |\n\[)', page, re.S).group()
                    for name in ('send', 'syncManual', 'scaleToOutput', 'outputToScale', 'rpmFor', 'pwmFor', 'applyManual'))
helpers += '\n' + '\n'.join(re.search(r'^const ' + name + r'=.*$', page, re.M).group() for name in ('valid', 'effUnit'))
assert 'belowMin' not in page and 'g-min' not in page
assert 'color:var(--accent);background:color-mix(in srgb,var(--accent) 16%,transparent)' in page
assert '.danger .ri{color:var(--danger)' in page and '--c:' not in page
subprocess.run(['node', '-e', 'const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));\n' + helpers + r'''
const assert=require('node:assert/strict');
let resetRequested=false,commandEpoch=0,commandsPending=0,commandQueue=Promise.resolve(),manualRevision=1,manualDirty=true;
const state={config:{cal:{valid:true,minimum:20,minimum_measured:18,minimum_rpm:500,maximum:100,auto_raised:0,rpm_step:2,rpm_dense:Array.from({length:51},(_,i)=>i*20),rpm:[0,200,400,600,800,1000,1200,1400,1600,1800,2000]}}};
const manual={unit:0,value:3};
const t=k=>k,toasts=[],toast=(m,e)=>{toasts.push([m,e])};
let calls=[],renders=[],active=0,maxActive=0,paints=0,failNext=false;
const render=s=>renders.push(s),paint=()=>paints++;
async function request(payload){active++;maxActive=Math.max(maxActive,active);calls.push(payload);await new Promise(resolve=>setTimeout(resolve,5));active--;if(failNext){failNext=false;throw Error('boom');}return payload;}
(async()=>{
 const a=send({op:'auto',value:true}),b=send({op:'auto',value:false});
 await Promise.all([a,b]);assert.equal(maxActive,1);assert.equal(commandsPending,0);
 assert.deepEqual(renders,[{op:'auto',value:false}]);
 const pendingManual=applyManual();manualRevision++;await pendingManual;assert.equal(manualDirty,true); // newer edit stays dirty
 await applyManual();assert.equal(manualDirty,false);
 assert.deepEqual(calls.at(-1),{op:'manual',unit:0,value:3});
 // Invalid or uncalibrated RPM values never reach the device.
 const before=calls.length;manual.value=101;assert.equal(await applyManual(),undefined);manual.value=3;
 manual.unit=1;manual.value=1200;state.config.cal.valid=false;assert.equal(await applyManual(),undefined);
 assert.equal(calls.length,before);assert.deepEqual(toasts.at(-1),['rejected',true]);
 state.config.cal.valid=true;assert.equal(effUnit(),1);await applyManual();assert.deepEqual(calls.at(-1),{op:'manual',unit:1,value:1200});
 // A failed command drops the local edit so the dial returns to the device value.
 state.config.manual_unit=0;state.config.manual=3;manual.unit=0;manual.value=40;manualDirty=true;failNext=true;
 assert.equal(await applyManual(),false);assert.equal(manualDirty,false);assert.deepEqual(manual,{unit:0,value:3});
 // Polling may only overwrite the local value while no edit is pending.
 manualDirty=true;manual.value=77;syncManual({config:{manual_unit:1,manual:1200}});assert.deepEqual(manual,{unit:0,value:77});
 manualDirty=false;syncManual({config:{manual_unit:1,manual:1200}});assert.deepEqual(manual,{unit:1,value:1200});
 manual.unit=0;manual.value=3;
 assert.equal(scaleToOutput(20,0),0);assert.equal(scaleToOutput(20,1),20);
 assert.ok(Math.abs(scaleToOutput(20,50)-59.6)<.01);assert.equal(scaleToOutput(20,100),100);
 assert.equal(outputToScale(20,0),0);assert.equal(outputToScale(20,20),1);
 assert.ok(Math.abs(outputToScale(20,scaleToOutput(20,50))-50)<1e-9);
 assert.equal(outputToScale(20,100),100);
 assert.equal(rpmFor(0),0);assert.equal(rpmFor(1),500);
 assert.ok(rpmFor(50)>500);assert.equal(rpmFor(100),1000);
 assert.equal(pwmFor(0),0);assert.equal(pwmFor(500),1);
 assert.ok(Math.abs(pwmFor(rpmFor(50))-50)<1e-9);
 assert.equal(pwmFor(1000),100);
 state.config.cal.valid=false;assert.equal(rpmFor(1),0);
 console.log('Web mode queue, slider acknowledgement and scale/RPM checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''], check=True)

# Notifications use one live toast plus a banner area; neither may be wired to the draft loader.
assert '<div id="toast" role="status" aria-live="polite"></div>' in page and '<div id="banners" role="status"></div>' in page
assert "toast(" not in re.search(r'^function loadDraft.*$', page, re.M).group()
notice_function = re.search(r'^function toast\(.*$', page, re.M).group()
subprocess.run(['node', '-e', notice_function + r'''
const assert=require('node:assert/strict');
let toastTimer,nextTimer=0;
const timers=new Map(),notice={textContent:'',className:''};
const $=()=>notice;
const setTimeout=(callback,delay)=>{timers.set(++nextTimer,{callback,delay});return nextTimer;};
const clearTimeout=id=>timers.delete(id);
toast('已保存');assert.equal(notice.textContent,'已保存');assert.equal(notice.className,'show');assert.equal(timers.get(toastTimer).delay,2400);
const first=toastTimer;
toast('保存失败',true);assert.equal(timers.has(first),false);assert.equal(notice.className,'show err');
assert.equal(timers.get(toastTimer).delay,6000);
timers.get(toastTimer).callback();assert.equal(notice.className,'');
toast('再次保存');toast('');assert.equal(timers.has(toastTimer),false);assert.equal(notice.className,'');
console.log('Toast replacement and automatic dismissal checks passed');
'''], check=True)

# Exercise the shipped destructive-action handler without touching a device.
reset_handler = re.search(r'async function requestFactoryReset\(\)\{.*?\n\}', page, re.S).group()
subprocess.run(['node', '-e', reset_handler + r'''
const assert=require('node:assert/strict');
let online=true,state={calibrating:false,mac:'AA:BB:CC:DD:EE:FF'},commandsPending=0,resetRequested=false,commandEpoch=0;
let resetNote='',paints=0,toasts=[];
const t=k=>k,paint=()=>paints++,toast=(m,e)=>{toasts.push([m,e])};
let confirmed=false,confirmationCount=0,calls=[];
const ask=async()=>{confirmationCount++;return confirmed};
let request=async payload=>{calls.push(payload);return {reset_pending:true}};
(async()=>{
 await requestFactoryReset();assert.equal(calls.length,0);assert.equal(resetRequested,false); // Cancel.
 confirmed=true;
 for(const blocked of ['offline','calibration','pending']) {
  online=blocked!=='offline';state.calibrating=blocked==='calibration';commandsPending=blocked==='pending'?1:0;
  const n=confirmationCount;await requestFactoryReset();assert.equal(confirmationCount,n);assert.equal(calls.length,0);
 }
 online=true;state.calibrating=false;commandsPending=0;
 await requestFactoryReset();assert.deepEqual(calls,[{op:'factory_reset',confirm:state.mac}]);
 assert.equal(commandsPending,0);assert.equal(resetRequested,true);assert.equal(resetNote,'resetAccepted'); // Page locks itself via resetRequested.
 await requestFactoryReset();assert.equal(calls.length,1); // No repeated submission.
 resetRequested=false;request=async()=>{throw Error('lost reply')};
 await requestFactoryReset();assert.equal(resetNote,'resetUncertain');assert.equal(commandsPending,0);assert.deepEqual(toasts.at(-1),['resetUncertain',true]);
 assert.equal(resetRequested,false); // No silent retry / false success.
 console.log('Factory reset: cancel, disabled states, identity confirmation, single submit and unknown-result handling passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''], check=True)
cpp = (Path(__file__).parents[1] / 'components/single_fan/single_fan.cpp').read_text()
command = re.sub(r'\s+', '', cpp.split('bool Controller::command(JsonObject o) {', 1)[1].split('bool Controller::canHandle', 1)[0])
assert command.index('if(core.calibrating())returnfalse;') < command.index('if(op=="factory_reset")')
reset_command = command.split('if(op=="factory_reset"){', 1)[1].split('if(op=="rename")', 1)[0]
assert 'o["confirm"].is<constchar*>()' in reset_command and 'get_mac_address_pretty_into_buffer(mac)' in reset_command
assert re.search(r'set_timeout\("factory_reset",1500,\[this\]\{factory_reset\(\);\}\);', reset_command)
assert 'if(reset_pending_)returnfalse;' in command

banner = page.split('function banners(){')[1].split('/* ---- dial ---- */')[0]
subprocess.run(['node','-e',r'''
const assert=require('node:assert/strict');let html='';
const resetRequested=false,online=true,ui={tab:'run'},state={calibrating:false,cal_error:''};
let calibrated=false;const valid=()=>calibrated,t=x=>x,bn=(...x)=>x.join(' '),$=x=>x==='banners'?{}:null,setH=(el,h)=>{html=h};
function banners(){''' + banner + r'''
for(const tab of ['run','curve','cal']){ui.tab=tab;banners();assert(html.includes('calSuggest'));}
calibrated=true;banners();assert(!html.includes('calSuggest'));
console.log('PASS calibration suggestion remains visible on calibration tab, clears when valid');
'''],check=True)
