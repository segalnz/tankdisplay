#!/usr/bin/env python3
"""Browser dashboard for the levelsnew5 MQTT sensors (no Qt required)."""
import argparse
import base64
import copy
import json
import logging
import math
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
TOPICS = {
    'hill': 'application/00000000-0000-0000-0000-000000000010/device/70b3d5cd00010375/event/up',
    'header': 'application/00000000-0000-0000-0000-000000000010/device/70b3d5cd00010376/event/up',
    'spring': 'application/00000000-0000-0000-0000-000000000005/device/be7a02000000044a/event/up',
    'house': 'status/pressure/data',
    'flow': 'esp32/davis/litresperhour',
    'valve': 'esp32/valve/status/1',
    'rain': 'esp32/davis/lasthoursrain',
}


def compensated(temperature, depth):
    return int(depth - depth * temperature * 0.00021)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Expected a finite number')
    return value


def decode(kind, payload):
    """Return display fields and optional legacy republish (topic, fields)."""
    publish = None
    if kind == 'house':
        temperature, depth = payload.decode('utf-8').split(',')
        temperature = float(temperature)
        fields = {'depth': compensated(number(temperature), int(depth)), 'temperature': temperature}
        fields['percent'] = max(0, min(100, fields['depth'] * 100 / 185))
    else:
        data = json.loads(payload)
        if kind in ('hill', 'header', 'spring'):
            encoded = data['data']
            raw = base64.b64decode(encoded + '=' * (-len(encoded) % 4), validate=True)
            if len(raw) < (5 if kind == 'header' else 6):
                raise ValueError('Sensor packet too short')
            if kind == 'spring':
                fields = {'distance': int.from_bytes(raw[3:5], 'big', signed=True) + 59,
                          'battery': raw[5] / 10}
                target = 'application/00000000-0000-0000-0000-000000000005/device/' + str(int.from_bytes(raw[:2], 'big'))
            else:
                temperature = int.from_bytes(raw[2:4], 'little') / 100
                fields = {'depth': compensated(temperature, int.from_bytes(raw[:2], 'little')),
                          'battery': raw[5 if kind == 'hill' else 4] / 10}
                if kind == 'hill':
                    fields['sstate'] = raw[4]
                target = 'application/10/device/' + ('70b3d5cd00010375' if kind == 'hill' else '70b3d5cd00010376')
            publish = (target, fields.copy())
        elif kind == 'flow':
            fields = {'value': number(data['value'])}
        elif kind == 'valve':
            if type(data) is not int or data not in (0, 1):
                raise ValueError('Expected valve state 0 or 1')
            fields = {'open': bool(data)}
        elif kind == 'rain':
            if not isinstance(data, list) or len(data) != 30:
                raise ValueError('Expected 30 two-minute rainfall buckets')
            fields = {'litres': [number(v) for v in data]}
        else:
            raise ValueError('Unknown sensor')
    return fields, publish


class Dashboard:
    def __init__(self, demo=False):
        self.lock = threading.Lock()
        self.state = {'demo': demo, 'connected': False, 'sensors': {k: None for k in TOPICS}, 'invalid_messages': 0}

    def update(self, kind, fields):
        with self.lock:
            self.state['sensors'][kind] = dict(fields, updated_at=time.time())

    def connection(self, connected):
        with self.lock:
            self.state['connected'] = connected

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state)


def start_mqtt(dashboard, config_path, broker, republish):
    import paho.mqtt.client as mqtt
    with open(config_path) as config_file:
        config = json.load(config_file)[broker]
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='tank-web-' + str(time.time_ns()))
    client.username_pw_set(config['username'], config['password'])

    def on_connect(client, userdata, flags, reason_code, properties):
        dashboard.connection(reason_code == 0)
        if reason_code == 0:
            client.subscribe([(topic, 1) for topic in TOPICS.values()])
        else:
            logging.warning('MQTT connection rejected: %s', reason_code)

    def on_message(client, userdata, message):
        kind = next((k for k, topic in TOPICS.items() if topic == message.topic), None)
        if kind is None:
            return
        try:
            fields, publication = decode(kind, message.payload)
            dashboard.update(kind, fields)
            if republish and publication:
                client.publish(publication[0], json.dumps(publication[1]))
        except (ValueError, KeyError, TypeError, OverflowError):
            with dashboard.lock:
                dashboard.state['invalid_messages'] += 1
            logging.warning('Ignored invalid %s sensor message', kind)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = lambda client, userdata, flags, reason, properties: dashboard.connection(False)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.connect_async(config['host'], int(config['port']), int(config.get('timeout', 60)))
    client.loop_start()
    return client


def demo_loop(dashboard, stop):
    while not stop.is_set():
        t = time.time() / 10
        dashboard.update('house', {'depth': round(135 + 12 * math.sin(t)), 'percent': (135 + 12 * math.sin(t)) / 185 * 100})
        dashboard.update('hill', {'depth': 172, 'battery': 3.8, 'sstate': int(t) % 4 != 0})
        dashboard.update('header', {'depth': 83, 'battery': 3.7})
        dashboard.update('spring', {'distance': 24, 'battery': 3.6})
        dashboard.update('flow', {'value': round(42 + 20 * math.sin(t))})
        dashboard.update('valve', {'open': int(t) % 3 != 0})
        dashboard.update('rain', {'litres': [round(max(0, 2 + 2 * math.sin(t / 4 + i)), 2) for i in range(30)]})
        stop.wait(2)


def handler_for(dashboard):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split('?', 1)[0]
            if path == '/api/state':
                body = json.dumps(dashboard.snapshot(), allow_nan=False).encode()
                content_type = 'application/json'
            elif path in ('/', '/app.js', '/style.css'):
                filename = 'index.html' if path == '/' else path[1:]
                body = (ROOT / 'web' / filename).read_bytes()
                content_type = {'index.html': 'text/html', 'app.js': 'text/javascript', 'style.css': 'text/css'}[filename]
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            logging.debug(format, *args)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--config', type=Path, default=ROOT / 'credentials')
    parser.add_argument('--broker', default='MQTT01')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--republish', action='store_true', help='Publish decoded hill/header/spring readings as the Qt app does')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    dashboard = Dashboard(args.demo)
    stop = threading.Event()
    client = None
    server = ThreadingHTTPServer((args.host, args.port), handler_for(dashboard))
    try:
        if args.demo:
            threading.Thread(target=demo_loop, args=(dashboard, stop), daemon=True).start()
        else:
            client = start_mqtt(dashboard, args.config, args.broker, args.republish)
        logging.info('Dashboard: http://%s:%s', args.host, args.port)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except (ImportError, OSError, KeyError, ValueError) as error:
        parser.exit(1, 'Unable to start dashboard: ' + str(error) + '\nInstall requirements-web.txt for MQTT mode.\n')
    finally:
        stop.set()
        server.server_close()
        if client:
            client.disconnect()
            client.loop_stop()


if __name__ == '__main__':
    main()
