# Water levels web dashboard

`levels_web.py` is a Qt-free browser version of `levelsnew5.py`. It shows the
house tank level and animated percentage fill (185 cm full), hill and header
tank depths, spring level, battery readings, roof flow, valve state, and the
30 two-minute rainfall buckets. Browsers refresh once per second. Each sensor
shows its last update time; readings older than five minutes get an amber border.
No readings are invented while waiting for MQTT data.

## Try it without sensors

```sh
bin/python levels_web.py --demo
```

Open http://127.0.0.1:8080. Demo readings are explicitly labelled and change every
two seconds. Demo mode uses only the Python standard library.

## Run with your MQTT broker

```sh
bin/python -m pip install -r requirements-web.txt
bin/python levels_web.py
```

Requires Python 3.10 or newer and a modern browser. The default broker is `MQTT01`
in `credentials` beside the script. Existing `host`, `port`, `username`,
`password`, and `timeout` fields are used; credentials are never sent to the
browser. Override the file or broker using `--config /path/to/credentials`
and `--broker MQTT01`. The web app does not require the old Qt requirements.

To view on other devices on your trusted local network:

```sh
bin/python levels_web.py --host 0.0.0.0 --port 8080
```

Open `http://<server-LAN-IP>:8080` on those devices. This is a local dashboard
without authentication or HTTPS; use an authenticated HTTPS reverse proxy if
remote access is needed. Stop the server with Ctrl+C.

## Compatibility

All seven subscriptions, temperature compensation, packet byte order, spring
59 cm offset, and valve states (0 closed, 1 open) match `levelsnew5.py`. The hill
switch retains its original red (0) and green (nonzero) indication. Rainfall is
shown oldest to newest, matching the Qt plot's reversal against descending x
positions; its vertical scale expands above 5 L when needed.

The original application also republishes decoded hill, header, and spring
packets. Enable that behaviour with `--republish` when replacing the Qt process:

```sh
bin/python levels_web.py --host 0.0.0.0 --republish
```

Leave this option off when running both applications together to avoid duplicate
publications. The dashboard has no valve control: the original is a status display.
MQTT reconnects automatically, and malformed messages leave the last good reading
intact. Readings are held in memory and reset on restart, as in the Qt application.
This repository contains only the web application and its supporting files.

## Checks

```sh
bin/python -m unittest discover -s tests -v
```

Tests cover sensor packet decoding, compensation, rainfall ordering, invalid
messages, JSON state, and the static file allowlist.
