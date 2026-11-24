"""Local UI fixture only; never talks to or updates a controller."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
from urllib.parse import parse_qs

FIXTURE = Path('/tmp/fan-captive-preview.json')
DEFAULT = dict(name='breezebox-a09058', mac='B0:CB:D8:A0:90:58', aps=[{},
    dict(ssid='Home Wi-Fi', rssi=-42, lock=True),
    dict(ssid='Living Room', rssi=-64, lock=True),
    dict(ssid='Guest', rssi=-78, lock=False)])

class Handler(BaseHTTPRequestHandler):
    def reply(self, data, kind='text/plain', status=200):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/config.json':
            data = json.loads(FIXTURE.read_text()) if FIXTURE.exists() else DEFAULT
            self.reply(json.dumps(data).encode(), 'application/json')
        else:
            self.reply((Path(__file__).parents[1]/'web/captive.html').read_bytes(), 'text/html; charset=utf-8')

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if self.path == '/wifisave':
            values = parse_qs(body.decode(), keep_blank_values=True)
            self.reply(b'Saved. Connecting...' if values.get('ssid') else b'Invalid', status=200 if values.get('ssid') else 400)
        elif self.path == '/update':
            self.reply(b'Update Failed!')  # Upstream returns HTTP 200 even on OTA failure.
        else:
            self.reply(b'Not found', status=404)

if __name__ == '__main__':
    HTTPServer(('127.0.0.1', 8769), Handler).serve_forever()
