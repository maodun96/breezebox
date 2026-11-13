#!/usr/bin/env python3
"""Local checks/build/package only. Never connects to or flashes a device."""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
VERSION = '2026.10.1'
FIRMWARE_VERSION = re.search(r'    version: ([0-9.]+)', (ROOT/'config.yaml').read_text())[1]

def run(args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, cwd=ROOT, **kwargs)

def source_files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
                  and not any(part in {'.esphome', '.venv', '__pycache__', 'dist'} for part in p.relative_to(ROOT).parts)
                  and p.name not in {'secrets.yaml', '.DS_Store'})

# Read from the released 1.2.5 factory image at 0x8000; OTA must preserve NVS and both slots.
PARTITIONS = [
    ('otadata', 1, 0, 0x9000, 0x2000, 0),
    ('phy_init', 1, 1, 0xb000, 0x1000, 0),
    ('app0', 0, 0x10, 0x10000, 0x1c0000, 0),
    ('app1', 0, 0x11, 0x1d0000, 0x1c0000, 0),
    ('eeprom', 1, 0x99, 0x390000, 0x1000, 0),
    ('spiffs', 1, 0x82, 0x391000, 0xf000, 0),
    ('nvs', 1, 2, 0x3a0000, 0x60000, 0),
]

def check_partitions(data):
    rows = []
    for offset in range(0, len(data), 32):
        entry = data[offset:offset+32]
        if entry[:2] in (b'\xeb\xeb', b'\xff\xff'):
            break
        magic, kind, subtype, start, size, label, flags = struct.unpack('<HBBII16sI', entry)
        assert magic == 0x50aa, 'Invalid partition entry'
        rows.append((label.rstrip(b'\0').decode(), kind, subtype, start, size, flags))
    assert rows == PARTITIONS, f'Partition layout differs from 1.2.5: {rows}'
    print('PASS partition table: identical to 1.2.5 (including types, subtypes and flags)')

def check_improv_source(build_dir):
    local = ROOT/'components/improv_ble'
    generated = build_dir/'src/esphome/components/improv_ble'
    for source in sorted(local.glob('*')):
        if source.suffix in ('.cpp', '.h'):
            assert (generated/source.name).read_bytes() == source.read_bytes(), f'Wrong Improv source: {source.name}'
    cpp = (generated/'improv_ble_component.cpp').read_text()
    assert 'if (rpc == 3)' in cpp and 'if (rpc == 4)' in cpp and 'fan_improv::scan_strings' in cpp, 'Missing application provisioning RPCs'
    assert not (build_dir/'src/esphome/components/esp32_improv').exists()
    print('PASS compiled config uses local improv_ble with device-info and Wi-Fi-list RPCs')

