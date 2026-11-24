"""UI-only preview. No connection to a physical fan; never use as firmware validation."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs
import argparse, json, time
config = dict(enabled=False,automatic=False,english=False,prompt_seen=False,manual_unit=0,curve_unit=0,custom=0,custom_unit=0,power=0,manual=30,last_pwm=30,last_rpm=1000,pulses=2,points=[[30,0],[40,50],[50,100]],cal=dict(valid=False,minimum=15,minimum_measured=0,minimum_rpm=0,maximum=100,auto_raised=0,rpm_step=2,rpm_dense=[0]*51,rpm=[0]*11))
state = dict(config=config,temperature=39.5,humidity=31.0,rpm=0,output=0,target=0,target_rpm=0,limited=False,calibrating=False,progress=0,cal_error='',cal_stage='',cal_wait=0,temp_fault=False,rpm_fault=False,save_fault=False,config_fault=False,error='',version='PREVIEW — NO DEVICE',uptime=0,free_heap=100000,ip='127.0.0.1',wifi=True)
cal_started = None
cal_auto_after = False
SIMULATED_CAL = dict(valid=True,minimum=22,minimum_measured=20,minimum_rpm=525,maximum=100,auto_raised=0,rpm_step=2,rpm_dense=[0 if i<10 else 525+(i-11)*49 for i in range(51)])
SIMULATED_CAL['rpm'] = SIMULATED_CAL['rpm_dense'][::5]

def scale_to_output(minimum, value):
    return 0 if value <= 0 else minimum + (min(100, max(1, value))-1)*(100-minimum)/99

def start_calibration(auto_after=False):
    global cal_started, cal_auto_after
    cal_started, cal_auto_after = time.monotonic(), auto_after
    state.update(calibrating=True,progress=0,cal_error='')

def cancel_calibration():
    global cal_started
    cal_started = None
    state.update(calibrating=False,progress=0,cal_stage='',cal_wait=0)

def update_preview(now=None):
    global cal_started
    if cal_started is not None:
        elapsed = (time.monotonic() if now is None else now) - cal_started
        state['progress'] = min(100, int(elapsed / 30 * 100))
        if elapsed < 30:
            # Condensed UI illustration only; algorithm checks use the C++ controller.
            stages = [('signal',100),('signal',100),('rpm_table',90),('rpm_table',80),
                      ('rpm_table',60),('rpm_table',40),('rpm_table',30),('rpm_table',20),
                      ('verify',100),('verify',22)]
            stage, output = stages[min(9, int(elapsed / 3))]
            state.update(cal_stage=stage,cal_wait=int(elapsed % 3),output=output,rpm=SIMULATED_CAL['rpm_dense'][output//2])
            return
        config['cal'] = dict(SIMULATED_CAL, rpm=list(SIMULATED_CAL['rpm']))
        config['prompt_seen'] = True
        if cal_auto_after: config['automatic'] = True
        cal_started = None
        state.update(calibrating=False,cal_stage='',cal_wait=0)
    target = config['manual']
    unit = config['manual_unit']
    if config['automatic']:
        points = sorted(config['points'])
        temp = state['temperature']
        target = points[0][1] if temp <= points[0][0] else points[-1][1]
        for (a,x),(b,y) in zip(points,points[1:]):
            if a <= temp <= b:
                target = x + (y-x)*(temp-a)/(b-a)
                break
        unit = config['curve_unit']
    if not config['enabled']: target = 0
    output = max(config['cal']['minimum'], min(100, target / 2450 * 100)) if target>0 and unit else scale_to_output(config['cal']['minimum'], target)
    state.update(target=target,output=output,rpm=round(output*24.5),target_rpm=round(target if unit else output*24.5))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/control':
            update_preview()
            self.reply(json.dumps(state).encode(),'application/json')
        else: self.reply((Path(__file__).parents[1]/'web/index.html').read_bytes(),'text/html; charset=utf-8')
    def do_POST(self):
        if self.path!='/control':self.send_error(400);return
        body=self.rfile.read(int(self.headers.get('Content-Length',0))).decode()
        o=json.loads(parse_qs(body)['data'][0]);op=o['op']
        if state['calibrating'] and op not in ('cancel','enable'):
            self.send_error(409);return
        if op=='enable':
            config['enabled']=o['value']
            if not o['value']:cancel_calibration()
        elif op=='auto':config['automatic']=o['value']
        elif op=='manual':config.update(automatic=False,manual=o['value'],manual_unit=o['unit'],enabled=o['value']>0)
        elif op=='custom':config.update(custom=o['value'],custom_unit=o['unit'])
        elif op=='prompt':config['prompt_seen']=True
        elif op=='config':
            for k,v in o['config'].items():
                if k=='cal':config[k].update(v)
                else:config[k]=v
        elif op=='calibrate':start_calibration(o.get('auto_after',False))
        elif op=='cancel':cancel_calibration()
        update_preview()
        self.reply(json.dumps(state).encode(),'application/json')
    def reply(self,data,kind):
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def log_message(self,*args): pass
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=18765)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:
        start_calibration(True); started=cal_started; update_preview(started+15)
        assert state['calibrating'] and state['progress']==50 and not config['cal']['valid']
        update_preview(started+30)
        assert 'version' not in config and config['cal']['valid'] and config['cal']['minimum_measured']==20 and config['cal']['auto_raised']==0 and config['cal']['rpm_step']==2 and len(config['cal']['rpm_dense'])==51
        assert not any(k.startswith('start') for k in config['cal'])
        assert scale_to_output(20,0)==0 and scale_to_output(20,1)==20 and abs(scale_to_output(20,50)-59.6)<.01 and scale_to_output(20,100)==100
        assert config['automatic'] and not config['enabled'] and state['rpm']==0
        old=config['cal'].copy(); start_calibration(); update_preview(cal_started+6)
        cancel_calibration(); update_preview()
        assert config['cal']==old and not state['calibrating'] and state['output']==0
        print('Preview calibration checks passed')
    else:
        HTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
