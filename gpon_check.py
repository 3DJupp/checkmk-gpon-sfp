#!/usr/bin/env python3
"""CheckMK datasource program / local check for GPON SFP ONU sticks.

Reads the stick's HTTP CGI API and emits a <<<local>>> section with two
services:

  GPON Line     registration / GPON O-state
  GPON Optics   RX/TX power, temperature, voltage, laser bias (graphed)

Usage:
  gpon_check.py <host> [user] [pass]

Defaults: host 192.168.1.1, user admin, pass 1234 (typical stick factory
settings). Point <host> at the stick's management IP.

CheckMK setup (agentless host for the stick):
  Setup -> Agents -> Other integrations ->
    "Individual program call instead of agent access"
  Command: python3 /omd/sites/<SITE>/local/bin/gpon_check.py $HOSTADDRESS$ admin <PW>
  Then add the stick as a host and run service discovery.

Only the Python 3 standard library is used, no external packages.
"""

import sys
import re
import base64
import urllib.request

if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
    print(__doc__)
    sys.exit(0)

host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.1"
user = sys.argv[2] if len(sys.argv) > 2 else "admin"
pw   = sys.argv[3] if len(sys.argv) > 3 else "1234"

# GPON transmission convergence states (ITU-T G.984.3)
O_STATE = {
    "1": "O1 (initial)",       "2": "O2 (standby)",
    "3": "O3 (serial number)", "4": "O4 (ranging)",
    "5": "O5 (operational)",   "6": "O6 (intermittent LOS)",
    "7": "O7 (emergency stop)",
}

# RX power window for a GPON Class B+ ONU, in dBm
RX_WARN_LOW, RX_CRIT_LOW = -25.0, -27.0
RX_WARN_HIGH, RX_CRIT_HIGH = -9.0, -8.0
# Case temperature, in degrees C
TEMP_WARN, TEMP_CRIT = 75.0, 83.0


def fetch(path):
    url = f"http://{host}{path}"
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode(errors="replace")


def parse(text):
    """Flat JS object (key:"val" or key:val) into a dict. Not real JSON."""
    return dict(re.findall(r'(\w+)\s*:\s*"?([^",}]+)"?', text))


print("<<<local>>>")

try:
    d = parse(fetch("/cgi/get_gpon_info"))
except Exception as e:  # noqa: BLE001 - surface any failure as a CRIT service
    print(f'2 "GPON Line" - fetch failed: {e}')
    sys.exit(0)

# --- GPON Line / registration ---
ls = d.get("line_status", "?")
label = O_STATE.get(ls, f"state {ls}")
line_state = 0 if ls == "5" else 2
print(
    f'{line_state} "GPON Line" - {label}, '
    f'LOID status {d.get("loid_status", "?")}, '
    f'FEC up/down {d.get("up_fec", "?")}/{d.get("down_fec", "?")}, '
    f'encrypt {d.get("encrypt", "?")}'
)


# --- GPON Optics ---
def num(key):
    try:
        return float(d[key])
    except (KeyError, ValueError, TypeError):
        return None


rx, tx, temp = num("rx_power"), num("tx_power"), num("temp")
volt, bias = num("voltage"), num("current")

state, msg = 0, []

if rx is None:
    state, msg = 2, ["no RX power"]
else:
    if rx <= RX_CRIT_LOW or rx >= RX_CRIT_HIGH:
        state = max(state, 2)
    elif rx <= RX_WARN_LOW or rx >= RX_WARN_HIGH:
        state = max(state, 1)
    msg.append(f"RX {rx:.2f} dBm")

if tx is not None:
    msg.append(f"TX {tx:.2f} dBm")

if temp is not None:
    if temp >= TEMP_CRIT:
        state = max(state, 2)
    elif temp >= TEMP_WARN:
        state = max(state, 1)
    msg.append(f"{temp:.1f}C")

# Perfdata. Thresholds here act as graph guide lines only; the service state
# comes from `state` above, because for RX power lower means worse and
# CheckMK's automatic perfdata evaluation only knows upper bounds.
perf = []
if rx   is not None: perf.append(f"rx_power={rx};{RX_WARN_LOW};{RX_CRIT_LOW}")
if tx   is not None: perf.append(f"tx_power={tx}")
if temp is not None: perf.append(f"temp={temp};{TEMP_WARN};{TEMP_CRIT}")
if volt is not None: perf.append(f"voltage={volt}")
if bias is not None: perf.append(f"bias={bias}")
perf = "|".join(perf) if perf else "-"

print(f'{state} "GPON Optics" {perf} {", ".join(msg)}')
