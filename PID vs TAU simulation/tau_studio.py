import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import pandas as pd
import numpy as np
import subprocess
import os
import threading
import queue
import time

# ==============================================================================
# GLOBAL SETTINGS
# ==============================================================================
plt.rcParams.update({
    'font.size': 11, 'axes.titlesize': 14, 'axes.labelsize': 12,
    'xtick.labelsize': 10, 'ytick.labelsize': 10, 'legend.fontsize': 11
})

# ==============================================================================
# 0. ROBUST TAU LOGIC
# ==============================================================================

TAU_CODE_ONE_LINER = ("set charvar off\ni1 : bv[8] = in console\no1 : bv[8] = out console\nrun always ((i1[t] > { #x50 }:bv[8]) ? (o1[t] = o1[t-1]) : ((i1[t] < { #x14 }:bv[8]) ? (o1[t] = { #x64 }:bv[8]) : (((o1[t-1] = { #x64 }:bv[8]) && (i1[t] < { #x1E }:bv[8])) ? (o1[t] = { #x64 }:bv[8]) : ((i1[t] < { #x2D }:bv[8]) ? (o1[t] = { #x3C }:bv[8]) : ((i1[t] > { #x37 }:bv[8]) ? (o1[t] = { #x28 }:bv[8]) : (o1[t] = { #x32 }:bv[8]))))))\n")

# ==============================================================================
# 0. ROBUST TAU LOGIC (SCALED FOR INT(VOL * 100))
# Target = 0.5 Flow -> Input 50 (0x32)
# ==============================================================================

## To be tested,

# TAU_CODE_ONE_LINER = (
#     "set charvar off\n"
#     "i1 : bv[8] = in console\n"
#     "o1 : bv[8] = out console\n"
#     "run always ("
#     # LAYER 1: FAULT PROTECTION
#     # If Input > 1.1 (0x6E) and history was normal (< 0.7 / 0x46), ignore glitch.
#     "((i1[t] > { #x6E }:bv[8]) && (i1[t-1] < { #x46 }:bv[8])) ? (o1[t] = o1[t-1]) : "
    
#     # LAYER 2: DEADBAND (STABILITY)
#     # If Input is 0.48 - 0.52 (0x30 - 0x34), hold steady power (0x32).
#     "((i1[t] >= { #x30 }:bv[8]) && (i1[t] <= { #x34 }:bv[8])) ? (o1[t] = { #x32 }:bv[8]) : "
    
#     # LAYER 3: CRITICAL RESPONSE
#     # > 0.8 (0x50) -> Cut Power (0x00)
#     "(i1[t] > { #x50 }:bv[8]) ? (o1[t] = { #x00 }:bv[8]) : "
    
#     # > 0.6 (0x3C) -> Low Power (0x19 / 25)
#     "(i1[t] > { #x3C }:bv[8]) ? (o1[t] = { #x19 }:bv[8]) : "
    
#     # < 0.2 (0x14) -> Max Power (0x64 / 100)
#     "(i1[t] < { #x14 }:bv[8]) ? (o1[t] = { #x64 }:bv[8]) : "
    
#     # < 0.4 (0x28) -> High Power (0x4B / 75)
#     "(i1[t] < { #x28 }:bv[8]) ? (o1[t] = { #x4B }:bv[8]) : "
    
#     # DEFAULT: Neutral/Maintenance Power (0x32 / 50)
#     "(o1[t] = { #x32 }:bv[8])"
#     ")\n"
# )


# ==============================================================================
# 1. PHYSICS & CONTROL CLASSES
# ==============================================================================
class PistonPump:
    def __init__(self): self.amp = 0.0
    def update(self, target, noise, load):
        self.amp += (target - self.amp) * 0.5
        return max(0, (self.amp * 0.1 * load) + noise)

class PID:
    def __init__(self, kp, ki, kd, clamp):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.clamp, self.prev_err, self.integral = clamp, 0, 0
    def compute(self, setpoint, measure):
        err = setpoint - measure
        self.integral += err
        if self.clamp: self.integral = max(-50, min(50, self.integral))
        p = self.kp * err
        i = self.ki * self.integral
        d = self.kd * (err - self.prev_err)
        self.prev_err = err
        return p + i + d

