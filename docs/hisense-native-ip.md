# Hisense native IP profiles

The two XML files in the repository root use **direct persistent TCP to the TV on port
7310**. They do not require Python, a separate bridge, the Google TV pairing code,
or the `.credentials` files at runtime. The Google TV protocol used in initial experiments is a separate service; its
client and private pairing credentials are not included in this repository.

These are **candidates for Blueprint validation**, not certified Savant profiles.
The Savant XSD, Component Profiling Tool, and target host are not available in this
workspace. Offline checks validate XML parsing, frames, routing and references;
they cannot establish compatibility with a particular Savant release.

Setup:

1. Enable **Settings > Channels & Inputs > External Inputs > Serial/IP Control
   Port** on the TV. The separate Network IP Control service on port 11679 uses a
   different protocol and is not used by these files.
2. Import both `hesense_zafiro - smart tv.xml` and `hisense_zafiro - monitor.xml` files into the user component library.
   They have distinct model names ending in **(Native IP)**.
3. Retain the original monitor/Smart TV media connections. Both LAN connections
   should point directly to **192.168.5.22:7310**, with IP as the control interface.
4. Use persistent TCP. Avoid a port-scanning client or an open/send/close pattern.
   Early disconnects during discovery left this TV refusing new connections;
   toggling Serial/IP Control Port off/on restored it. This behavior needs further
   reliability testing on the actual Savant host.
5. Test `QueryVolumeStatus` first in the profiling tool. The TV's reply is
   case-sensitive **ALL:OkAY**, with a lowercase `k`. Requests are echoed before
   the reply; the receive-start condition skips the echo. Replies end in CRLF.
6. Configure Wake-on-LAN before relying on PowerOn. A follow-up live test
   confirmed that a **single broadcast magic packet to UDP 9** wakes this TV,
   without changing further TV settings. Its Ethernet MAC is
   **C4:08:26:EA:BA:85**; the tested broadcast address is **192.168.5.255**.
   Allow approximately eight seconds for the native TCP service to settle after
   wake. Native TCP PowerOn alone could not reach the TV in standby.
   **The supplied XML PowerOn action does not yet send the WOL packet.** A Savant
   wake workflow must precede it; the exact native XML/host mechanism still needs
   confirmation against the installed Savant schema. No always-on Python bridge
   is required by the TV's WOL mechanism.

Both candidates preserve the original media routing. They map 111 existing action
instances each, repair two already-missing selection actions in the monitor
profile, and add power/volume/mute queries with five-second polling. No cached
power/mute precondition suppresses commands. PowerOff updates its state only on
the TV's acknowledgement. Other queries use actual returned values; an absent
reply does not falsely mean OFF.

Absolute volume is 0-100. Its checksum varies with the ASCII digits, so the XML
uses 101 guarded helper actions with precomputed complete frames. Only the helper
matching `NativeRequestedVolume` sends a command. This avoids inventing a Savant
checksum algorithm name; dispatch performance and the volume scale must still be
checked in Blueprint. Do not invoke `NativeVolumeNNN` helpers manually.

The profile names `Apps`, `SmartHub` and `Internet@TV` map to Home. The protocol
document does not supply direct Netflix/Amazon launch commands or all legacy
Samsung actions present in the originals. Unsupported actions are omitted from
the IP candidates and listed individually in `tools/hisense_native_ip/coverage.json`; no IR
fallback is implied. Notable gaps include direct channel-number selection,
Guide/Info, direct streaming-app launch, recording, AV2 and USB selection. Digit
buttons and channel up/down are mapped. Other keys/inputs are documented mappings
that still need model-specific testing.

Live results on this TV:

- Native volume query returned 18; set to 19 and queried 19; restored to 18.
- Native volume +/- buttons confirmed 18 -> 19 -> 18.
- Mute on/off queries confirmed 0001 -> 0000.
- Home opened the Google TV launcher (also observed through the Google TV client).
- HDMI 1 select was acknowledged and input query returned 0009; Home restored.
- Power query returned 0001. PowerOff was acknowledged; standby disconnected TCP.
  Native TCP PowerOn failed from standby. Broadcast Wake-on-LAN restored the TV.
  A second cycle isolated WOL: after eight seconds in standby, one magic packet to
  UDP 9 woke it; eight seconds later a read-only power query returned 0001, without
  sending a TCP power-on command. Thus TV wake is verified; Savant's WOL dispatch
  is still unimplemented/unvalidated in these candidate XML files.
- Two simultaneous persistent TCP sessions accepted queries and commands, which
  supports the paired-profile layout. This is not a long-term reliability test.

Development only:

```powershell
python tools/hisense_native_ip/build_native_profiles.py
python -m unittest discover -s tools/hisense_native_ip -p test_native_profiles.py -v
python -u tools/hisense_native_ip/native_serial_probe.py
```

The diagnostic probe maintains a connection and accepts `Q VOLM`, `Q MUTE`,
`Q POWR`, `Q INPT`, or `S COMMAND VALUE`. It is not needed by Savant.

Sources:

- Original profiles: https://github.com/devprbtt/componentProfiles
- Hisense ASCII framing, checksum and commands:
  https://assets.hisense-usa.com/assets/ProductDownloads/18/5342defe83/Hisense-RS-232-and-IR-Protocol-English_2.pdf
- Hisense TV manual describing optional Serial/IP control and network wake:
  https://files.hisense-usa.com/download/f2567eff84ed9265

Port 7310, lowercase-k acknowledgements, echoed requests and CRLF replies were
verified directly on this TV; they are not asserted from the older serial manual.

## Test evidence and reproduction

The live test sequence is recorded in `tools/hisense_native_ip/power-wake-test.json`.
It is an observation log, not an automated test to run against a TV. The six offline
unittests do not access the network or change TV settings. Original IR profiles are
retained under `tools/hisense_native_ip/original/` as generator inputs, so rebuilds
are reproducible. The tested model reported Hisense SmartTV 4K FFM, software
7.00.999235495; the retail model number was not supplied. Results do not establish
compatibility with every Hisense U7 or VIDAA model.
