"""Fast glove-only annotation UI. Space starts/finishes; streaming never pauses."""
from collections import deque
import ipaddress
import math
import os
from pathlib import Path
import queue
import socket
import threading
import time
import tkinter as tk
from tkinter import ttk

from collector_core import ACTIVITIES, CLASSES, Connection, Session, configure_wifi

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "datasets"
NAVY, BLUE, GREEN, RED, MUTED = "#10213d", "#2563eb", "#15803d", "#b91c1c", "#64748b"
SHORT = ("Come", "Sit", "Paw", "Spin", "Bang", "Overhand", "Underhand")


def local_ips():
    try:
        ips = {x[4][0] for x in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
        ips = [ip for ip in ips if not ip.startswith(("127.", "169.254."))]
        return sorted(ips, key=lambda ip: (not ip.startswith("172.20."), not ip.startswith("192.168."), not ip.startswith("10."), ip)) or ["127.0.0.1"]
    except OSError:
        return ["127.0.0.1"]


class App:
    def __init__(self, root):
        self.root = root
        root.title("Milo • Automatic gesture detector — data collection")
        root.geometry("1180x740"); root.minsize(1020, 700)
        root.configure(bg="#f3f6fb")
        self.lock = threading.RLock()
        self.messages = queue.Queue()
        self.session = None
        self.last_session = None
        self.link = None
        self.token = None
        self.latest = None
        self.history = deque(maxlen=200)
        self.selected = 0
        self.space_down = False
        self.last_toggle = 0
        self.closing = False
        self.exports_pending = 0
        self.last_table = None
        self.last_zip = None
        self.transport = tk.StringVar(value="USB")
        self.port = tk.StringVar()
        self.host = tk.StringVar(value=local_ips()[0])
        self.participant = tk.StringVar(value="Nitin")
        self.split = tk.StringVar(value="training")
        self.mode = tk.StringVar(value="gesture")
        self.activity = tk.StringVar(value=ACTIVITIES[0])
        self.target = tk.IntVar(value=10)
        self.auto = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Flash GloveCandidateLogger once, close Serial Monitor, then connect.")
        self.saved = tk.StringVar(value="ZIP location will appear here after End session & ZIP.")
        self.build()
        self.refresh_ports()
        root.bind("<KeyPress-space>", self.key_space)
        root.bind("<KeyRelease-space>", self.release_space)
        root.bind_class("TButton", "<KeyPress-space>", self.key_space)
        root.bind_class("TButton", "<KeyRelease-space>", self.release_space)
        root.bind_class("Button", "<KeyPress-space>", self.key_space)
        root.bind_class("Button", "<KeyRelease-space>", self.release_space)
        root.bind("<Escape>", self.cancel)
        root.bind("<BackSpace>", self.undo_key)
        for i in range(7):
            root.bind(str(i + 1), lambda e, n=i: self.number_key(e, n))
        root.bind("<FocusOut>", lambda e: setattr(self, "space_down", False))
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.poll()

    def build(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names(): style.theme_use("clam")
        style.configure("TFrame", background="#f3f6fb")
        style.configure("TLabel", background="#f3f6fb", foreground=NAVY, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(8, 4))
        style.configure("Selected.TButton", background=BLUE, foreground="white")
        style.map("Selected.TButton", background=[("active", "#1d4ed8")], foreground=[("active", "white")])
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=25)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        main = ttk.Frame(self.root, padding=14); main.pack(fill="both", expand=True)
        ttk.Label(main, text="Collect naturally. No countdowns.", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(main, text="Space → do the action → Space. Repeat immediately. No fist trigger, microphone or playback.", foreground=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 8))

        network = ttk.Frame(main); network.pack(fill="x")
        ttk.Label(network, text="Connection").pack(side="left")
        ttk.Combobox(network, textvariable=self.transport, values=("USB", "Wi-Fi"), width=8, state="readonly").pack(side="left", padx=6)
        self.port_box = ttk.Combobox(network, textvariable=self.port, width=10, state="readonly"); self.port_box.pack(side="left")
        ttk.Button(network, text="Refresh", command=self.refresh_ports, takefocus=False).pack(side="left", padx=5)
        self.connect_button = ttk.Button(network, text="Connect", command=self.connect, takefocus=False); self.connect_button.pack(side="left", padx=5)
        ttk.Label(network, text="Laptop IP").pack(side="left", padx=(12, 4))
        self.ip_box = ttk.Combobox(network, textvariable=self.host, values=local_ips(), width=16); self.ip_box.pack(side="left")
        ttk.Button(network, text="Set up Wi-Fi via USB", command=self.wifi_dialog, takefocus=False).pack(side="right")
        options = ttk.Frame(main); options.pack(fill="x", pady=(6, 6))
        ttk.Label(options, text="Wearer").pack(side="left")
        ttk.Entry(options, textvariable=self.participant, width=15).pack(side="left", padx=6)
        ttk.Label(options, text="Session role").pack(side="left", padx=(10, 0))
        ttk.Combobox(options, textvariable=self.split, values=("training", "validation", "final_test"), width=13, state="readonly").pack(side="left", padx=6)
        ttk.Button(options, text="New session", command=self.new_session, takefocus=False).pack(side="left", padx=8)
        ttk.Button(options, text="End session & ZIP", command=self.end_session, takefocus=False).pack(side="right")
        live = ttk.Frame(main); live.pack(fill="x", pady=(0, 8))
        self.sensor_text = ttk.Label(live, text="Thumb —     Index —     Middle —", font=("Segoe UI", 11, "bold")); self.sensor_text.pack(side="left")
        self.health_text = ttk.Label(live, text="No sensor data", foreground=MUTED); self.health_text.pack(side="right")

        modes = ttk.Frame(main); modes.pack(fill="x", pady=(2, 8))
        for text, value in [("Gesture takes", "gesture"), ("Everyday activity / non-command", "background")]:
            ttk.Radiobutton(modes, text=text, variable=self.mode, value=value, command=self.mode_changed).pack(side="left", padx=(0, 20))
        ttk.Label(modes, text="Target / gesture:").pack(side="left")
        ttk.Spinbox(modes, from_=1, to=200, textvariable=self.target, width=4).pack(side="left", padx=5)
        ttk.Checkbutton(modes, text="Advance automatically", variable=self.auto).pack(side="right")
        choices = ttk.Frame(main); choices.pack(fill="x")
        self.class_buttons = []
        for i, (_, title, _) in enumerate(CLASSES):
            b = ttk.Button(choices, text=f"{i + 1}. {SHORT[i]}", command=lambda n=i: self.choose(n), takefocus=False)
            b.grid(row=0, column=i, sticky="ew", padx=(0, 4), pady=2)
            self.class_buttons.append(b)
        for i in range(7): choices.columnconfigure(i, weight=1)
        bg = ttk.Frame(main); bg.pack(fill="x", pady=(5, 0))
        self.bg_frame = bg
        ttk.Label(bg, text="Everyday activity label:").pack(side="left")
        ttk.Combobox(bg, textvariable=self.activity, values=ACTIVITIES, width=25, state="readonly").pack(side="left", padx=8)
        ttk.Label(bg, text="Record ordinary movement, not deliberate commands.", foreground=MUTED).pack(side="left")

        self.instruction = ttk.Label(main, text="", font=("Segoe UI", 11), wraplength=1080)
        self.instruction.pack(anchor="w", pady=(7, 4))
        controls = ttk.Frame(main); controls.pack(fill="x")
        self.record_button = tk.Button(controls, text="Start action [Space]", command=self.toggle, bg=BLUE, fg="white",
                                       activebackground="#1d4ed8", activeforeground="white", relief="flat", bd=0,
                                       font=("Segoe UI", 14, "bold"), padx=20, pady=8, takefocus=False)
        self.record_button.pack(side="left", fill="x", expand=True)
        ttk.Button(controls, text="Cancel [Esc]", command=self.cancel, takefocus=False).pack(side="left", padx=8)
        ttk.Button(controls, text="Undo last [Backspace]", command=self.undo, takefocus=False).pack(side="left")
        self.progress = ttk.Label(main, text="0 gesture takes • 0:00 everyday activity", font=("Segoe UI", 10, "bold"))
        self.progress.pack(anchor="w", pady=(6, 4))
        self.canvas = tk.Canvas(main, height=104, background="white", highlightthickness=1, highlightbackground="#dbe3ee")
        self.canvas.pack(fill="x", pady=(0, 8))
        self.table = ttk.Treeview(main, columns=("label", "kind", "duration", "status"), show="headings", height=3, selectmode="browse")
        for key, title, width in [("label", "Recent recordings", 240), ("kind", "Type", 120), ("duration", "Seconds", 80), ("status", "Quality / status", 370)]:
            self.table.heading(key, text=title); self.table.column(key, width=width)
        self.table.pack(fill="both", expand=True)
        footer = ttk.Frame(main); footer.pack(fill="x", pady=(5, 0))
        ttk.Button(footer, text="Discard selected take", command=self.discard_selected, takefocus=False).pack(side="left")
        ttk.Button(footer, text="Open data folder", command=self.open_folder, takefocus=False).pack(side="right")
        self.status_label = ttk.Label(main, textvariable=self.status, foreground=BLUE, wraplength=1100, font=("Segoe UI", 9))
        self.status_label.pack(fill="x", pady=(6, 2))
        self.saved_label = ttk.Label(main, textvariable=self.saved, foreground=MUTED, wraplength=1100, font=("Segoe UI", 9))
        self.saved_label.pack(fill="x")
        self.choose(0)

    def refresh_ports(self):
        try:
            from serial.tools import list_ports
            values = [p.device for p in list_ports.comports()]
        except ImportError:
            values = []
        self.port_box.configure(values=values)
        if self.port.get() not in values: self.port.set(values[0] if values else "")

    def new_session(self):
        if self.session is not None:
            self.notice("This session is already recording continuously. End & ZIP before starting another.")
            return
        participant = self.participant.get().strip()
        if not participant:
            self.notice("Enter the wearer's name first.", True); return
        try:
            session = Session(RESULTS, participant, self.split.get(), self.transport.get())
        except OSError as error:
            self.notice(f"Cannot create dataset folder: {error}", True); return
        with self.lock: self.session = session
        self.last_session = session
        self.last_table = None
        self.saved.set("Saving continuously: " + str(session.folder))
        self.notice("New session ready. Connect, then Space → action → Space. There is no countdown.")

    def receive(self, token, frame):
        with self.lock:
            if token is not self.token: return
            self.latest = frame; self.history.append(frame)
            session = self.session
        if session is not None: session.ingest(frame)

    def connect(self):
        if self.link is not None:
            with self.lock: self.token = None
            self.link.stop(); self.link = None
            self.connect_button.configure(text="Connect")
            self.notice("Disconnected. Completed takes stay saved; reconnect or End session & ZIP.")
            return
        if self.transport.get() == "USB" and not self.port.get():
            self.notice("Choose the glove USB port. Refresh if needed.", True); return
        if self.session is None: self.new_session()
        if self.session is None: return
        token = object()
        with self.lock: self.token = token; self.latest = None; self.history.clear()
        self.link = Connection(self.transport.get(), self.port.get(), lambda f: self.receive(token, f),
                               lambda text: self.messages.put(("status", token, text)))
        self.link.start(); self.connect_button.configure(text="Disconnect")

    def notice(self, text, bad=False):
        self.status.set(text); self.status_label.configure(foreground=RED if bad else BLUE)

    def choose(self, index):
        if self.session and self.session.active:
            self.notice("Finish the current segment first, or press Esc to cancel it.", True); return
        self.selected = index; self.mode.set("gesture")
        self.bg_frame.pack_forget()
        for i, button in enumerate(self.class_buttons): button.configure(style="Selected.TButton" if i == index else "TButton")
        self.instruction.configure(text=CLASSES[index][2])

    def mode_changed(self):
        if self.session and self.session.active:
            self.mode.set(self.session.active["kind"])
            self.notice("Finish or cancel the current segment before changing mode.", True); return
        if self.mode.get() == "background":
            self.bg_frame.pack(fill="x", pady=(5, 0), before=self.instruction)
            self.instruction.configure(text="Start once, do ordinary activities for as long as you like, then finish. No fixed recording length.")
        else:
            self.bg_frame.pack_forget()
            self.instruction.configure(text=CLASSES[self.selected][2])

    def toggle(self):
        now = time.monotonic()
        if now - self.last_toggle < .18: return
        self.last_toggle = now
        if self.session is None: self.new_session()
        if self.session is None: return
        try:
            if self.session.active:
                e = self.session.finish()
                if e["accepted"]:
                    self.notice(f"Saved {e['label']} ({e['duration_s']:.2f}s). Start the next one immediately.")
                    if e["kind"] == "gesture" and self.auto.get():
                        counts = self.session.snapshot()["counts"]
                        try: target = max(1, self.target.get())
                        except tk.TclError: target = 10
                        if counts[e["label"]] >= target:
                            next_index = next((i for i, (c, _, _) in enumerate(CLASSES) if counts[c] < target), None)
                            if next_index is None:
                                self.mode.set("background"); self.mode_changed()
                                self.notice("Gesture target reached. Now record ordinary activities, or End session & ZIP.")
                            else: self.choose(next_index)
                else:
                    reason = e.get("reason") or ", ".join(e.get("quality", {}).get("issues", []))
                    self.notice("Not counted: " + reason + ". Raw readings kept. Try again.", True)
            else:
                kind = self.mode.get()
                label = CLASSES[self.selected][0] if kind == "gesture" else self.activity.get()
                self.session.start(kind, label)
                self.notice("Recording " + label + ". Perform it now, then press Space to finish.")
        except (ValueError, OSError) as error:
            self.notice(str(error), True)

    def cancel(self, event=None):
        if self.session:
            self.session.cancel()
            self.notice("Segment cancelled. Raw stream kept. Ready for the next take.")
        return "break"

    def undo(self):
        if not self.session: return
        event = self.session.discard()
        if event:
            if event["kind"] == "gesture": self.choose(next(i for i, c in enumerate(CLASSES) if c[0] == event["label"]))
            self.notice("Last segment discarded. Its raw readings remain in the stream.")

    def discard_selected(self):
        if self.session and self.table.selection():
            event = self.session.discard(self.table.selection()[0])
            if event: self.notice("Selected segment discarded. Raw readings retained.")

    def is_typing(self):
        widget = self.root.focus_get()
        return widget is not None and (widget.winfo_toplevel() != self.root or widget.winfo_class() in
            ("Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox", "TRadiobutton", "TCheckbutton"))

    def key_space(self, event):
        if self.is_typing(): return None
        if not self.space_down:
            self.space_down = True; self.toggle()
        return "break"

    def release_space(self, event):
        self.space_down = False
        return None if self.is_typing() else "break"

    def undo_key(self, event):
        if self.is_typing(): return None
        self.undo(); return "break"

    def number_key(self, event, index):
        if self.is_typing(): return None
        self.choose(index); return "break"

    def end_session(self, close_after=False):
        with self.lock:
            session = self.session; self.session = None
        if session is None:
            if close_after and not self.exports_pending: self.root.destroy()
            return
        try:
            if session.active and not close_after:
                session.finish()
            session.close_input()
        except OSError as error:
            with self.lock: self.session = session
            self.closing = False
            self.notice("Could not finish saving: " + str(error) + ". Raw folder: " + str(session.folder), True)
            return
        self.last_session = session
        self.exports_pending += 1
        self.notice("Saving ZIP in the background. You can start another session immediately.")
        def work():
            try: self.messages.put(("exported", session.export()))
            except Exception as error: self.messages.put(("export_error", str(error), str(session.folder)))
        threading.Thread(target=work, daemon=False).start()

    def open_folder(self):
        RESULTS.mkdir(exist_ok=True)
        os.startfile(str(self.last_session.folder if self.last_session else RESULTS))

    def wifi_dialog(self):
        if self.link is not None:
            self.notice("Disconnect first for the one-time Wi-Fi setup, then use the glove USB cable.", True); return
        win = tk.Toplevel(self.root); win.title("One-time Wi-Fi setup"); win.geometry("570x450"); win.resizable(False, False)
        box = ttk.Frame(win, padding=20); box.pack(fill="both", expand=True)
        ttk.Label(box, text="Keep glove USB attached for setup", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ssid, password = tk.StringVar(), tk.StringVar()
        for row, (title, variable, hidden) in enumerate([("USB port", self.port, False), ("Wi-Fi / hotspot name", ssid, False), ("Wi-Fi password", password, True), ("Laptop Wi-Fi IP", self.host, False)], 1):
            ttk.Label(box, text=title).grid(row=row, column=0, sticky="w", pady=5)
            if row == 1:
                widget = ttk.Combobox(box, textvariable=variable, values=self.port_box.cget("values"), state="readonly", width=25)
            else: widget = ttk.Entry(box, textvariable=variable, show="•" if hidden else "", width=27)
            widget.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=5)
        ttk.Label(box, text="Saved on the glove, not in your dataset. Both devices must use the same local network.", wraplength=460, foreground=MUTED).grid(row=5, column=0, columnspan=2, sticky="w", pady=10)
        info = ttk.Label(box, text=""); info.grid(row=7, column=0, columnspan=2, sticky="w")
        def send():
            try:
                ipaddress.IPv4Address(self.host.get())
                if not self.port.get() or not ssid.get(): raise ValueError("Enter a USB port and Wi-Fi name.")
            except ValueError as error: info.configure(text=str(error)); return
            button.configure(state="disabled"); info.configure(text="Configuring glove… this does not block the main window.")
            values = self.port.get(), ssid.get(), password.get(), self.host.get()
            def work():
                try:
                    configure_wifi(*values)
                    self.messages.put(("wifi_ok", win))
                except Exception as error: self.messages.put(("wifi_error", win, info, button, str(error)))
            threading.Thread(target=work, daemon=True).start()
        button = ttk.Button(box, text="Save to glove & use Wi-Fi", command=send, takefocus=False)
        button.grid(row=6, column=0, columnspan=2, sticky="ew")

    def draw(self, frames):
        canvas = self.canvas; canvas.delete("all")
        w, h = max(canvas.winfo_width(), 500), max(canvas.winfo_height(), 100)
        canvas.create_text(9, 11, text="Live wrist motion + finger states (last 4 seconds)", anchor="w", fill=MUTED, font=("Segoe UI", 9))
        if len(frames) < 2: return
        boot = frames[-1].boot; frames = [f for f in frames if f.boot == boot]
        if len(frames) < 2: return
        end = frames[-1].device_us; start = end - 4_000_000
        magnitudes = [math.sqrt(sum(v * v for v in f.features[3:6])) for f in frames]
        scale = max(2., max(magnitudes))
        points = []
        for f, magnitude in zip(frames, magnitudes):
            x = 110 + (w - 125) * (f.device_us - start) / 4_000_000
            if x >= 110: points.extend((x, 53 - 30 * magnitude / scale))
        if len(points) >= 4: canvas.create_line(points, fill=BLUE, width=2)
        for i, (name, color) in enumerate([("Thumb", "#0f766e"), ("Index", "#7c3aed"), ("Middle", "#c2410c")]):
            y = 62 + i * 15
            canvas.create_text(9, y, text=name + " bent", anchor="w", fill=color, font=("Segoe UI", 9))
            line = []
            for f in frames:
                x = 110 + (w - 125) * (f.device_us - start) / 4_000_000
                if x >= 110: line.extend((x, y - 7 if f.features[6 + i] else y + 3))
            if len(line) >= 4: canvas.create_line(line, fill=color, width=2)

    def poll(self):
        while True:
            try: message = self.messages.get_nowait()
            except queue.Empty: break
            if message[0] == "status" and message[1] is self.token:
                self.notice(message[2], message[2].startswith("Connection error"))
                if message[2].startswith("Connection error") and self.link:
                    self.link.stop(); self.link = None; self.token = None; self.connect_button.configure(text="Connect")
            elif message[0] == "exported":
                self.exports_pending -= 1; self.last_zip = message[1]
                self.saved.set("SEND THIS ZIP: " + str(message[1]))
                self.notice("ZIP saved. Send it for detector training when collection is complete.")
            elif message[0] == "export_error":
                self.exports_pending -= 1
                self.notice("ZIP export failed: " + message[1] + ". Raw files remain at " + message[2], True)
            elif message[0] == "wifi_ok":
                if message[1].winfo_exists(): message[1].destroy()
                self.transport.set("Wi-Fi")
                if self.link is None: self.connect()
            elif message[0] == "wifi_error":
                _, win, info, button, error = message
                if win.winfo_exists(): info.configure(text=error, wraplength=460); button.configure(state="normal")
        with self.lock:
            latest = self.latest; frames = list(self.history); session = self.session or self.last_session
        snapshot = session.snapshot() if session else None
        if latest:
            self.sensor_text.configure(text="     ".join(f"{name}: {latest.raw[i]} / {'BENT' if latest.features[6+i] else 'OPEN'}" for i, name in enumerate(("Thumb", "Index", "Middle"))))
            age = (time.monotonic_ns() - latest.host_ns) / 1e6
            healthy = latest.imu_ok and not latest.rails and not latest.clipped and age < 500
            missing = snapshot["stats"]["missing_samples"] if snapshot else 0
            flags = "FLEX RAIL" if latest.rails else "3 fingers"
            if latest.clipped: flags += " / CLIPPED"
            self.health_text.configure(text=f"{'LIVE' if age < 500 else 'STALE'} • IMU {'OK' if latest.imu_ok else 'ERROR'} • {flags} • gaps {missing}", foreground=GREEN if healthy else RED)
        self.draw(frames)
        active = snapshot["active"] if snapshot else None
        if active:
            elapsed = (time.monotonic_ns() - active["start"]["host_monotonic_ns"]) / 1e9
            self.record_button.configure(text=f"Finish & save [Space]   •   {elapsed:.1f}s", bg=GREEN, activebackground="#166534")
        else:
            self.record_button.configure(text="Start everyday activity [Space]" if self.mode.get() == "background" else "Start action [Space]", bg=BLUE, activebackground="#1d4ed8")
        if snapshot:
            counts = snapshot["counts"]; seconds = int(snapshot["background_s"])
            self.progress.configure(text=f"{sum(counts.values())} gesture takes • {seconds//60}:{seconds%60:02d} everyday activity    |    " + "   ".join(f"{c.replace('throw_', '')}: {n}" for c, n in counts.items()))
            for i, (c, title, _) in enumerate(CLASSES): self.class_buttons[i].configure(text=f"{i+1}. {SHORT[i]} [{counts[c]}]")
            signature = tuple((e["id"], e["status"], e.get("duration_s")) for e in snapshot["events"])
            if signature != self.last_table:
                self.last_table = signature
                self.table.delete(*self.table.get_children())
                for e in reversed(snapshot["events"]):
                    issues = ", ".join(e.get("quality", {}).get("issues", []))
                    quality = e["status"] + (" • " + issues if issues else "")
                    self.table.insert("", "end", iid=e["id"], values=(e["label"], e["kind"], e.get("duration_s", "—"), quality))
        if self.closing and not self.exports_pending:
            self.root.destroy(); return
        self.root.after(50, self.poll)

    def on_close(self):
        if self.closing: return
        self.closing = True
        if self.link: self.token = None; self.link.stop(); self.link = None
        self.end_session(close_after=True)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
