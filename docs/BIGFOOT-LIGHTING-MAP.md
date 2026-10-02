# Basement Bigfoot chambers: lighting signal map and timing

Status 2026-09-22. DEPI 02 and DEPI 04 are basement BioChambers "Bigfoot"
chambers with DEPI lighting controllers. They are different chambers with
different controller boxes; DEPI 01 (upstairs) is a third configuration.
Each claim is marked **live** (measured today), **source** (legacy code in
`~/Developer/DepiBeans/legacy-reference`, may differ from what is installed)
or **unknown**.

## Signal chain

```
PC ──USB 2.0──► Digilent USB chip ──DEPP──► FPGA (ChrisBlaster) ──32 output bits──► box connectors
                (bus powered)               (needs box AC power)                      │
                                                                                     ├─ bits 0/1  SmartLight I2C bus ──► LED rail boards (ATtiny45 + MCP4728 DAC)
                                                                                     ├─ bits 2/3  legacy bus B (not driven today)
                                                                                     ├─ bits 4/5  fast-switch "choke" / saturation flash
                                                                                     └─ 6,21,22,23 measuring; 7–12 cameras; 13–20 aux
LED rails also need their own lighting supply (24 V class; DEPI 04 PSU box shows "Lights −7.2V/GND/+32V").
```

| Layer | DEPI 02 | DEPI 04 | Basis |
|---|---|---|---|
| PC | Dell OptiPlex 7070 | mini-PC | live |
| USB interface | 1443:0005, name `DOnbUsb` | 1443:0005, name `Nexys2` | live |
| FPGA | XC3S500E + XCF04S, DONE set, 50 MHz, idle 0x09 | Nexys2, 50 MHz, idle 0x09 | live |
| FPGA power | controller box "AC Power" inlet; without it: Adept error 5 | box corded | live |
| Box front | 3/4/6, barrel jack, Aux, Pulse Trigg, FPGA Comm | Cameras 1–6, Aux Cam, MP Trigger, Actinic (DB9), MP Power | photos |
| FPGA bit → connector pin | unknown (no .ucf in archive) | unknown | source |
| Lighting code | identical `lighting.py`; mask 35; SmartLight broadcast | same | live |
| Rails lit at 100 | none | some whole rails lit, others dark | operator |

## Timing, layer by layer

**1. PC → FPGA (USB/DEPP).** One FPGA command is ~20 register transfers. A
main-light command is ~185 FPGA commands (connect, 2 mask sets, allocate,
168 pulses, 8 loop counts, terminal, trigger, release). Measured upload time:
DEPI 02 1.48–1.52 s, DEPI 04 1.65 s (live, 7 commands today).

**2. FPGA playback (source, ChrisBlaster V3).** 50 MHz (20 ns tick). Each mask
lasts exactly its cycle count if ≥4 cycles; the first mask of a loop gets +3
cycles; loop-to-loop adds 4 cycles including a 1-cycle (20 ns) glitch that
replays the finished loop's first mask. After the last loop the terminal mask
latches indefinitely. Trigger to first edge is microseconds. These effects are
nanoseconds against millisecond I2C phases, so they do not affect the rails.

**3. Light bus (live + source).** Bit-banged I2C on bit 0 (SDA) / bit 1 (SCL):

| Element | Duration |
|---|---|
| START (SCL high/SDA high → SDA low → SCL low) | 3 × 1 ms |
| Each bit: SCL low 1 ms, high 2 ms, low 1 ms | 4 ms (250 Hz) |
| Each byte: 8 bits + ACK slot, master drives SDA high in ACK | 36 ms |
| STOP (0,0 → SCL high → SDA high) | 3 × 1 ms |
| Intensity packet `00 A1 42 C8 00 00` (100.0, broadcast) | 222 ms |
| Trigger → controller reports completion | 0.26 s (live, both chambers) |

This is bit-for-bit the legacy SmartLight writer (William `SmartlightController`,
`UseChoke=false`). Differences from older writers: mk9000 held the choke bit low
during the packet and for 250 ms afterward; mk9000/Calibratron sent a throwaway
intensity 0 at startup; Python sends neither. The ACK is never read, so
"completed" proves only that the FPGA played the waveform.

**4. Rail board (source, `CalibratedLightController.ino`).** ATtiny45 at 1 MHz,
polling pins (no interrupts, no timeout). Address compiled per board: rails
1–26, aux board 127 (FR/UVA/UVB); broadcast 0 accepted. Samples SDA ~0.3–0.5 ms
after SCL rises (2 ms available) and detects STOP with ~0.5 ms margin.
Processes a packet in roughly 10–60 ms (estimate); keep ≥100 ms between packets
(legacy used 250 ms). Does not write the DAC at power-up: rails stay dark after
a power cycle until a command arrives.

**5. Older "dumb" rails (source, mk9000 `FPGA_Control`).** Two buses (A 0/1,
B 2/3), addresses 0x38–0x3F (wire 0x70…0x7E), one 8-bit value per address,
~78 kHz clock, master drives ACK low, ~2 ms for all 16 values. The current
SmartLight broadcast cannot address these receivers.

