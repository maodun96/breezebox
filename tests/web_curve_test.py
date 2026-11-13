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
