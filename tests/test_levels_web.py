import base64
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
from levels_web import Dashboard, decode, handler_for


def packet(raw):
    return json.dumps({'data': base64.b64encode(bytes(raw)).decode().rstrip('=')}).encode()


class DecoderTests(unittest.TestCase):
    def test_house_compensation_and_clamp(self):
        fields, publication = decode('house', b'20,185')
        self.assertEqual(fields['depth'], 184)
        self.assertAlmostEqual(fields['percent'], 184 / 185 * 100)
        self.assertIsNone(publication)
        self.assertEqual(decode('house', b'0,200')[0]['percent'], 100)
        self.assertEqual(decode('house', b'0,-1')[0]['percent'], 0)

    def test_hill_and_header_packet_layout(self):
        hill, pub = decode('hill', packet([200, 0, 208, 7, 1, 38]))
        self.assertEqual(hill, {'depth': 199, 'battery': 3.8, 'sstate': 1})
        self.assertEqual(pub, ('application/10/device/70b3d5cd00010375', hill))
        header, pub = decode('header', packet([100, 0, 208, 7, 37]))
        self.assertEqual(header, {'depth': 99, 'battery': 3.7})
        self.assertTrue(pub[0].endswith('70b3d5cd00010376'))

    def test_spring_signed_big_endian(self):
        spring, pub = decode('spring', packet([0, 42, 0, 255, 246, 36]))
        self.assertEqual(spring, {'distance': 49, 'battery': 3.6})
        self.assertTrue(pub[0].endswith('/42'))

    def test_flow_valve_and_rain_chronology(self):
        self.assertEqual(decode('flow', b'{"value":42}')[0], {'value': 42})
        self.assertEqual(decode('valve', b'0')[0], {'open': False})
        self.assertEqual(decode('valve', b'1')[0], {'open': True})
        values = list(range(30))
        self.assertEqual(decode('rain', json.dumps(values).encode())[0]['litres'], values)

    def test_bad_messages(self):
        for kind, payload in [('house', b'nan,123'), ('hill', packet([1])),
                              ('spring', b'{"data":"!!!"}'), ('valve', b'2'),
                              ('rain', b'[1]'), ('flow', b'{"value":NaN}')]:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                decode(kind, payload)


class HTTPTests(unittest.TestCase):
    def test_dashboard_api_and_static_allowlist(self):
        dashboard = Dashboard()
        dashboard.update('valve', {'open': True})
        snapshot = dashboard.snapshot()
        snapshot['sensors']['valve']['open'] = False
        self.assertTrue(dashboard.snapshot()['sensors']['valve']['open'])
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(dashboard))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for path in ['/', '/app.js', '/style.css', '/api/state']:
                with urlopen(base + path) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.read())
            with urlopen(base + '/api/state') as response:
                self.assertTrue(json.load(response)['sensors']['valve']['open'])
            for path in ['/mqtt_brokers.jsn', '/../levelsnew5.py']:
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
