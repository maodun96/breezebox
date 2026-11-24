#pragma once
#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>

namespace fan_improv {
inline bool valid_packet(const std::vector<uint8_t> &p) {
  if (p.size() < 3 || p.size() != size_t(p[1]) + 3) return false;
  uint8_t sum=0; for(size_t i=0;i+1<p.size();++i) sum+=p[i];
  if(sum!=p.back()) return false;
  if(p[0]==2 || p[0]==3 || p[0]==4) return p[1]==0;
  if(p[0]!=1) return true;
  if(p[1]<3 || p[2]==0 || p[2]>32) return false;
  const size_t password=3+p[2];
  if(password>=p.size()-1 || p[password]>64 || password+1+p[password]!=p.size()-1) return false;
  if(p[password]!=0 && p[password]<8) return false;
  for(size_t i=3;i<password;++i) if(p[i]==0) return false;
  for(size_t i=password+1;i+1<p.size();++i) if(p[i]==0) return false;
  if(p[password]==64) for(size_t i=password+1;i+1<p.size();++i)
    if(!((p[i]>='0'&&p[i]<='9')||(p[i]>='a'&&p[i]<='f')||(p[i]>='A'&&p[i]<='F'))) return false;
  return true;
}
struct Network { std::string ssid; int rssi; uint8_t auth; };
inline std::string authentication(uint8_t auth) {
  switch(auth) {
    case 0:return "NO"; case 1:return "WEP"; case 2:return "WPA";
    case 3:return "WPA2"; case 4:return "WPA/WPA2"; case 5:return "WPA2 EAP";
    case 6:return "WPA3"; case 7:return "WPA2/WPA3"; case 8:return "WAPI";
    default:return "";
  }
}
inline std::vector<std::string> scan_strings(std::vector<Network> networks) {
  std::stable_sort(networks.begin(),networks.end(),[](const auto&a,const auto&b){return a.rssi>b.rssi;});
  std::vector<std::string> result, seen; size_t bytes=0;
  for(const auto& n:networks) {
    const auto auth=authentication(n.auth),rssi=std::to_string(n.rssi);
    if(n.ssid.empty() || n.ssid.size()>32 || auth.empty() || std::find(seen.begin(),seen.end(),n.ssid)!=seen.end()) continue;
    seen.push_back(n.ssid);
    const auto size=n.ssid.size()+rssi.size()+auth.size()+3;
    // Improv BLE carries a single response, with one byte for the complete payload length.
    if(bytes+size>255) continue;
    result.insert(result.end(),{n.ssid,rssi,auth}); bytes+=size;
  }
  return result;
}
}