def check():
    run([sys.executable, ROOT/'tests/partition_test.py'])
    with tempfile.TemporaryDirectory(prefix='fan-check-') as tmp:
        binary = Path(tmp) / 'core-check'
        run([os.environ.get('CXX', 'clang++'), '-std=c++17', '-Wall', '-Wextra', '-Werror',
             '-fsanitize=address,undefined', ROOT/'tests/core_test.cpp', '-o', binary])
        run([binary])
        run([os.environ.get("CXX", "clang++"), "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", ROOT/"tests/improv_test.cpp", "-o", Path(tmp)/"improv-check"])
        run([Path(tmp)/"improv-check"])
        run([sys.executable, ROOT/'tests/provisioning_scan_test.py'])
        run([sys.executable, ROOT/'tests/captive_portal_test.py'])
        run([sys.executable, ROOT/'tests/config_boot_test.py'])
        page = (ROOT/'web/index.html').read_text()
        script = Path(tmp)/'web.js'
        script.write_text(page.split('<script>')[1].split('</script>')[0])
        run(['node', '--check', script])
        run([sys.executable, ROOT/'tests/web_curve_test.py'])
        run([sys.executable, ROOT/'tests/web_control_test.py'])
        run([sys.executable, ROOT/'tests/ha_entities_test.py'])
        run([sys.executable, ROOT/'tests/device_identity_test.py'])
        run([sys.executable, ROOT/'tests/entity_identity_test.py'])
        run([sys.executable, ROOT/'tests/native_ui_test.py'])
        assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=["\']https?://', page)
        # All OLED strings must be covered by the local font subset.
        cfg = (ROOT/'config.yaml').read_text()
        glyphs = set(re.search(r"glyphs: '([^']*)'", cfg)[1])
        cpp = (ROOT/'components/single_fan/single_fan.cpp').read_text().split('void Controller::draw(')[1]
        chars = set(re.sub(r'%[.0-9]*[fs]', '', ''.join(re.findall(r'"([^"\n]*)"', cpp))))
        assert not chars-glyphs, f'Missing OLED glyphs: {chars-glyphs}'
        generated = Path(tmp)/'generated'
        run([sys.executable, '-m', 'esphome', 'compile', ROOT/'config.yaml', '--only-generate'],
            env=dict(os.environ, FAN_BUILD_DIR=str(generated), PLATFORMIO_CORE_DIR='/tmp/single-fan-platformio'))
        check_improv_source(generated)
    print('Core, JavaScript syntax, offline assets and OLED glyph checks passed.')

def package(build_dir):
    out = ROOT/'dist'
    out.mkdir(exist_ok=True)
    env = build_dir/'build'
    ota = env/'firmware.ota.bin'
    check_partitions((env/'partition_table/partition-table.bin').read_bytes())
    partitions = (build_dir/'partitions.csv').read_text()
    rows = [line.split(',') for line in partitions.splitlines() if line.strip() and not line.startswith('#')]
    slots = [int(row[4].strip(), 0) for row in rows if row[2].strip() in ('ota_0', 'ota_1')]
    assert len(slots) == 2 and ota.stat().st_size <= min(slots), 'Does not fit both OTA slots'
    files = source_files()
    manifest = {'version': FIRMWARE_VERSION, 'esphome': VERSION, 'built_at_utc': datetime.now(timezone.utc).isoformat(),
                'hardware_verified': False, 'ota_slot_bytes': slots,
                'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    font = ROOT/'fonts/NotoSansSC-Regular.otf'
    manifest['font_sha256'] = hashlib.sha256(font.read_bytes()).hexdigest()
    manifest['artifacts'] = {}
    (out/'dependencies.txt').write_bytes(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze']))
    for src, name in [(ota, f'single-fan-{FIRMWARE_VERSION}.ota.bin'), (env/'firmware.factory.bin', f'single-fan-{FIRMWARE_VERSION}.factory.bin'),
                      (build_dir/'partitions.csv', 'partitions.csv')]:
        if not src.exists():
            raise FileNotFoundError(src)
        dest = out/name
        shutil.copyfile(src, dest)
        manifest['artifacts'][name] = {'bytes': dest.stat().st_size, 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}
    archive = out/f'single-fan-{FIRMWARE_VERSION}-source.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for p in files:
            tar.add(p, arcname='firmware/'+str(p.relative_to(ROOT)))
    # Verify the delivered source works without files from the current checkout.
    with tempfile.TemporaryDirectory(prefix='fan-source-check-') as tmp:
        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter='data')
        run([sys.executable, Path(tmp)/'firmware/build.py', 'check'], env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    manifest['artifacts']['dependencies.txt'] = {'bytes': (out/'dependencies.txt').stat().st_size, 'sha256': hashlib.sha256((out/'dependencies.txt').read_bytes()).hexdigest()}
    manifest['artifacts'][archive.name] = {'bytes': archive.stat().st_size, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'Packaged {ota.stat().st_size} bytes; smaller OTA slot {min(slots)} bytes. NOT hardware validated.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'build', 'package'])
    args = parser.parse_args()
    if args.action == 'check':
        check(); return
    if importlib.metadata.version('esphome') != VERSION:
        raise SystemExit(f'Requires exactly esphome=={VERSION}')
    if args.action == 'package':
        package(Path(os.environ.get('FAN_BUILD_DIR', '/tmp/single-fan-build'))); return
    check()
    # Fresh ASCII path avoids stale generated sources and toolchain Unicode path failures.
    build_dir = Path(tempfile.mkdtemp(prefix='single-fan-build-'))
    env = dict(os.environ, FAN_BUILD_DIR=str(build_dir))
    env.setdefault('UV_CACHE_DIR', str(Path(tempfile.gettempdir())/'single-fan-uv'))
    env.setdefault('PLATFORMIO_CORE_DIR', str(Path(tempfile.gettempdir())/'single-fan-platformio'))
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files()}
    print(f'Clean build: {build_dir}', flush=True)
    # Native IDF does not execute PlatformIO pre-scripts. Patch after generation, before compilation.
    import esphome.__main__ as esphome_cli
    spec = importlib.util.spec_from_file_location('api_names', ROOT/'components/single_fan/api_names.py')
    api_names = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api_names)
    write_cpp = esphome_cli.write_cpp
    def write_patched_cpp(config):
        result = write_cpp(config)
        if result == 0:
            check_improv_source(build_dir)
            source = build_dir/'src/esphome/components/api/api_connection.cpp'
            source.write_text(api_names.patch_source(source.read_text()))
        return result
    esphome_cli.write_cpp = write_patched_cpp
    os.environ.update(env)
    result = esphome_cli.run_esphome(['esphome', 'compile', str(ROOT/'config.yaml')])
    if result:
        raise SystemExit(result)
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files()}
    assert before == after, 'Source changed during build; rebuild before packaging'
    package(build_dir)

if __name__ == '__main__':
    main()
