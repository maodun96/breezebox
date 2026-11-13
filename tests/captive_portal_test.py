"""Offline checks of shipped captive-portal decisions; no radio operations."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).parents[1]
page = (root/'web/captive.html').read_text()
script = page.split('<script>')[1].split('</script>')[0]
with tempfile.TemporaryDirectory() as directory:
    js = Path(directory)/'portal.js'
    js.write_text(script)
    subprocess.run(['node', '--check', str(js)], check=True)
helpers = '\n'.join(re.search(r'^function '+name+r'\(.*$', script, re.M)[0]
                    for name in ('t', 'label', 'networkLabel', 'applyLanguage', 'uniqueNetworks', 'validCredentials', 'showPage', 'passwordVisibility', 'passwordState', 'chooseNetwork'))
translations = re.search(r'^const chinese=.*$', script, re.M)[0]
subprocess.run(['node', '-e', translations + "\nlet language='en';\n" + helpers + r'''
const assert=require('node:assert/strict');
assert(validCredentials('客厅 Wi-Fi','password'));
assert(validCredentials('Guest',''));
assert(validCredentials('SSID','a'.repeat(64)));
assert(!validCredentials('SSID','x'.repeat(64)));
assert(!validCredentials('','password'));
assert(!validCredentials('中'.repeat(11),'password'));
assert(!validCredentials('SSID','short'));
assert(!validCredentials('A\0B','password'));
const list=uniqueNetworks([{}, {ssid:'Guest',rssi:-70,lock:false}, {ssid:'Home',rssi:-50,lock:true}, {ssid:'Home',rssi:-80,lock:true}, {ssid:'<img "x">',rssi:-60,lock:true}]);
assert.deepEqual(list.map(x=>x.ssid),['Home','<img "x">','Guest']);
const nodes={}; const $=id=>nodes[id]??=( {dataset:{},value:'',hidden:false,checked:false,required:false,type:'password',textContent:'',setAttribute(k,v){this[k]=v},focus(){this.focused=true}} );
const pages=['networksPage','credentialsPage','result','infoPage','updatePage']; const window={scrollTo(){}};
chooseNetwork('Home',true);
assert.equal($('ssid').value,'Home');assert($('ssidField').hidden);assert($('psk').focused);assert($('psk').required);assert($('networksPage').hidden);
$('psk').value='password';chooseNetwork('Home',true);assert.equal($('psk').value,'password');
chooseNetwork('Guest',false);assert($('passwordField').hidden);assert(!$('psk').required);assert.equal($('psk').value,'');
chooseNetwork('',true,true);assert(!$('ssidField').hidden);assert(!$('openField').hidden);assert($('ssid').focused);
showPage('infoPage');assert(!$('infoPage').hidden&&$('credentialsPage').hidden);
const document={documentElement:{},querySelectorAll(selector){return Object.values(nodes).filter(n=>selector==='[data-i18n]'?n.dataset.i18n!==undefined:n.dataset.ssid!==undefined);}};
chooseNetwork('Home',true);$('psk').value='preview123';passwordVisibility(true);
label($('connect'),'Connecting…');$('connect').disabled=true;label($('formStatus'),'Check the network name and password.');
$('row').dataset={ssid:'中文 SSID',strength:'Strong',lock:'true'};
for(const locale of ['zh','en','zh']){language=locale;applyLanguage();assert.equal($('psk').value,'preview123');assert.equal($('psk').type,'text');assert.equal($('ssid').value,'Home');assert(!$('credentialsPage').hidden);assert($('connect').disabled);assert.equal($('connect').textContent,t('Connecting…'));assert.equal($('formStatus').textContent,t('Check the network name and password.'));assert($('row')['aria-label'].includes('中文 SSID'));assert.equal($('eye')['aria-label'],t('Hide password'));}
console.log('PASS bilingual: switching preserves page, SSID, password, visibility, busy state and translates status');
console.log('PASS portal: credentials, Unicode limits, network dedup/sort, page separation, focus, open/hidden network');
'''], check=True)
# OTA's HTTP 200 is not proof of success. Check the actual response body.
handler = re.search(r"\$\('updateForm'\)\.onsubmit=async event=>\{.*?\n\};", script, re.S)[0]
subprocess.run(['node', '-e', r'''
const assert=require('node:assert/strict');let busy=false;
const nodes={};const $=id=>nodes[id]??={dataset:{}};const FormData=class{};const label=(el,text)=>{el.textContent=text;};
let reply='Update Failed!';const request=async()=>({text:async()=>reply});
''' + handler + r'''
(async()=>{await $('updateForm').onsubmit({preventDefault(){}});assert($('updateStatus').textContent.startsWith('Update not confirmed'));assert(!busy);
reply='Update Successful!';await $('updateForm').onsubmit({preventDefault(){}});assert($('updateStatus').textContent.startsWith('Update accepted'));
console.log('PASS OTA: HTTP 200 failure is not displayed as success');})().catch(e=>{console.error(e);process.exitCode=1});
'''], check=True)
assert '<html lang="en">' in page and 'name="psk"' in page
assert "name.textContent=ap.ssid" in script
assert "method:'POST',body:new URLSearchParams({ssid,psk:password})" in script
assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=["\']https?://', page)

assert "let language='en'" in script
assert 'background:#fff' in page and 'prefers-color-scheme:dark' not in page

# Execute the shipped DNS parser with an in-memory datagram socket.
dns = (root/'components/captive_portal/dns_server_esp32_idf.cpp').read_text()
constants = dns[dns.index('// DNS constants'):dns.index('void DNSServer::start')]
process = dns[dns.index('void DNSServer::process_next_request()'):dns.index('}  // namespace')]
harness = r'''
#include <arpa/inet.h>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <vector>
#define ESP_LOGV(...) ((void)0)
#define ESP_LOGVV(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
struct ip4_addr_t { uint32_t addr; };
std::vector<uint8_t> query, reply;
ssize_t fake_recvfrom(int, void *out, size_t size, int, sockaddr *, socklen_t *) {
  assert(query.size()<=size);memcpy(out,query.data(),query.size());return query.size();
}
#define recvfrom fake_recvfrom
struct Socket {
  bool ready(){return true;} int get_fd(){return 1;}
  ssize_t sendto(const void *data,size_t len,int,sockaddr *,socklen_t){
    auto p=static_cast<const uint8_t *>(data);reply.assign(p,p+len);return len;
  }
};
class DNSServer {
 public:
  Socket socket; Socket *socket_=&socket; uint8_t buffer_[512]{};
  ip4_addr_t server_ip_{inet_addr("192.168.4.1")};
  void process_next_request();
};
'''
harness += constants + process + r'''
int main(){
  DNSServer server;
  for(uint16_t type: {1,28,64,65}){
    query={0x12,0x34,1,0,0,1,0,0,0,0,0,1,4,'t','e','s','t',0,0,uint8_t(type),0,1};
    const auto question=query;
    // EDNS additional record is omitted from the response, including its count.
    query.insert(query.end(),{0,0,41,4,208,0,0,0,0,0,0});
    reply.clear();server.process_next_request();
    assert(reply.size()==question.size()+(type==1?sizeof(DNSAnswer):0));
    auto *h=reinterpret_cast<const DNSHeader *>(reply.data());
    assert(ntohs(h->id)==0x1234 && ntohs(h->flags)==0x8400);
    assert(ntohs(h->qd_count)==1 && ntohs(h->an_count)==(type==1?1:0));
    assert(h->ns_count==0 && h->ar_count==0);
    assert(memcmp(reply.data()+12,question.data()+12,question.size()-12)==0);
    if(type==1)assert(memcmp(reply.data()+reply.size()-4,&server.server_ip_.addr,4)==0);
  }
  query.resize(20);reply.clear();server.process_next_request();assert(reply.empty());
}
'''
with tempfile.TemporaryDirectory() as directory:
    source=Path(directory)/'dns.cpp';binary=Path(directory)/'dns'
    source.write_text(harness)
    subprocess.run(['clang++','-std=c++17','-fsanitize=address,undefined',str(source),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
print('PASS DNS: A redirect, AAAA/SVCB/HTTPS empty answers, echoed question, EDNS counts, truncated rejection')

# Read the actual serializer assignments, checking booleans and the AP-derived URL.
portal=(root/'components/captive_portal/captive_portal.cpp').read_text()
api=portal.split('if (url == ESPHOME_F("/captive-portal-api")) {')[1].split('  if (url ==')[0]
fields=dict(re.findall(r'root\["([^"]+)"\] = (.*);',api))
assert fields == {'captive':'true','user-portal-url':'std::string("http://") + wifi::global_wifi_component->wifi_soft_ap_ip().str_to(ip_buf) + "/"'}
assert 'beginResponse(200, "application/captive+json", data.c_str())' in api
assert 'addHeader("Cache-Control", "private")' in api
assert 'json::build_json' in api and 'req->send(response)' in api
wifi=(root/'components/wifi/wifi_component_esp_idf.cpp').read_text()
assert 'sizeof("http://255.255.255.255/captive-portal-api")' in wifi
assert 'strcat(captive_portal_uri, "/captive-portal-api")' in wifi
assert '此页面无法确认结果' in page and '微风盒 App 或设备网页中查看和管理' in page
print('PASS captive API serializer shape, content type, cache policy and DHCP URI; submission remains unconfirmed')
