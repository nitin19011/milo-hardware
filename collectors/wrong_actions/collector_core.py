"""Continuous stream storage and coarse gesture/background brackets. No inference yet."""
from collections import deque
from dataclasses import dataclass
from datetime import datetime
import csv
import json
import math
from pathlib import Path
import re
import socket
import threading
import time
import uuid
import zipfile

FEATURES = ("ax", "ay", "az", "gx", "gy", "gz", "thumb", "index", "middle")
CLASSES = (
    ("come", "Come / beckon", "Beckon naturally with your index finger."),
    ("sit", "Sit / point down", "Point down deliberately, then relax."),
    ("paw", "Paw / palm up", "Present an upward-facing open palm, then relax."),
    ("spin", "Spin / turn clockwise", "Point and turn your hand clockwise, then relax."),
    ("bang", "Bang / finger gun", "Form your finger gun naturally, then relax."),
    ("throw_overhand", "Overhand throw", "Loosely hold an imaginary ball; throw overhand and open your fingers."),
    ("throw_underhand", "Underhand throw", "Loosely hold an imaginary ball; throw underhand and open your fingers."),
)
ACTIVITIES = ("mixed_everyday", "idle", "walking", "typing", "reaching", "scratching",
              "talking_with_hands", "casual_pointing", "wrist_turns", "open_close_no_command", "adjusting_glove")
COLUMNS = ("frame_index", "host_monotonic_ns", "host_utc_ns", "transport", "packet_order", "boot_id", "seq", "device_us",
           *FEATURES, "raw_thumb", "raw_index", "raw_middle", "imu_ok", "imu_clipped", "flex_rail_mask", "imu_errors_total", "queue_drops_total")


@dataclass(slots=True)
class Frame:
    boot: str
    seq: int
    device_us: int
    features: tuple
    raw: tuple
    imu_ok: int
    clipped: int
    rails: int
    imu_errors: int
    drops: int
    host_ns: int
    utc_ns: int
    transport: str

    def row(self, index, order):
        return (index, self.host_ns, self.utc_ns, self.transport, order, self.boot, self.seq, self.device_us,
                *self.features, *self.raw, self.imu_ok, self.clipped, self.rails, self.imu_errors, self.drops)


def parse_packet(packet, transport, host_ns=None, utc_ns=None):
    try:
        fields = packet.decode("ascii").strip().split(",")
        if len(fields)==27 and fields[0] in ("MILO2","MILO3"):
            fields=fields[:21];fields[0]="MILO1" # Ignore prediction fields; no model gating for manual wrong takes.
        if len(fields) != 21 or fields[0] != "MILO1" or not re.fullmatch(r"[0-9a-f]{16}", fields[1]):
            return None
        seq, device = int(fields[2]), int(fields[3])
        axes = tuple(map(float, fields[4:10]))
        states = tuple(map(int, fields[10:13]))
        raw = tuple(map(int, fields[13:16]))
        ok, clipped, rails, errors, drops = map(int, fields[16:21])
        if not all(math.isfinite(x) for x in axes) or not all(x in (0, 1) for x in (*states, ok, clipped)):
            return None
        if not all(0 <= x <= 4095 for x in raw) or not 0 <= rails <= 7 or min(seq, device, errors, drops) < 0:
            return None
        return Frame(fields[1], seq, device, axes + states, raw, ok, clipped, rails, errors, drops,
                     time.monotonic_ns() if host_ns is None else host_ns,
                     time.time_ns() if utc_ns is None else utc_ns, transport)
    except (ValueError, UnicodeError, OverflowError):
        return None


def save_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