# ==============================================================================
# 2. DEBUG CONSOLE WIDGET
# ==============================================================================
class DebugConsole(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.text = scrolledtext.ScrolledText(self, height=12, bg="black", fg="#00ff00", font=("Consolas", 9))
        self.text.pack(fill=tk.BOTH, expand=True)
        self.log(">>> TAU CONSOLE READY")

    def log(self, msg, color=None):
        tag = "normal"
        if color == "red":
            self.text.tag_config("err", foreground="#ff5555")
            tag = "err"
        elif color == "cyan":
            self.text.tag_config("tx", foreground="#55ffff")
            tag = "tx"
            
        self.text.insert(tk.END, msg + "\n", tag)
        self.text.see(tk.END)
        # self.text.update_idletasks() # Optional: Un-comment if you want live updates (slower)
        
    def clear(self):
        self.text.delete('1.0', tk.END)

# ==============================================================================
# 3. TAU INTERFACE (FLIGHT RECORDER MODE)
# ==============================================================================
class TauInterface:
    def __init__(self, exe_path):
        self.valid = False
        self.process = None
        self.output_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.full_log = [] # FLIGHT RECORDER: Stores everything
        
        if not exe_path or not os.path.exists(exe_path):
            self.full_log.append("![Sys] Tau executable not found.")
            return

        try:
            # 1. Launch
            self.process = subprocess.Popen(
                [exe_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=0
            )
            # Start Reader Thread
            threading.Thread(target=self._reader_thread, daemon=True).start()

            # 2. Handshake
            self.full_log.append("![Sys] Waiting for 'tau>' prompt...")
            if not self._wait_for_log_pattern("tau>", 5.0):
                self.full_log.append("![Err] Prompt timeout. Is Tau running?")
                # We continue anyway, sometimes prompt gets eaten.

            # 3. Send Logic
            self.full_log.append("![Sys] Sending Logic Spec...")
            self.process.stdin.write(TAU_CODE_ONE_LINER)
            self.process.stdin.flush()
            
            # 4. Wait for Execution Start
            if self._wait_for_log_pattern(["Execution step", "Please provide"], 10.0):
                self.valid = True
                self.full_log.append("![Sys] Logic Accepted. Simulation Started.")
            else:
                self.full_log.append("![Err] Logic Rejected (Syntax Error or Timeout).")
                self.close()

        except Exception as e:
            self.full_log.append(f"![Exc] Init Error: {e}")

    def _reader_thread(self):
        """Reads stdout char by char or line by line and stores it."""
        while not self.stop_event.is_set():
            try:
                line = self.process.stdout.readline()
                if not line: break
                self.output_queue.put(line)
            except: break

    def _wait_for_log_pattern(self, patterns, timeout):
        """Waits for a pattern while recording logs."""
        if isinstance(patterns, str): patterns = [patterns]
        start = time.time()
        while time.time() - start < timeout:
            try:
                while not self.output_queue.empty():
                    line = self.output_queue.get_nowait()
                    self.full_log.append(f"RX: {line.strip()}") # Record it!
                    
                    for p in patterns:
                        if p in line: return True
                        
                    if "error" in line.lower():
                        self.full_log.append(f"![Tau Error detected]: {line.strip()}")
            except: pass
            time.sleep(0.05)
        return False

    def compute(self, measure_vol):
        if not self.valid: return None
        
        val_int = max(0, min(255, int(measure_vol * 100)))
        hex_in = f"#x{val_int:02X}\n"
        
        try:
            self.process.stdin.write(hex_in)
            self.process.stdin.flush()
            self.full_log.append(f"TX: {hex_in.strip()}")
            
            # Wait for response
            while True:
                try:
                    line = self.output_queue.get(timeout=0.2)
                    self.full_log.append(f"RX: {line.strip()}")
                    
                    if "o1[" in line and ":=" in line:
                        parts = line.split(":=")
                        val_part = parts[-1].strip()
                        # Parse Hex/Bin/Dec
                        if "#x" in val_part: res = int(val_part.replace("#x",""), 16)
                        elif "#b" in val_part: res = int(val_part.replace("#b",""), 2)
                        elif "T" in val_part: res = 1
                        else: 
                            try: res = int(val_part)
                            except: res = 0
                        return float(res) / 10.0
                except queue.Empty:
                    if self.process.poll() is not None: return None
                    continue # Keep waiting
        except: return None

    def close(self):
        self.stop_event.set()
        if self.process:
            try:
                self.full_log.append("![Sys] Sending Quit Command...")
                self.process.stdin.write("q\n")
                self.process.stdin.flush()
                time.sleep(0.2)
                self.process.terminate()
            except: pass
        
        # Drain remaining logs
        while not self.output_queue.empty():
            try: self.full_log.append(f"RX: {self.output_queue.get_nowait().strip()}")
            except: break

    def get_all_logs(self):
        return self.full_log

# ==============================================================================
# 4. GUI APPLICATION
# ==============================================================================
class TauStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tau Studio: Playback & Console")
        self.root.geometry("1400x950")
        self.ani = None
        
        style = ttk.Style()
        style.configure("Header.TLabel", font=("Arial", 14, "bold"))
        style.configure("Status.TLabel", font=("Arial", 16, "bold"))
        
        # --- LEFT PANEL ---
        control_frame = ttk.Frame(root, padding="15")
        control_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        ttk.Label(control_frame, text="1. Environment", style="Header.TLabel").pack(pady=5, anchor="w")
        self.tau_path = tk.StringVar()
        self.btn_load_tau = ttk.Button(control_frame, text="Locate Tau Executable...", command=self.load_tau_exe)
        self.btn_load_tau.pack(fill=tk.X, pady=5)
        self.lbl_tau_status = ttk.Label(control_frame, text="Mode: PID ONLY", foreground="red")
        self.lbl_tau_status.pack(pady=2)

        ttk.Separator(control_frame).pack(fill='x', pady=10)

        ttk.Label(control_frame, text="2. Parameters", style="Header.TLabel").pack(pady=5, anchor="w")
        self.kp = self.create_input(control_frame, "Kp:", "4.0")
        self.steps = self.create_input(control_frame, "Duration:", "200")
        self.glitches = self.create_input(control_frame, "Glitches:", "3")
        self.speed = self.create_input(control_frame, "Speed (ms):", "20")

        ttk.Separator(control_frame).pack(fill='x', pady=10)
        
        self.btn_run = ttk.Button(control_frame, text="▶ COMPUTE & PLAY", command=self.run_scenario)
        self.btn_run.pack(fill=tk.X, ipady=10)
        self.lbl_status = ttk.Label(control_frame, text="Ready", style="Status.TLabel")
        self.lbl_status.pack(pady=10)
        self.progress = ttk.Progressbar(control_frame, length=200)
        self.progress.pack(fill=tk.X)

        # CONSOLE
        ttk.Separator(control_frame).pack(fill='x', pady=10)
        ttk.Label(control_frame, text="Tau Execution Logs:", font=("Arial", 10, "bold")).pack(anchor="w")
        self.console = DebugConsole(control_frame)
        self.console.pack(fill=tk.BOTH, expand=True, pady=5)

        # --- RIGHT PANEL ---
        plot_frame = ttk.Frame(root)
        plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 8))
        self.fig.subplots_adjust(hspace=0.4, top=0.9, bottom=0.1)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.setup_empty_plots()

    def create_input(self, parent, label, default):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)
        ttk.Label(frame, text=label, width=12).pack(side=tk.LEFT)
        entry = ttk.Entry(frame)
        entry.insert(0, default)
        entry.pack(side=tk.RIGHT, expand=True, fill=tk.X)
        return entry

    def load_tau_exe(self):
        f = filedialog.askopenfilename()
        if f:
            self.tau_path.set(f)
            self.lbl_tau_status.config(text="Mode: PID vs TAU", foreground="green")

    def setup_empty_plots(self):
        self.ax1.clear(); self.ax2.clear()
        self.ax1.set_title("Volume Flow Rate")
        self.ax1.grid(True, alpha=0.3)
        self.ax2.set_title("Controller Action")
        self.ax2.grid(True, alpha=0.3)
        self.canvas.draw()

    def generate_scenario(self, steps, num_glitches):
        np.random.seed(None)
        df = pd.DataFrame({'step': range(steps), 'noise': np.random.normal(0, 0.01, steps), 'load': [1.0] * steps})
        for _ in range(num_glitches):
            t = np.random.randint(30, steps-30)
            kind = np.random.choice(['spike', 'dropout', 'blockage'])
            if kind == 'spike': df.loc[t:t+2, 'noise'] += 1.5
            elif kind == 'dropout': df.loc[t:t+2, 'noise'] -= 0.5
            elif kind == 'blockage': df.loc[t:t+40, 'load'] = 0.2
        return df

    def run_scenario(self):
        try:
            steps = int(self.steps.get())
            n_glitch = int(self.glitches.get())
            kp = float(self.kp.get())
            speed_val = int(self.speed.get())
        except: return

        if self.ani: self.ani.event_source.stop()
        self.btn_run.config(state="disabled")
        self.console.clear()
        self.console.log("--- COMPUTING... ---")
        self.lbl_status.config(text="Computing...", foreground="blue")
        self.root.update()
        
        df = self.generate_scenario(steps, n_glitch)
        
        plant_pid = PistonPump()
        plant_tau = PistonPump()
        pid = PID(kp, 0.5, 1.0, True)
        tau = TauInterface(self.tau_path.get())
        
        amp_pid, amp_tau = 0.0, 0.0
        
        self.history = {'x':[], 'pid_v':[], 'tau_v':[], 'pid_a':[], 'tau_a':[], 'status':[]}
        self.progress['maximum'] = steps

        for i in range(steps):
            self.progress['value'] = i
            # Update GUI every 10 steps to stay responsive but fast
            if i % 10 == 0: self.root.update()
            
            row = df.iloc[i]
            
            # PID
            m_p = plant_pid.update(amp_pid, row['noise'], row['load'])
            amp_pid = max(0, min(10, amp_pid + pid.compute(0.5, m_p)))
            
            # Tau
            m_t = plant_tau.update(amp_tau, row['noise'], row['load'])
            tgt = tau.compute(m_t)
            
            # If Tau is valid, update. If not (flatline issue), keep 0.
            if tgt is not None: amp_tau = tgt
            
            self.history['x'].append(i)
            self.history['pid_v'].append(m_p)
            self.history['tau_v'].append(m_t)
            self.history['pid_a'].append(amp_pid)
            self.history['tau_a'].append(amp_tau)
            
            st = "Normal"
            if abs(row['noise']) > 0.5: st = "GLITCH"
            elif row['load'] < 0.9: st = "BLOCKAGE"
            self.history['status'].append(st)

        # DUMP LOGS at the end
        logs = tau.get_all_logs()
        for l in logs:
            col = "cyan" if "TX" in l else "red" if "Err" in l else None
            self.console.log(l, col)

        tau.close()
        self.lbl_status.config(text="Playing...", foreground="green")
        self.btn_run.config(state="normal")
        self.play_animation(steps, speed_val)

    def play_animation(self, steps, speed):
        self.ax1.clear(); self.ax2.clear()
        self.ax1.set_xlim(0, steps); self.ax1.set_ylim(-0.5, 2.0)
        self.ax1.set_title("Playback: Volume Flow Rate")
        self.ax1.axhline(0.5, color='k', ls='--')
        l_pid_v, = self.ax1.plot([], [], 'r-', label="PID")
        l_tau_v, = self.ax1.plot([], [], 'b-', label="Tau")
        self.ax1.legend()
        self.ax1.grid(True, alpha=0.3)
        
        self.ax2.set_xlim(0, steps); self.ax2.set_ylim(0, 12)
        self.ax2.set_title("Controller Action")
        l_pid_a, = self.ax2.plot([], [], 'r-', alpha=0.5)
        l_tau_a, = self.ax2.plot([], [], 'b-', alpha=0.5)
        self.ax2.grid(True, alpha=0.3)

        def update(f):
            x = self.history['x'][:f]
            l_pid_v.set_data(x, self.history['pid_v'][:f])
            l_tau_v.set_data(x, self.history['tau_v'][:f])
            l_pid_a.set_data(x, self.history['pid_a'][:f])
            l_tau_a.set_data(x, self.history['tau_a'][:f])
            
            st = self.history['status'][f]
            if st == "GLITCH": self.lbl_status.config(text="⚠️ GLITCH", foreground="red")
            elif st == "BLOCKAGE": self.lbl_status.config(text="⚠️ BLOCKAGE", foreground="orange")
            else: self.lbl_status.config(text=f"Step {f}/{steps}", foreground="black")
            
            return l_pid_v, l_tau_v, l_pid_a, l_tau_a

        self.ani = FuncAnimation(self.fig, update, frames=range(steps), interval=speed, blit=False, repeat=False)
        self.canvas.draw()

if __name__ == "__main__":
    root = tk.Tk()
    app = TauStudioApp(root)
    root.mainloop()