"""USB-only raw flex calibration. Does not alter any firmware thresholds."""
import argparse
import csv
import json
import math
from pathlib import Path
import re
import statistics
import time
from datetime import datetime
import zipfile

NAMES = ("thumb", "index", "middle")
PATTERN = re.compile(r"Thumb:\s*(\d+)\s+Index:\s*(\d+)\s+Middle:\s*(\d+)")
BASE = Path(__file__).resolve().parent


def percentile(values, p):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def analyse(rows):
    result = {}
    for name in NAMES:
        opened = [r[name] for r in rows if r["pose"] == "relaxed"]
        closed = [r[name] for r in rows if r["pose"] == "fist"]
        increases = statistics.median(closed) >= statistics.median(opened)
        sign = 1 if increases else -1
        upper_open = percentile([sign * v for v in opened], .98)
        lower_bent = percentile([sign * v for v in closed], .02)
        gap = lower_bent - upper_open
        rails = sum(v <= 20 or v >= 4075 for v in opened + closed)
        # Compare the worst repeats as well as the pooled distributions.
        repeat_gaps = []
        for repeat in sorted({r["repeat"] for r in rows}):
            a = [sign * r[name] for r in rows if r["repeat"] == repeat and r["pose"] == "relaxed"]
            b = [sign * r[name] for r in rows if r["repeat"] == repeat and r["pose"] == "fist"]
            repeat_gaps.append(round(percentile(b, .02) - percentile(a, .98), 2))
        status = "separated" if gap >= 8 and min(repeat_gaps) >= 8 and rails == 0 else "needs_review"
        thresholds = None
        if status == "separated":
            release = round(sign * (upper_open + .25 * gap))
            bend = round(sign * (upper_open + .55 * gap))
            thresholds = {"bend": bend, "release": release, "increases": increases}
        result[name] = {
            "status": status,
            "relaxed": {"min": min(opened), "median": statistics.median(opened), "max": max(opened)},
            "fist": {"min": min(closed), "median": statistics.median(closed), "max": max(closed)},
            "separation_adc": round(gap, 2),
            "repeat_separations_adc": repeat_gaps,
            "rail_samples": rails,
            "suggested_thresholds": thresholds,
        }
    return result


def read_sample(port):
    match = PATTERN.search(port.readline().decode("utf-8", errors="replace"))
    if not match:
        return None
    values = tuple(map(int, match.groups()))
    return values if all(0 <= v <= 4095 for v in values) else None


def collect_pose(port, pose, repeat, folder, rows):
    instruction = ("RELAX your hand naturally; don't force the fingers straight."
                   if pose == "relaxed" else
                   "Make a NORMAL COMFORTABLE FIST; don't squeeze extra hard.")
    while True:
        print(f"\nRound {repeat}/3 - {instruction}")
        input("Get into position, then press Enter and hold still for about 5 seconds...")
        # Discard queued pre-pose values and the settling interval.
        port.reset_input_buffer()
        until = time.monotonic() + .7
        while time.monotonic() < until:
            read_sample(port)
        port.reset_input_buffer()
        print("Recording... hold this pose.", flush=True)
        start = time.monotonic()
        take = []
        while time.monotonic() - start < 4:
            values = read_sample(port)
            if values is not None:
                take.append({"repeat": repeat, "pose": pose,
                             "elapsed_ms": round((time.monotonic() - start) * 1000),
                             **dict(zip(NAMES, values))})
        if len(take) < 25:
            print(f"Only {len(take)} readings received. Check USB / correct sketch; repeating this pose.")
            continue
        rows.extend(take)
        # Save after each pose so an interrupted session still retains raw readings.
        with (folder / "readings.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=("repeat", "pose", "elapsed_ms", *NAMES))
            writer.writeheader()
            writer.writerows(rows)
        summary = "  ".join(f"{n}: {int(statistics.median(r[n] for r in take))}" for n in NAMES)
        print(f"Saved {len(take)} readings. Medians: {summary}")
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="USB serial port, for example COM5")
    args = parser.parse_args()
    import serial
    from serial.tools import list_ports
    port_name = args.port
    if not port_name:
        ports = list(list_ports.comports())
        if not ports:
            raise RuntimeError("No serial ports found. Connect the glove using a USB data cable.")
        for i, p in enumerate(ports, 1):
            print(f"{i}: {p.device} - {p.description}")
        if len(ports) == 1:
            port_name = ports[0].device
        else:
            choice = input("Enter the glove's port number from this list: ").strip()
            if not choice.isdigit() or not 1 <= int(choice) <= len(ports):
                raise RuntimeError("Invalid port selection. Run again and choose its list number.")
            port_name = ports[int(choice) - 1].device
    print(f"\nOpening {port_name} at 115200. Close Arduino Serial Monitor first.")
    rows = []
    with serial.Serial(port_name, 115200, timeout=.25) as port:
        deadline = time.monotonic() + 10
        while read_sample(port) is None:
            if time.monotonic() >= deadline:
                raise RuntimeError("No flex readings. Flash Flex_USB_Calibration.ino and check the port.")
        folder = BASE / "results" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        folder.mkdir(parents=True)
        print("\nWear the glove as you normally use it. Keep USB connected.")
        print("Three rounds: relaxed hand, then comfortable fist. No MQTT or mic needed.")
        for repeat in range(1, 4):
            for pose in ("relaxed", "fist"):
                collect_pose(port, pose, repeat, folder, rows)
    results = analyse(rows)
    report = ["USB flex calibration - suggested thresholds only; no demo files changed.",
              "12-bit ADC, 11 dB attenuation, 8-read average; GPIO35/34/39.",
              "Repeat measurements do not rule out an intermittent wiring/sensor fault.", ""]
    for name, value in results.items():
        a, b = value["relaxed"], value["fist"]
        report.append(f"{name.upper()}: relaxed {a['min']}..{a['max']}; fist {b['min']}..{b['max']}")
        if value["suggested_thresholds"]:
            t = value["suggested_thresholds"]
            report.append(f"  Suggested bend={t['bend']}, release={t['release']}; increases={t['increases']}")
        else:
            report.append("  NEEDS REVIEW: overlapping/narrow ranges, inconsistent repeats or ADC rail values.")
        report.append(f"  Separation={value['separation_adc']} ADC counts; repeat gaps={value['repeat_separations_adc']}")
    metadata = {"created_local": datetime.now().astimezone().isoformat(), "port": port_name,
                "samples": len(rows), "pose_seconds": 4, "rounds": 3, "pins": [35, 34, 39],
                "method": "P98 relaxed / P02 fist, in bend direction; release at 25%, bend at 55% of gap",
                "thresholds_applied": False, "sensors": results}
    (folder / "calibration.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (folder / "summary.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    archive = folder.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for file in sorted(folder.iterdir()):
            z.write(file, file.name)
    print("\n" + "\n".join(report))
    print(f"\nSEND THIS ZIP:\n{archive}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped. Any completed poses remain saved under results.")
    except Exception as error:
        print(f"\nERROR: {error}")
        raise SystemExit(1)