## Why a rail can stay dark although the FPGA completed

| Cause | Pattern | Source |
|---|---|---|
| No lighting supply / 24 V at rail | whole group dark, every time | operator/physical |
| Bus cable not connected or wrong port | all dark | physical |
| Light gate bit wrong (choke on 4 vs 5) | all dark; bit 5 might instead be the saturation flash | mk9000 default fast=4/sat=5; Calibratron, test rig and profile use fast=5/sat=4 |
| Board calibration blank (EEPROM reset, reflash, power loss during 0x40) | same rails dark every time; raw commands still light them | firmware: blank → coefficients 0 → 0xA1 gives 0 |
| Rails of the older addressed type or on bus B | same rails dark every time | mk9000 two-bus path |
| Bus glitch at ACK (every board briefly drives SDA low, can fake a STOP) | a different subset each time | firmware ACK code |

## Discriminating checks

Physical (engineer, no commands needed):
1. DEPI 02 lighting supply on; 24 V present at a rail board.
2. Which DEPI 02 connector carries the light bus; cable seated at both ends.
3. Rail board chips: ATtiny45 (8-pin) + MCP4728 (SmartLight) vs PCF8574A-type (older).
4. What FPGA bits 4 and 5 physically drive on each chamber (meter or scope at the connector).

Commands (each needs explicit operator authorization; not run):
5. DEPI 04: 0 → 100 → 0 → 100, ≥1 s apart. Same rails lit each time = per-board state; different subset = bus.
6. Raw all-zone broadcast at a low value (`00 07 hi lo`, bypasses calibration). Rails that light only with raw writes have lost calibration.
7. Scope bits 0/1/4/5 at the rail connector during one command.

## Evidence from the operator's USB drive (2026-09-22)

**Light-bus capture** (`depi I2C capture/DEPI i2c capture.7z`; Saleae Logic,
8 channels, SDA = ch 6, SCL = ch 7, ch 0–5 idle; captured 2026-06-08; chamber
not recorded). Decoded packets:

| Recording | Packets on the wire | Meaning |
|---|---|---|
| all zones 0/1/2/3/128/222/505/555/4000 | `00 00 hi lo`, `00 01 hi lo`, `00 02 hi lo` | broadcast raw DAC value to zones 0, 1, 2 |
| address 5, zone 1, value 28/29 | `0A 00 00 1C` / `0A 00 00 1D` | rail address 5, zone index 0 (UI zone 1), raw 28/29 |

- Every packet is a **raw zone write** (Calibratron path). None is the calibrated
  `0xA1` intensity command the current Python sends. Raw writes bypass each rail's
  EEPROM calibration; `0xA1` depends on it.
- Timing matches the current software: 36 ms per byte, 145 ms per 4-byte packet,
  packets ~620 ms apart (start to start).
- At every ACK clock the analyzer logs START then STOP ~70 µs later: the ATtiny
  rail firmware briefly pulling SDA low while SCL is high. This confirms SmartLight
  ATtiny rails on that bus and that their ACK glitch is electrically visible.
- A rail with address 5 existed on that bus.

**2013 PhenomicsCC** (`PhenomicsCC_gibbs20130823`, May–June 2013). Configs name chambers "Gibbs" (Hitachi
KP-F145GV camera, slopes 8.545/10.730, intercepts 42.06/74.21, transition 85) and
"KobayashiMaru" (template). Its `Configuration.java` is the first-generation
design: two buses (A 0/1 inner, B 2/3 outer), eight 0x70–0x7E addresses per
bus, fast switch **4**, saturation **5**, measuring 6, cameras 7–12, aux 13–20.

`Node 2/3/4` on the drive are greenhouse soil temperature/VWC logs, unrelated.

### Consequence and next test

Two rail generations exist: first-generation two-bus 8-bit rails (2013) and
SmartLight ATtiny rails (addresses 1–26, aux 127). The capture shows SmartLight
rails were being driven with raw zone writes. A rail with blank calibration stays
dark under `0xA1` at any intensity but lights under a raw write. With operator
authorization and someone watching:

1. Broadcast raw zones 0–2 at 128 (≈3% of the 4095 DAC range, a value used in the
   capture), then 0. Rails that light now but not under `0xA1` lack calibration.
2. Address sweep: raw zone 0 = 128 to one address at a time (1–26), then 0. The
   rail that lights identifies that address's physical position. No ACK readback
   exists, so the observer is the reply.

## Firmware defects found in source (not yet confirmed on installed bitstreams)

- 0x10 release frees the slot's memory but clears slot 0's table entry; a later
  0x11 on the same slot frees it again. The Python sends 0x10 after every run.
  Reusing the slot with 0x11 alone avoids this.
- Status is sticky: successful 0x21/0x22/0x31/0x32 do not rewrite status.
- A loop shorter than the next loop's load time (~1–30 µs), a zero-repetition
  loop, or a zero-loop protocol can hold status at 0x0F until reconfiguration.
- Pin constraints (.ucf) are not archived; original project path was
  `C:/Users/<user>/FPGA/Xilinx/ChrisBlasterV3_0/`.
