"""Small regression check against the actual webpage helpers."""
from pathlib import Path
import re, subprocess
s= (Path(__file__).parents[1]/'web/index.html').read_text()
helpers=[]
for name in ('curveOrdered','insertPoint','displayCalRpm','curveError','moveNode','curveAt'):
    helpers.append(re.search(r'function '+name+r'\(.*?(?=\nfunction |\n\$|\nconst )',s,re.S).group())
subprocess.run(['node','-e','const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));\n'+'\n'.join(helpers)+"""
const assert=require('node:assert/strict');
assert.equal(curveOrdered([[30,60],[40,50]]),false);
assert.equal(curveOrdered([[30,50],[40,50]]),true);
assert.deepEqual(insertPoint([[30,0],[40,50],[50,100]]),[[30,0],[35,25],[40,50],[50,100]]);
assert.equal(insertPoint([[30,0],[31,50]]),null);
assert.equal(insertPoint([[30,60],[40,50]]),null);
assert.equal(insertPoint([[30.5,0],[40,50]]),null);
assert.equal(curveError([[30,NaN],[40,50]],100),'invalid');
assert.equal(curveError([[30,0],[30,50]],100),'invalid');
assert.equal(curveError([[51,0],[40,50]],100),'invalid');
assert.equal(curveError([[30,101],[40,100]],100),'invalid');
assert.equal(curveError([[30,60],[40,50]],100),'descending');
assert.equal(curveError([[30,0],[40,50]],100),'');
assert.equal(curveError([[30,0],[40,2451]],2450),'invalid');
assert.equal(displayCalRpm(1040),1050);
assert.equal(displayCalRpm(2040,true),2000);
assert.equal(displayCalRpm(1050),1050);
// Dragging a node can neither cross its neighbours nor leave 0-50 C / 0-100 %.
let pts=[[25,20],[32,35],[40,60],[46,100]];
moveNode(pts,1,60,0);assert.deepEqual(pts[1],[39,20]);moveNode(pts,1,-5,100);assert.deepEqual(pts[1],[26,60]);
moveNode(pts,0,-9,-9);assert.deepEqual(pts[0],[0,0]);moveNode(pts,3,99,0);assert.deepEqual(pts[3],[50,60]);
assert.equal(curveError(pts,100),'');
assert.equal(curveAt([[25,20],[40,60]],10),20);assert.equal(curveAt([[25,20],[40,60]],32.5),40);assert.equal(curveAt([[25,20],[40,60]],99),60);
console.log('Web curve and calibration display checks passed');
"""],check=True)

s_web=s
# Exercise the actual stage/failure formatter and require translations for every firmware stage/error.
words=re.search(r"/\* i18n: .*?/\* end i18n \*/",s_web,re.S).group()
formatter=re.search(r"function calibrationText\(.*?\n\}\n",s_web,re.S).group()
assert "const STAGES=['signal','rpm_table','verify','saving']" in s_web
assert 'belowMin' not in s_web and 'g-min' not in s_web
assert '<div class="card" id="calRes"></div><p class="note" data-t="pctNote"></p>' in s_web
for key in ('howCal', 'calHelp', 'calRounding'):
    assert key not in s_web
