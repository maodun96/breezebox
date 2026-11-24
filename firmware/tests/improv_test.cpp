#include "../components/improv_ble/fan_improv_protocol.h"
#include <cassert>
int main() {
  using namespace fan_improv;
  assert(valid_packet({4,0,4})); assert(!valid_packet({4,0,5}));
  assert(!valid_packet({1,1,255,1}));
  std::vector<uint8_t> credential{1,11,1,'a',8,'1','2','3','4','5','6','7','8'};
  uint8_t sum=0;for(auto v:credential)sum+=v;credential.push_back(sum);
  assert(valid_packet(credential)); credential[2]=32;assert(!valid_packet(credential));
  auto found=scan_strings({{"弱",-80,3},{"强",-30,7},{"强",-40,3},{"",-20,0},{"开放",-50,0}});
  assert(found.size()==9 && found[0]=="强" && found[2]=="WPA2/WPA3" && found[5]=="NO");
  std::vector<Network> many;for(int i=0;i<100;i++)many.push_back({std::string(25,'a')+std::to_string(i),-30-i,3});
  auto bounded=scan_strings(many);size_t bytes=0;for(const auto&s:bounded)bytes+=s.size()+1;
  assert(bytes<=255 && bounded.size()%3==0 && bounded.size()<300);
  assert(scan_strings({}).empty());
}