class Session:
    def __init__(self, root, participant="Nitin", split="training", transport="USB"):
        self.folder = Path(root) / (datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
        self.folder.mkdir(parents=True)
        self.lock = threading.RLock()
        self.frames, self.orders, self.events = [], [], []
        self.offsets = deque(maxlen=250)
        self.active = None
        self.last_boot = None
        self.last_seq = None
        self.closed = False
        self.last_flush = time.monotonic()
        self.stats = dict(received=0, missing_samples=0, duplicate_packets=0, out_of_order_packets=0,
                          boot_changes=0, imu_bad=0, flex_rail=0, clipped=0)
        self.meta = {"schema": "milo-candidate-continuous-v1", "session_id": self.folder.name,
                     "participant": participant, "split_role": split, "transport": transport,
                     "created_local": datetime.now().astimezone().isoformat(), "sample_hz": 50,
                     "feature_names": FEATURES, "finger_encoding": {"NOT_BENT": 0, "BENT": 1},
                     "calibration_id": "nitin-20261023-usb-relaxed-fist-v3",
                     "bend": [1696, 1920, 3520], "release": [1583, 1762, 3487],
                     "imu": {"acceleration": "m/s^2 including gravity", "gyro": "rad/s; no bias subtraction",
                             "accel_range_g": 16, "gyro_range_dps": 2000, "dlpf_hz": 21},
                     "classes": [{"id": c, "instruction": instruction} for c, _, instruction in CLASSES],
                     "annotation_semantics": "Operator brackets around the action, not precise physical onset/end labels.",
                     "timing": "Host monotonic markers; device estimates use recent minimum arrival offset. One-way latency is unknown.",
                     "context_policy": "Up to 1 second before and after each gesture. Context/unlabelled data are NOT background labels.",
                     "status": "recording"}
        self.file = (self.folder / "stream.csv").open("w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)
        self.writer.writerow(COLUMNS)
        save_json(self.folder / "session.json", self.meta)
        self.persist_events()

    def ingest(self, frame):
        with self.lock:
            if self.closed:
                return
            order = "ok"
            if frame.boot != self.last_boot:
                if self.last_boot is not None:
                    self.stats["boot_changes"] += 1
                    order = "new_boot"
                self.offsets.clear()
                self.last_boot, self.last_seq = frame.boot, None
            if self.last_seq is not None:
                if frame.seq == self.last_seq:
                    order = "duplicate"; self.stats["duplicate_packets"] += 1
                elif frame.seq < self.last_seq:
                    order = "out_of_order"; self.stats["out_of_order_packets"] += 1
                elif frame.seq > self.last_seq + 1:
                    order = "gap"; self.stats["missing_samples"] += frame.seq - self.last_seq - 1
            if self.last_seq is None or frame.seq > self.last_seq:
                self.last_seq = frame.seq
                self.offsets.append(frame.host_ns - frame.device_us * 1000)
            self.writer.writerow(frame.row(len(self.frames), order))
            self.frames.append(frame); self.orders.append(order)
            self.stats["received"] += 1
            self.stats["imu_bad"] += not frame.imu_ok
            self.stats["flex_rail"] += bool(frame.rails)
            self.stats["clipped"] += bool(frame.clipped)
            if time.monotonic() - self.last_flush >= 1:
                self.file.flush(); self.last_flush = time.monotonic()

    def marker(self, now_ns):
        if not self.frames or not self.offsets:
            raise ValueError("No sensor stream yet. Connect the glove first.")
        latest = self.frames[-1]
        if now_ns - latest.host_ns > 500_000_000:
            raise ValueError("Sensor stream is stale. Check the connection.")
        offsets = sorted(self.offsets)
        return {"host_monotonic_ns": now_ns, "host_utc_ns": time.time_ns(), "boot_id": latest.boot,
                "device_us_estimate": (now_ns - offsets[0]) // 1000,
                "arrival_offset_spread_ms": (offsets[int(.95 * (len(offsets) - 1))] - offsets[0]) / 1e6,
                "last_frame_index": len(self.frames) - 1}

    def start(self, kind, label, now_ns=None, annotation=None):
        with self.lock:
            if self.closed or self.active:
                raise ValueError("A segment is already active, or this session has ended.")
            if kind not in ("gesture", "incorrect_attempt", "background"):
                raise ValueError("Unknown recording mode.")
            if kind in ("gesture","incorrect_attempt") and label not in {x[0] for x in CLASSES}:
                raise ValueError("Unknown gesture.")
            start = self.marker(time.monotonic_ns() if now_ns is None else now_ns)
            self.active = {"id": uuid.uuid4().hex[:12], "kind": kind, "label": label, "start": start,
                           "status": "active", "accepted": False}
            self.active.update(annotation or {})
            self.events.append(self.active)
            self.persist_events()
            return self.active

    def finish(self, now_ns=None):
        with self.lock:
            if not self.active:
                raise ValueError("Start a segment first.")
            e = self.active
            try:
                e["end"] = self.marker(time.monotonic_ns() if now_ns is None else now_ns)
            except ValueError as error:
                e["status"] = "rejected"; e["reason"] = str(error)
                self.active = None; self.persist_events(); return e
            duration = (e["end"]["host_monotonic_ns"] - e["start"]["host_monotonic_ns"]) / 1e9
            e["duration_s"] = round(duration, 4)
            boot = e["start"]["boot_id"]
            a, b = e["start"]["device_us_estimate"], e["end"]["device_us_estimate"]
            core = [(f, order) for f, order in zip(self.frames, self.orders) if f.boot == boot and a <= f.device_us <= b]
            if e["kind"] == "background" and e["end"]["boot_id"] != boot:
                # Preserve useful long negatives across a reboot; split/filter windows by boot later.
                first_host, last_host = e["start"]["host_monotonic_ns"], e["end"]["host_monotonic_ns"]
                core = [(f, order) for f, order in zip(self.frames, self.orders) if first_host <= f.host_ns <= last_host]
            problems = []
            if e["end"]["boot_id"] != boot or self.stats["boot_changes"] and any(f.boot != boot for f in self.frames[e["start"]["last_frame_index"]:]):
                problems.append("device_restarted")
            if not core or len(core) < 5:
                problems.append("too_few_frames")
            if duration < .15:
                problems.append("too_short")
            if e["kind"] in ("gesture","incorrect_attempt") and duration > 12:
                problems.append("gesture_bracket_over_12_seconds")
            if any(not f.imu_ok for f, _ in core): problems.append("imu_read_failure")
            if any(f.rails for f, _ in core): problems.append("flex_rail")
            if any(f.clipped for f, _ in core): problems.append("imu_clipping")
            if any(order != "ok" for _, order in core): problems.append("packet_gap_or_reordering")
            if any(y.seq != x.seq + 1 or not 0 < y.device_us - x.device_us <= 40000 for (x, _), (y, _) in zip(core, core[1:])):
                problems.append("irregular_or_missing_samples")
            if core and core[-1][0].drops != core[0][0].drops: problems.append("device_queue_drops")
            if duration >= .15 and len(core) < max(5, duration * 50 - 4): problems.append("incomplete_segment")
            e["quality"] = {"core_frames": len(core), "issues": sorted(set(problems))}
            # Long negative recordings are useful even with occasional gaps: filter their windows later.
            e["accepted"] = not problems if e["kind"] in ("gesture","incorrect_attempt") else len(core) >= 5
            e["status"] = "accepted" if e["accepted"] else "rejected"
            e["requires_window_quality_filter"] = bool(problems)
            self.active = None
            self.file.flush(); self.persist_events()
            return e

    def cancel(self, reason="operator_cancelled"):
        with self.lock:
            if self.active:
                self.active.update(status="discarded", accepted=False, reason=reason)
                self.active = None
                self.persist_events()

    def discard(self, event_id=None):
        with self.lock:
            target = next((e for e in reversed(self.events) if e["id"] == event_id), None) if event_id else next((e for e in reversed(self.events) if e["status"] != "discarded"), None)
            if not target or target is self.active:
                return None
            target.update(status="discarded", accepted=False, reason="operator_discarded")
            self.persist_events()
            return target

    def persist_events(self):
        save_json(self.folder / "events.json", self.events)

    def snapshot(self):
        with self.lock:
            counts = {c: sum(e["kind"] in ("gesture","incorrect_attempt") and e["label"] == c and e["accepted"] for e in self.events) for c, _, _ in CLASSES}
            negative = sum(e.get("duration_s", 0) for e in self.events if e["kind"] == "background" and e["accepted"])
            return {"counts": counts, "background_s": negative, "stats": dict(self.stats),
                    "frames": self.frames[-200:], "events": [dict(e) for e in self.events[-40:]],
                    "active": dict(self.active) if self.active else None}

    def close_input(self):
        with self.lock:
            if not self.closed:
                self.cancel("session_ended_while_segment_active")
                self.closed = True
                self.file.flush(); self.file.close()

    def export(self):
        self.close_input()
        valid = [e for e in self.events if e["accepted"] and e["kind"] == "gesture"]
        for e in valid:
            a, b = e["start"]["device_us_estimate"], e["end"]["device_us_estimate"]
            boot = e["start"]["boot_id"]
            folder = self.folder / "gesture_clips" / e["label"]
            folder.mkdir(parents=True, exist_ok=True)
            selected = [(i, f, order) for i, (f, order) in enumerate(zip(self.frames, self.orders)) if f.boot == boot and a - 1_000_000 <= f.device_us <= b + 1_000_000]
            with (folder / (e["id"] + ".csv")).open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow((*COLUMNS, "relative_to_start_s", "inside_target_bracket", "other_gesture_ids"))
                for index, f, order in selected:
                    others = [x["id"] for x in valid if x is not e and x["start"]["boot_id"] == boot and x["start"]["device_us_estimate"] <= f.device_us <= x["end"]["device_us_estimate"]]
                    writer.writerow((*f.row(index, order), (f.device_us - a) / 1e6, int(a <= f.device_us <= b), ";".join(others)))
            saved = dict(e)
            saved["pre_context_available_s"] = max(0, (a - min((f.device_us for _, f, _ in selected), default=a)) / 1e6)
            saved["post_context_available_s"] = max(0, (max((f.device_us for _, f, _ in selected), default=b) - b) / 1e6)
            save_json(folder / (e["id"] + ".json"), saved)
        with (self.folder / "events.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("id", "kind", "label", "status", "accepted", "boot_id", "start_device_us_estimate", "end_device_us_estimate", "duration_s", "issues"))
            for e in self.events:
                writer.writerow((e["id"], e["kind"], e["label"], e["status"], int(e["accepted"]), e["start"]["boot_id"], e["start"]["device_us_estimate"], e.get("end", {}).get("device_us_estimate", ""), e.get("duration_s", ""), ";".join(e.get("quality", {}).get("issues", []))))
        self.meta.update(status="complete", finished_local=datetime.now().astimezone().isoformat(), stats=self.stats,
                         accepted_counts=self.snapshot()["counts"], accepted_background_seconds=self.snapshot()["background_s"])
        save_json(self.folder / "session.json", self.meta)
        archive = self.folder.parent / ("Milo_Candidate_Data_" + self.folder.name + ".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for file in sorted(self.folder.rglob("*")):
                if file.is_file() and file.suffix != ".tmp":
                    z.write(file, file.relative_to(self.folder))
        return archive


class Connection:
    def __init__(self, kind, address, on_frame, on_status, udp_port=25400):
        self.kind, self.address, self.udp_port = kind, address, udp_port
        self.on_frame, self.on_status = on_frame, on_status
        self.stop_event = threading.Event()
        self.handle = None

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.handle is not None:
            try:
                if hasattr(self.handle, "cancel_read"): self.handle.cancel_read()
                self.handle.close()
            except (OSError, AttributeError): pass

    def run(self):
        try:
            if self.kind == "USB":
                import serial
                self.handle = serial.Serial(self.address, 230400, timeout=.25)
                self.on_status("Connected to USB. Waiting for the logger stream...")
            else:
                self.handle = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.handle.bind(("0.0.0.0", self.udp_port)); self.handle.settimeout(.25)
                self.on_status(f"Listening for glove Wi-Fi data on UDP {self.udp_port}...")
            started, seen = time.monotonic(), False
            while not self.stop_event.is_set():
                try:
                    packet = self.handle.readline() if self.kind == "USB" else self.handle.recvfrom(2048)[0]
                except socket.timeout:
                    continue
                frame = parse_packet(packet, self.kind)
                if frame is not None:
                    seen = True
                    self.on_frame(frame)
                elif self.kind == "USB" and not seen and time.monotonic() - started > 12:
                    raise RuntimeError("No MILO1 logger stream. Check the COM port, flash GloveCandidateLogger and close Serial Monitor.")
        except Exception as error:
            if not self.stop_event.is_set(): self.on_status("Connection error: " + str(error))
        finally:
            self.stop()


def configure_wifi(port, ssid, password, host, udp_port=25400):
    import serial
    socket.inet_aton(host)
    with serial.Serial(port, 230400, timeout=.25) as link:
        # Opening USB can reset the ESP; wait for the logger instead of sending into the bootloader.
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if parse_packet(link.readline(), "USB") is not None:
                break
        else:
            raise RuntimeError("No logger stream. Flash GloveCandidateLogger and close Serial Monitor.")
        command = json.dumps({"cmd": "wifi", "ssid": ssid, "password": password, "host": host, "port": udp_port})
        link.write((command + "\n").encode("utf-8")); link.flush()
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            line = link.readline()
            if line.startswith(b"#CONFIG_OK"): return
            if line.startswith(b"#CONFIG_ERROR"): raise RuntimeError("Glove rejected Wi-Fi settings.")
        raise RuntimeError("No configuration acknowledgement. Check USB and try again.")