subprocess.run(['node','-e',words+"\n"+formatter+"\n"+"""
const assert=require('node:assert/strict');
let lang='zh';const t=k=>words[lang][k]||k;
for(const [k,v] of Object.entries(W))assert.equal(v.split('|').length,2,`one zh|en pair: ${k}`);
for(const k of ['invalid','descending','resetFailed','updateFailed','offline','rejected','needCal','busy','noRoom'])assert.ok(words.zh[k]&&words.en[k],k);
const labels={signal:['检查转速信号','Checking speed signal'],rpm_table:['测量转速表','Measuring RPM table'],verify:['复核最低档','Verifying minimum'],saving:['保存结果','Saving'],no_rpm:['没有转速信号，请检查接线','No speed signal. Check the wiring.'],save_failed:['保存失败，请重试','Save failed. Try again.'],calibration_timeout:['校准超时，请重试','Calibration timed out. Try again.'],invalid_calibration:['校准结果无效，已保留原设置','Invalid result. Previous settings kept.']};
for(const [k,[zh,en]] of Object.entries(labels)){assert.equal(words.zh[k],zh);assert.equal(words.en[k],en)}
for(const [k,zh,en] of [['custom','自定义','Custom'],['customUnset','未设置','Not set'],['customHint','先调好转速，再长按这里保存','Set a speed first, then press and hold here to save'],['customOff','先开启风扇并调好转速','Turn the fan on and set a speed first'],['customSaved','已存为自定义','Saved as custom']]){assert.equal(words.zh[k],zh);assert.equal(words.en[k],en)}
assert.equal(words.zh.pctNote,'百分比说明：控制和曲线里的百分比是换算后的档位，0% 关，1% 对应风扇最低稳转档，100% 满速；校准结果里的百分比是实际输出给风扇的 PWM 占空比。');
assert.equal(words.en.pctNote,'About percentages: percentages in control and curves are a scale — 0% is off, 1% is the fan’s lowest stable speed, 100% is full speed. Percentages in calibration results are the actual PWM duty sent to the fan.');
for(const k of ['stop','start_search','minimum_search','stop_timeout','cannot_start','unstable_or_missing_rpm','inconsistent_table','feedback_lost','temperature_lost','measuredStart','belowMin','start'])assert.equal(W[k],undefined,k);
assert.match(calibrationText({calibrating:true,cal_stage:'verify',output:23,cal_wait:2}),/复核最低档/);
const failure={cal_error:'no_rpm',cal_failed_stage:'signal',cal_failed_output:100,cal_retry:1,cal_readings:[200,null,1500]};
assert.match(calibrationText(failure),/100%.*1\\/3.*200, —, 1500/);
lang='en';assert.match(calibrationText(failure),/Checking speed signal/);
lang='zh';assert.equal(calibrationText({cal_error:'',config:{cal:{valid:true,minimum_measured:18,auto_raised:2}}}),'实测最低稳转输出 18% · 运行中已自动提高最低档 2%');
lang='en';assert.equal(calibrationText({cal_error:'',config:{cal:{valid:true,minimum_measured:18,auto_raised:2}}}),'Measured lowest stable output 18% · Minimum raised automatically by 2% during use');
assert.equal(calibrationText({cal_error:''}),'');
console.log('Calibration stage and failure details checks passed');
"""],check=True)

# Curve editor uses immediate auto-save with retry on failure (no manual save/undo draft bar).
for removed in ('id="saveBar"', 'data-a="saveCurve"', 'data-a="undo"', 'draftNone:'):
    assert removed not in s_web, removed
for required in ('id="curveErr"', 'data-a="retryCurve"', "curveSaveFail:'曲线未保存，修改已保留|Curve not saved. Changes retained.'"):
    assert required in s_web, required

