# checkmk-gpon-sfp

Monitor a GPON SFP ONU stick in CheckMK by reading its HTTP CGI API.

Many "PON on a stick" modules (Zyxel PMG3000 and similar Lantiq/MaxLinear
based sticks) expose a small CGI interface but no SNMP. This script queries
that interface and turns the result into CheckMK local checks, so you can
alert on a degrading fiber link before it drops.

It reports two services:

| Service       | What it covers                                              |
|---------------|-------------------------------------------------------------|
| `GPON Line`   | Registration / GPON O-state, LOID status, FEC, encryption   |
| `GPON Optics` | RX/TX power, temperature, supply voltage, laser bias (graphed) |

The RX power graph is the useful one to watch. A slow drop over weeks usually
means a dirty connector, a failing splitter, or an OLT-side level change.

## Requirements

- A GPON stick that answers `GET /cgi/get_gpon_info` over HTTP Basic auth.
  Endpoint paths and field names vary between firmwares, so verify yours first
  (see below).
- Python 3.6+ on the CheckMK server. Standard library only, nothing to install.
- CheckMK 2.x.

## Verify your stick

Before wiring it into CheckMK, confirm the endpoint exists and see what it
returns:

```bash
curl -su admin:PASSWORD http://192.168.1.1/cgi/get_gpon_info
```

Expected shape (note: this is a JavaScript object, not strict JSON):

```
{line_status:"5",loid_status:0,up_fec:"Disable",down_fec:"Disable",encrypt:"Disable",temp:"43.85",voltage:"3.30",current:"12.62",tx_power:"2.99",rx_power:"-15.29"}
```

If your firmware uses different keys or paths, adjust the `fetch()` path and the
`num()` / `.get()` keys in `gpon_check.py`.

## Test it

```bash
python3 gpon_check.py 192.168.1.1 admin PASSWORD
```

Sample output:

```
<<<local>>>
0 "GPON Line" - O5 (operational), LOID status 0, FEC up/down Disable/Disable, encrypt Disable
0 "GPON Optics" rx_power=-15.29;-25.0;-27.0|tx_power=2.99|temp=43.85;75.0;83.0|voltage=3.30|bias=12.62 RX -15.29 dBm, TX 2.99 dBm, 43.9C
```
<img width="1125" height="339" alt="image" src="https://github.com/user-attachments/assets/fdc67efc-41ad-4262-9424-d08eca2d1904" />

## Install in CheckMK

The stick is agentless, so run the script as a datasource program against a
host that represents the stick.

1. Copy the script onto the CheckMK server and make it executable:

   ```bash
   cp gpon_check.py /omd/sites/<SITE>/local/bin/
   chmod +x /omd/sites/<SITE>/local/bin/gpon_check.py
   ```

2. Add the stick as a host in CheckMK using its management IP.

3. Create the rule under
   `Setup -> Agents -> Other integrations -> Individual program call instead of agent access`
   with the command:

   ```
   python3 /omd/sites/<SITE>/local/bin/gpon_check.py $HOSTADDRESS$ admin <PW>
   ```

4. Run service discovery on the host. `GPON Line` and `GPON Optics` should appear.

## Tuning thresholds

Levels live at the top of `gpon_check.py`:

```python
RX_WARN_LOW, RX_CRIT_LOW   = -25.0, -27.0
RX_WARN_HIGH, RX_CRIT_HIGH =  -9.0,  -8.0
TEMP_WARN, TEMP_CRIT       =  75.0,  83.0
```

The RX values are Class B+ ballpark figures. If you know your provider's OLT
level, set the low warn about 3 dB above your module's rated receive
sensitivity so you catch a slow decline early.

## Security note

Passing the password on the command line puts it in the rule and in the process
list. Prefer the CheckMK password store and hand it in through a wrapper rather
than typing it into the rule directly.

## Credits

The CGI endpoints (`/cgi/get_gpon_info`, `/cgi/get_sn`, ...) were mapped by the
wider GPON-stick community. This project only reuses the read-only `get_gpon_info`
call for monitoring.

## License

MIT. See [LICENSE](LICENSE).
