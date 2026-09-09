# Tank display

A live MQTT water-monitoring web dashboard with tank and spring levels, battery
voltages, roof flow, valve status, and an hourly rainfall chart.

## Setup

The Python virtual environment lives directly in this project folder:

```sh
python3 -m venv .
bin/python -m pip install -r requirements-web.txt
cp credentials.example credentials
# Edit credentials with your MQTT broker settings.
bin/python levels_web.py
```

Open http://localhost:8080. For a sensor-free preview, use
`bin/python levels_web.py --demo`.

The local installation already has broker settings in `credentials`.
Credentials and virtual environment files are excluded from Git.

See [the dashboard guide](README-web.md) for LAN access, MQTT behaviour, and tests.