curve_fns = '\n'.join(
    re.search(r'function ' + name + r'\(.*?(?=\nfunction |\n\$|\nconst |\nlet )', s_web, re.S).group()
    for name in ('send', 'loadDraft', 'pointsEqual', 'markCurveEdit', 'scheduleCurveSave', 'saveCurve', 'curveOrdered', 'curveError', 'moveNode', 'insertPoint', 'render', 'bindGraph')
)
hold_block = re.search(r'let hT=null.*?\nfunction hold\(.*?(?=\ndocument\.addEventListener)', s_web, re.S).group()
actions_src = {
    name: re.search(r'\b' + name + r':([^\n]+),', s_web).group(1)
    for name in ('go', 'addPt', 'del', 'retryCurve')
}
auto_save_script = (
    'const assert=require("node:assert/strict");\n'
    'const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));\n'
    + words + '\n'
    + 'let lang="zh",resetRequested=false,resetNote="",online=true,state,draft=null,dirty=false,curveRev=0,curveSaving=false,curveQueued=false,curveFail="",curveTimer=null;\n'
    + 'let commandEpoch=0,commandsPending=0,commandQueue=Promise.resolve(),rebooting=null,graphDrag=false,graphMoved=false;\n'
    + 'const ui={tab:"curve",node:0,cu:0,unit:0};\n'
    + 'let G={L:0,R:500,T:0,B:200};\n'
    + 'const listeners={},graphEl={addEventListener:(ev,fn)=>{listeners[ev]=fn},getBoundingClientRect:()=>({left:0,top:0,width:500,height:200}),setPointerCapture:()=>{}};\n'
    + 'const $=id=>id==="graph"?graphEl:null;\n'
    + 'const t=k=>words[lang][k]||k,live=()=>online===true&&!resetRequested,valid=()=>false,cuOn=()=>false;\n'
    + 'const busyGuard=()=>{if(!live()||state.calibrating)return true;return false};\n'
    + 'let paints=0,curveRenders=0,toasts=[],calls=[],timers=new Map(),nextTimer=0;\n'
    + 'const paint=()=>paints++,renderCurve=()=>curveRenders++,translate=()=>{},syncManual=()=>{},scrollTo=()=>{},toast=(m,e)=>toasts.push([m,!!e]);\n'
    + 'const origSetTimeout=setTimeout,origClearTimeout=clearTimeout;\n'
    + 'setTimeout=(fn,ms)=>{const id=++nextTimer;timers.set(id,{fn,ms});return id;};\n'
    + 'clearTimeout=id=>{timers.delete(id);};\n'
    + 'const flushTimers=()=>{for(const [id,t] of [...timers.entries()]){timers.delete(id);t.fn();}};\n'
    + 'let requestImpl;\n'
    + 'async function request(payload){calls.push(payload);return await requestImpl(payload);}\n'
    + curve_fns + '\n'
    + hold_block + '\n'
    + 'const A={' + ','.join(f'{k}:{v}' for k, v in actions_src.items()) + '};\n'
    + r'''
const mkState=pts=>({config:{english:false,cal:{valid:false},points:pts.map(p=>[...p])},calibrating:false});
const tick=()=>new Promise(r=>origSetTimeout(r,0));
(async()=>{
 render(mkState([[25,20],[35,50],[45,100]]));
 assert.deepEqual(draft.points,[[25,20],[35,50],[45,100]]);
 assert.equal(dirty,false);
 bindGraph();

 // 1. Selecting a node without moving does not send a request.
 requestImpl=async p=>mkState(p.config.points);
 listeners.pointerdown({clientX:350,clientY:100,pointerId:1});
 assert.equal(ui.node,1);assert.equal(graphDrag,true);
 listeners.pointerup({});
 await tick();
 assert.equal(calls.length,0);

 // 2. Dragging updates draft, blocks polling overwrite while dragging, and saves immediately on pointerup.
 listeners.pointerdown({clientX:350,clientY:100,pointerId:2});
 listeners.pointermove({clientX:370,clientY:80}); // 37C, 60%
 assert.deepEqual(draft.points[1],[37,60]);
 assert.equal(calls.length,0);
 render(mkState([[25,20],[35,50],[45,100]])); // polling during drag must not clobber
 assert.deepEqual(draft.points[1],[37,60]);
 listeners.pointerup({});
 await commandQueue;await tick();
 assert.equal(calls.length,1);
 assert.deepEqual(calls[0],{op:'config',config:{curve_unit:0,points:[[25,20],[37,60],[45,100]]}});
 assert.equal(dirty,false);assert.equal(curveFail,'');

 // 3. pointercancel after drag also auto-saves immediately.
 listeners.pointerdown({clientX:370,clientY:80,pointerId:3});
 listeners.pointermove({clientX:380,clientY:70}); // 38C, 65%
 listeners.pointercancel({});
 await commandQueue;await tick();
 assert.equal(calls.length,2);
 assert.deepEqual(calls[1].config.points,[[25,20],[38,65],[45,100]]);

 // 4. Add and delete node auto-save immediately.
 A.addPt();
 await commandQueue;await tick();
 assert.equal(calls.length,3);
 assert.equal(calls[2].config.points.length,4);
 ui.node=1;
 A.del();
 await commandQueue;await tick();
 assert.equal(calls.length,4);
 assert.equal(calls[3].config.points.length,3);

 // 5. Stepper fine-tuning debounces rapid taps into a single save and flushes on tab leave.
 ui.node=1;
 assert.equal(hold('t',1),true);stopHold();
 assert.equal(calls.length,4);assert.equal(timers.size,1);
 assert.equal(hold('t',1),true);stopHold();
 assert.equal(timers.size,1); // coalesced timer
 flushTimers();
 await commandQueue;await tick();
 assert.equal(calls.length,5);
 assert.equal(calls[4].config.points[1][0],40);

 // Tab switch while debounce timer is pending flushes immediately.
 assert.equal(hold('o',1),true);stopHold();
 assert.equal(timers.size,1);assert.equal(calls.length,5);
 A.go({dataset:{v:'run'}});
 await commandQueue;await tick();
 assert.equal(calls.length,6);
 assert.equal(calls[5].config.points[1][1],66);
 ui.tab='curve';

 // 6. Newer edit while a save is in flight is preserved and queued for a follow-up save.
 let releaseFirst;
 const firstGate=new Promise(r=>{releaseFirst=r;});
 let reqIdx=0;
 requestImpl=async p=>{
  reqIdx++;
  if(reqIdx===1){await firstGate;return mkState(p.config.points);}
  return mkState(p.config.points);
 };
 A.addPt(); // kicks off save #1 (4 points)
 await tick();
 assert.equal(curveSaving,true);
 const beforeSecondCount=draft.points.length;
 A.addPt(); // queues save #2 (5 points) while save #1 is in flight
 assert.equal(draft.points.length,beforeSecondCount+1);
 const expectedLatest=draft.points.map(p=>[...p]);
 releaseFirst();
 await commandQueue;await tick();await commandQueue;await tick();
 assert.equal(draft.points.length,5);
 assert.deepEqual(calls.at(-1).config.points,expectedLatest);
 assert.equal(dirty,false);assert.equal(curveFail,'');

 // 7. Save failure retains local edits, resists polling overwrite, and Retry succeeds.
 requestImpl=async()=>{throw Error('offline');};
 ui.node=1;
 const beforeFail=Math.round(draft.points[1][1]);
 hold('o',1);hold('o',1);stopHold();
 const retained=draft.points.map(p=>[...p]);
 assert.equal(retained[1][1],beforeFail+2);
 flushTimers();
 await commandQueue;await tick();
 assert.equal(dirty,true);
 assert.equal(curveFail,'curveSaveFail');
 assert.equal(words.zh[curveFail],'曲线未保存，修改已保留');
 assert.equal(words.en[curveFail],'Curve not saved. Changes retained.');
 render(mkState([[25,20],[40,66],[45,100]])); // stale poll must not overwrite failed draft
 assert.deepEqual(draft.points,retained);
 // Mismatched server echo also stays failed and retains draft.
 requestImpl=async()=>mkState([[25,20],[40,66],[45,100]]);
 A.retryCurve();
 await commandQueue;await tick();
 assert.equal(dirty,true);assert.equal(curveFail,'curveSaveFail');
 assert.deepEqual(draft.points,retained);
 // Retry succeeds when server accepts.
 requestImpl=async p=>mkState(p.config.points);
 A.retryCurve();
 await commandQueue;await tick();
 assert.equal(dirty,false);assert.equal(curveFail,'');
 assert.deepEqual(calls.at(-1).config.points,retained);
 console.log('Web curve auto-save, queueing, polling protection and retry checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
)
subprocess.run(['node', '-e', auto_save_script], check=True)
