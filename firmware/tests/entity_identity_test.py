"""Exercise translated names with explicit legacy IDs through the real API protocol."""
import ast
import re
import importlib.util
from pathlib import Path

import esphome
from esphome.helpers import fnv1_hash_object_id
from aioesphomeapi import api_pb2, model
from aioesphomeapi.object_id import compute_object_id, fill_missing_object_ids

ROOT = Path(__file__).resolve().parents[1]
component = ROOT / 'components/single_fan'
source = (component / '__init__.py').read_text()
tree = ast.parse(source)
entities = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'ENTITIES' for t in n.targets))
assert re.search(r'default=\{[\"\']name[\"\']:en\}', re.sub(r"\s+", "", source))
assert 'ha_english ?' in source
assert 'ha_english=core.settings.english;' in re.sub(r'\s+', '', (component / 'single_fan.cpp').read_text())
for path in (component / 'single_fan.h', component / 'single_fan.cpp'):
    text = re.sub(r'\s+', '', path.read_text())
    assert 'name_=' not in text and 'set_name(' not in text

spec = importlib.util.spec_from_file_location('api_names', component / 'api_names.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
upstream = (Path(esphome.__file__).parent / 'components/api/api_connection.cpp').read_text()
patched = patch.patch_source(upstream)
assert patched != upstream and patch.patch_source(patched) == patched
assert 'msg.object_id = entity->get_object_id_to(object_id_buf);' in patched
assert 'msg.name = StringRef(name);' in patched
for unexpected in (upstream.replace('msg.name = entity->get_name();', 'changed_upstream();'),
                   upstream.replace(patch.HEADER, patch.HEADER + patch.DECLARATION)):
    try:
        patch.patch_source(unexpected)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Unexpected upstream source was accepted')

classes = dict(fan=(model.FanInfo, api_pb2.ListEntitiesFanResponse),
               sensor=(model.SensorInfo, api_pb2.ListEntitiesSensorResponse),
               text=(model.TextSensorInfo, api_pb2.ListEntitiesTextSensorResponse),
               button=(model.ButtonInfo, api_pb2.ListEntitiesButtonResponse),
               select=(model.SelectInfo, api_pb2.ListEntitiesSelectResponse))
macs = ('aabbcca09058', 'aabbcca09059')
broken = fill_missing_object_ids([model.SensorInfo(key=1, name='温度'),
                                 model.SensorInfo(key=2, name='湿度')], model.DeviceInfo())
assert model.build_unique_id(macs[0], broken[0]) == model.build_unique_id(macs[0], broken[1])
devices = []
for mac in macs:
    snapshots = []
    for language in ('zh', 'en', 'zh'):
        device = model.DeviceInfo(name='breezebox-' + mac[-6:], mac_address=mac)
        infos = []
        for _, en, zh, kind in entities:
            info_class, proto_class = classes[kind]
            msg = proto_class(key=fnv1_hash_object_id(en), name=en if language == 'en' else zh,
                              object_id=compute_object_id(en))
            info = info_class.from_pb(proto_class.FromString(msg.SerializeToString()))
            infos.append(info)
        infos = fill_missing_object_ids(infos, device)
        assert [i.name for i in infos] == [en if language == 'en' else zh for _, en, zh, _ in entities]
        assert [i.object_id for i in infos] == [compute_object_id(en) for _, en, _, _ in entities]
        assert len({i.key for i in infos}) == len(infos)
        ids = [model.build_unique_id(mac, i) for i in infos]
        assert len(set(ids)) == len(entities)
        names_ids = [model.build_unique_id(mac, i, version=2) for i in infos]
        assert len(set(names_ids)) == len(entities)
        snapshots.append((ids, names_ids, [i.key for i in infos]))
    assert snapshots[0][0] == snapshots[1][0] == snapshots[2][0]
    assert snapshots[0][2] == snapshots[1][2] == snapshots[2][2]
    # Name-based IDs change with language; real HA migration is a separate acceptance check.
    assert snapshots[0][1] != snapshots[1][1] and snapshots[0][1] == snapshots[2][1]
    devices.append(set(snapshots[0][0]))
assert devices[0].isdisjoint(devices[1])
print('API protobuf: Chinese/English names, stable keys and legacy IDs, two-device uniqueness; patch idempotence and failure guards passed. Name-based HA migration requires real HA verification.')
