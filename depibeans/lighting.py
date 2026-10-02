"""Offline codecs for the legacy lighting protocol. No device I/O.

Source correspondence: Calibratron App.java setZone/setAllZones,
uploadCalibration/setLightIntensity. Float values are IEEE-754 big-endian.
Transport ranges here are not commissioned physical operating limits.
"""
from dataclasses import dataclass
import math
import struct

BROADCAST = 0


def require_address(address, allow_broadcast):
    integer(address, 0, 127, 'I2C address')
    if address == BROADCAST and allow_broadcast is not True:
        raise ValueError('Broadcast raw/calibration writes require explicit opt-in')


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")
    return value


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite number")
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError("Number is outside the supported range") from exc
    if not math.isfinite(value):
        raise ValueError("Expected a finite number")
    return value


def float32(value):
    value = finite(value)
    try:
        return struct.pack('>f', value)
    except (OverflowError, struct.error) as exc:
        raise ValueError("Value does not fit a float32") from exc


@dataclass(frozen=True)
class Packet:
    address: int
    payload: bytes

    def __post_init__(self):
        integer(self.address, 0, 127, 'I2C address')
        if not isinstance(self.payload, bytes) or not self.payload:
            raise ValueError('Payload must be nonempty bytes')

    @property
    def wire_bytes(self):
        return bytes([self.address << 1]) + self.payload


def zone_packet(address, zone, raw, *, allow_broadcast=False):
    require_address(address, allow_broadcast)
    integer(zone, 0, 6, 'zone')  # 7 is the all-channels command.
    integer(raw, 0, 65535, 'raw output')
    return Packet(address, bytes([zone]) + struct.pack('>H', raw))


def all_zones_packet(address, raw, *, allow_broadcast=False):
    require_address(address, allow_broadcast)
    integer(raw, 0, 65535, 'raw output')
    return Packet(address, b'\x07' + struct.pack('>H', raw))


def intensity_packet(intensity, address=BROADCAST):
    """Legacy calibrated-intensity command deliberately targets all rails by default."""
    if finite(intensity) < 0:
        raise ValueError('Intensity cannot be negative')
    return Packet(address, b'\xa1' + float32(intensity))


def calibration_packet(address, zone, coefficients, *, allow_broadcast=False):
    require_address(address, allow_broadcast)
    integer(zone, 0, 6, 'zone')
    if len(coefficients) != 3:
        raise ValueError('Legacy calibration requires three quadratic coefficients')
    return Packet(address, bytes([0x40, zone]) + b''.join(float32(c) for c in coefficients))


@dataclass(frozen=True)
class Pulse:
    bitmask: int
    duration_s: float


def i2c_waveform(packet, *, clock_pin, data_pin, baseline_mask, terminal_mask, bit_duration_s=0.001):
    """Compile FPGA bitmasks, never software-sleep bit-bang the physical bus.

    Keeps unrelated configured bits intact. The caller must supply commissioned
    baseline/terminal masks; do not guess choke or saturation pin polarity.
    ACK clock slots match the legacy writer; this does NOT read acknowledgments.
    """
    integer(clock_pin, 0, 31, 'clock pin')
    integer(data_pin, 0, 31, 'data pin')
    integer(baseline_mask, 0, 0xffffffff, 'baseline mask')
    integer(terminal_mask, 0, 0xffffffff, 'terminal mask')
    if clock_pin == data_pin or finite(bit_duration_s) <= 0:
        raise ValueError('Distinct pins and positive timing are required')
    pulses = []
    mask = baseline_mask
    def emit(clock, data, factor=1):
        nonlocal mask
        mask = (mask & ~((1 << clock_pin) | (1 << data_pin))) | (clock << clock_pin) | (data << data_pin)
        pulses.append(Pulse(mask, bit_duration_s * factor))
    emit(1, 1); emit(1, 0); emit(0, 0)
    for byte in packet.wire_bytes:
        for shift in range(7, -1, -1):
            bit = (byte >> shift) & 1
            emit(0, bit); emit(1, bit, 2); emit(0, bit)
        emit(0, 1); emit(1, 1, 2); emit(0, 0)
    emit(0, 0); emit(1, 0); emit(1, 1)
    return tuple(pulses), terminal_mask
