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
import re

# ==============================================================================
# 0. ROBUST TAU LOGIC (Dynamic Target)
# ==============================================================================
# LEVEL 6: TUNED CONTROLLER (Physics-Correct)
# Neutral Power adjusted to 25 (#x19) to maintain 0.5 Flow.
# Gaps closed to prevent "coasting".

# LEVEL 6: TUNED CONTROLLER (Physics-Correct)
TAU_CODE_ONE_LINER = (
    "set charvar off\n"
    "i1 : bv[8] = in console\n"
    "i2 : bv[8] = in console\n"
    "o1 : bv[8] = out console\n"
    "run always ("
    "((i1[t] > (i2[t] + { #x3C }:bv[8]))) ? (o1[t] = o1[t-1]) : "
    "((i1[t] >= (i2[t] - { #x04 }:bv[8])) && (i1[t] <= (i2[t] + { #x04 }:bv[8]))) ? (o1[t] = { #x19 }:bv[8]) : "
    "(i1[t] > (i2[t] + { #x28 }:bv[8])) ? (o1[t] = { #x00 }:bv[8]) : "
    "(i1[t] > (i2[t] + { #x0A }:bv[8])) ? (o1[t] = { #x0A }:bv[8]) : "
    "(i1[t] < (i2[t] - { #x1E }:bv[8])) ? (o1[t] = { #x64 }:bv[8]) : "
    "(i1[t] < (i2[t] - { #x0A }:bv[8])) ? (o1[t] = { #x32 }:bv[8]) : "
    "(o1[t] = { #x19 }:bv[8])"
    ")\n"
)

# ==============================================================================
# 1. PHYSICS (Heavy Inertia)
# ==============================================================================
class PistonPump:
    def __init__(self): 
        self.amp = 0.0      
        self.velocity = 0.0 

    def update(self, target_force, noise, load):
        force = target_force - (self.amp * 0.5) 
        accel = force * 0.1 
        self.velocity += accel
        self.velocity *= 0.9 
        self.amp += self.velocity
        self.amp = max(0, min(20, self.amp))
        return max(0, (self.amp * 0.1 * load) + noise)

class PID:
    def __init__(self, kp, ki, kd, clamp):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.clamp, self.prev_err, self.integral = clamp, 0, 0
    def compute(self, setpoint, measure):
        err = setpoint - measure
        self.integral += err
        if self.clamp: self.integral = max(-20, min(20, self.integral)) # Tighter clamp
        p = self.kp * err
        i = self.ki * self.integral
        d = self.kd * (err - self.prev_err)
        self.prev_err = err
        return p + i + d

# ==============================================================================
# 2. DEBUG CONSOLE
# ==============================================================================
class DebugConsole(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.text = scrolledtext.ScrolledText(self, height=12, bg="black", fg="#00ff00", font=("Consolas", 9))
        self.text.pack(fill=tk.BOTH, expand=True)
        self.log(">>> SYSTEM READY")

    def log(self, msg, color=None):
        tag = "normal"
        if color == "red":
            self.text.tag_config("err", foreground="#ff5555")
            tag = "err"
        elif color == "cyan":
            self.text.tag_config("tx", foreground="#55ffff")
            tag = "tx"
        elif color == "yellow":
            self.text.tag_config("warn", foreground="yellow")
            tag = "warn"
            
        self.text.insert(tk.END, msg + "\n", tag)
        self.text.see(tk.END)
        
    def clear(self):
        self.text.delete('1.0', tk.END)


# ==============================================================================
# 3. TAU INTERFACE (REGEX HARDENED)
# ==============================================================================
class TauInterface:
    def __init__(self, exe_path, logger_callback=None):
        self.valid = False
        self.process = None
        self.output_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.logger = logger_callback
        
        if not exe_path or not os.path.exists(exe_path):
            if self.logger: self.logger("![Sys] Tau executable not found.", "red")
            return

        try:
            self.process = subprocess.Popen(
                [exe_path], 
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=0
            )
            
            threading.Thread(target=self._stdout_reader, daemon=True).start()
            threading.Thread(target=self._stderr_reader, daemon=True).start()

            if self.logger: self.logger("![Sys] Initializing...", "yellow")

            # Initial handshake
            if not self._wait_for_regex(r"tau>", 5.0):
                 if self.logger: self.logger("![Warn] Prompt check skipped...", "yellow")

            self.process.stdin.write(TAU_CODE_ONE_LINER)
            self.process.stdin.flush()
            
            if self._wait_for_regex(r"Execution step|Please provide", 20.0):
                self.valid = True
                if self.logger: self.logger("![Sys] Logic Accepted.", "green")
            else:
                self.valid = False
                if self.logger: self.logger("![Err] Logic Rejected.", "red")

        except Exception as e:
            if self.logger: self.logger(f"![Exc] {e}", "red")

    def _stdout_reader(self):
        while not self.stop_event.is_set():
            try:
                char = self.process.stdout.read(1)
                if not char: break
                self.output_queue.put(char)
            except: break

    def _stderr_reader(self):
        while not self.stop_event.is_set():
            try:
                line = self.process.stderr.readline()
                if not line: break
                # Only log unexpected errors
                if "Error" in line or "fail" in line:
                    if self.logger: self.logger(f"[LOG] {line.strip()}", "yellow")
            except: break

    def _clean_text(self, text):
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def _wait_for_regex(self, pattern, timeout):
        start = time.time()
        buffer = ""
        while time.time() - start < timeout:
            while not self.output_queue.empty():
                buffer += self.output_queue.get()
            if re.search(pattern, self._clean_text(buffer)): return True
            time.sleep(0.05)
        return False

    def _read_until_token(self, token, timeout=0.5):
        """Waits until a specific string appears in the buffer."""
        buffer = ""
        start = time.time()
        while time.time() - start < timeout:
            while not self.output_queue.empty():
                buffer += self.output_queue.get()
            if token in self._clean_text(buffer): return buffer
            time.sleep(0.001)
        return buffer

    def compute(self, measure_vol, target_vol):
        if not self.valid: return None
        
        # 1. Format Inputs (Strict Bitvector Hex)
        # ensure we send integer hex (e.g. #x1F) not float strings
        val_m = max(0, min(255, int(measure_vol * 100)))
        val_t = max(0, min(255, int(target_vol * 100)))
        
        hex_m = f"#x{val_m:02X}\n"
        hex_t = f"#x{val_t:02X}\n"
        
        try:
            # STEP 1: Wait for i1 -> Send i1
            self._read_until_token("i1", 1.0)
            self.process.stdin.write(hex_m)
            self.process.stdin.flush()
            
            # STEP 2: Wait for i2 -> Send i2
            self._read_until_token("i2", 1.0)
            self.process.stdin.write(hex_t)
            self.process.stdin.flush()
            
            # STEP 3: Wait for o1 output
            # We read enough buffer to ensure we capture the value
            # We do NOT use split() here to avoid crashes.
            response = self._read_until_token("o1", 0.5)
            
            # Continue reading a bit more if we have the prompt but not the value
            if ":=" in response and not re.search(r":=\s*([#\w]+)", response):
                 time.sleep(0.05) # Tiny wait for the value to arrive
                 while not self.output_queue.empty():
                     response += self.output_queue.get()
            
            # STEP 4: Regex Parse (The Crash Fix)
            # Looks for ":= " followed by any word chars or #
            clean_resp = self._clean_text(response)
            
            # Match patterns like: := #x32, := 0, := T
            match = re.search(r":=\s*([#]?[xXbB]?[0-9a-fA-F]+|T|F)", clean_resp)
            
            if match:
                val_part = match.group(1).strip()
                
                # if self.logger: self.logger(f"RX: {val_part}", "normal") # Debug print
                
                if "#x" in val_part: res = int(val_part.replace("#x",""), 16)
                elif "#b" in val_part: res = int(val_part.replace("#b",""), 2)
                elif "T" in val_part: res = 1
                elif "F" in val_part: res = 0
                else: 
                    try: res = int(val_part)
                    except: res = 0
                
                return float(res) / 10.0
            else:
                # If regex failed, it means we didn't get a valid value yet.
                # Return None (safe fail) instead of crashing.
                return None
                
        except Exception as e:
            if self.logger: self.logger(f"![IO] {e}", "red")
            return None

# ==============================================================================
# 4. GUI APPLICATION
# ==============================================================================
class TauStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tau Studio: Synchronized Control")
        self.root.geometry("1400x950")
        self.ani = None
        self.is_running = False
        self.manual_glitch = False
        
        style = ttk.Style()
        style.configure("Header.TLabel", font=("Arial", 12, "bold"))
        
        # --- LEFT PANEL ---
        control_frame = ttk.Frame(root, padding="15")
        control_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        ttk.Label(control_frame, text="1. Setup", style="Header.TLabel").pack(pady=5, anchor="w")
        self.tau_path = tk.StringVar()
        ttk.Button(control_frame, text="Locate Tau Executable...", command=self.load_tau_exe).pack(fill=tk.X)
        self.lbl_tau_status = ttk.Label(control_frame, text="Mode: PID ONLY", foreground="red")
        self.lbl_tau_status.pack(pady=2)

        ttk.Separator(control_frame).pack(fill='x', pady=10)
        
        # CONTROLS
        ttk.Label(control_frame, text="TARGET SETPOINT", font=("Arial", 10, "bold")).pack(anchor="w")
        self.target_scale = tk.Scale(control_frame, from_=0.2, to=0.8, resolution=0.01, orient=tk.HORIZONTAL, length=250)
        self.target_scale.set(0.5)
        self.target_scale.pack(pady=5)

        ttk.Label(control_frame, text="PID Tuning:", style="Header.TLabel").pack(anchor="w", pady=(10,0))
        self.kp_scale = self.create_slider(control_frame, "Kp (Power)", 0.0, 10.0, 4.0)
        self.ki_scale = self.create_slider(control_frame, "Ki (Correct)", 0.0, 2.0, 0.1)
        self.kd_scale = self.create_slider(control_frame, "Kd (Dampen)", 0.0, 5.0, 2.5)

        ttk.Separator(control_frame).pack(fill='x', pady=10)

        self.btn_glitch = ttk.Button(control_frame, text="⚡ INJECT SPIKE FAULT", command=self.trigger_glitch)
        self.btn_glitch.pack(fill=tk.X, pady=5)

        ttk.Label(control_frame, text="Sim Speed (ms):").pack(anchor="w")
        self.speed_scale = tk.Scale(control_frame, from_=10, to=500, orient=tk.HORIZONTAL)
        self.speed_scale.set(50)
        self.speed_scale.pack(fill=tk.X)

        self.btn_run = ttk.Button(control_frame, text="▶ START LIVE SIM", command=self.toggle_simulation)
        self.btn_run.pack(fill=tk.X, ipady=10, pady=10)

        self.console = DebugConsole(control_frame)
        self.console.pack(fill=tk.BOTH, expand=True, pady=5)

        # --- RIGHT PANEL ---
        plot_frame = ttk.Frame(root)
        plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 8))
        self.fig.subplots_adjust(hspace=0.3, top=0.95, bottom=0.05)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.setup_empty_plots()

    def create_slider(self, parent, label, vmin, vmax, vdef):
        ttk.Label(parent, text=label).pack(anchor="w")
        s = tk.Scale(parent, from_=vmin, to=vmax, resolution=0.1, orient=tk.HORIZONTAL)
        s.set(vdef)
        s.pack(fill=tk.X)
        return s

    def load_tau_exe(self):
        f = filedialog.askopenfilename()
        if f:
            self.tau_path.set(f)
            self.lbl_tau_status.config(text="Mode: PID vs TAU", foreground="green")

    def trigger_glitch(self): self.manual_glitch = True
    
    def setup_empty_plots(self):
        self.ax1.clear(); self.ax2.clear()
        self.ax1.set_title("Response Comparison")
        self.ax1.set_xlim(0, 300); self.ax1.set_ylim(-0.1, 1.1)
        self.ax1.grid(True, alpha=0.3)
        self.ax2.set_title("Controller Action")
        self.ax2.set_xlim(0, 300); self.ax2.set_ylim(0, 12)
        self.ax2.grid(True, alpha=0.3)
        self.canvas.draw()

    def toggle_simulation(self):
        if self.is_running: self.stop_simulation()
        else: self.start_live_simulation()

    def stop_simulation(self):
        self.is_running = False
        if self.ani: self.ani.event_source.stop()
        if hasattr(self, 'tau_interface'): self.tau_interface.close()
        self.btn_run.config(text="▶ START LIVE SIM")

    def start_live_simulation(self):
        self.is_running = True
        self.btn_run.config(text="⏹ STOP SIMULATION")
        self.console.clear()
        
        self.plant_pid = PistonPump()
        self.plant_tau = PistonPump()
        self.pid = PID(self.kp_scale.get(), self.ki_scale.get(), self.kd_scale.get(), True)
        
        # Pass console logger to interface
        self.tau_interface = TauInterface(self.tau_path.get(), self.console.log)
        
        # WARM START: Initialize pumps at Target (0.5 -> 5.0 Force)
        # This prevents the initial drop to 0.0
        self.amp_pid = 5.0
        self.amp_tau = 5.0
        
        # Initialize Pump Velocity to 0 (Steady state)
        self.plant_pid.amp = 5.0
        self.plant_tau.amp = 5.0
        
        self.step_idx = 0
        try: self.window_size = int(self.entry_window.get())
        except: self.window_size = 300
        
        self.data_x, self.data_target = [], []
        self.data_pid_v, self.data_tau_v = [], []
        self.data_pid_a, self.data_tau_a = [], []
        
        self.ax1.clear(); self.ax2.clear()
        self.ax1.set_xlim(0, self.window_size); self.ax1.set_ylim(-0.2, 1.5)
        self.ax1.grid(True, alpha=0.3)
        self.ax2.set_xlim(0, self.window_size); self.ax2.set_ylim(0, 12)
        self.ax2.grid(True, alpha=0.3)
        
        self.line_target, = self.ax1.plot([], [], 'g--', label="Target", linewidth=2)
        self.line_pid, = self.ax1.plot([], [], 'r-', label="PID")
        self.line_tau, = self.ax1.plot([], [], 'b-', label="Tau")
        self.ax1.legend()
        
        self.line_pid_a, = self.ax2.plot([], [], 'r-', alpha=0.5)
        self.line_tau_a, = self.ax2.plot([], [], 'b-', alpha=0.5)

        self.ani = FuncAnimation(self.fig, self.update_frame, interval=50, blit=False)
        self.canvas.draw()

    def update_frame(self, frame):
        if not self.is_running: return
        
        # 1. PARAMETER UPDATE
        target = self.target_scale.get()
        self.pid.kp = self.kp_scale.get()
        self.pid.ki = self.ki_scale.get()
        self.pid.kd = self.kd_scale.get()
        
        noise = np.random.normal(0, 0.01)
        if self.manual_glitch:
            noise += 2.0
            self.console.log(">> GLITCH INJECTED", "red")
            self.manual_glitch = False
            
        # 2. PHYSICS (Synchronized Step)
        # Both plants update using the output calculated in the PREVIOUS frame
        m_p = self.plant_pid.update(self.amp_pid, noise, 1.0)
        m_t = self.plant_tau.update(self.amp_tau, noise, 1.0)
        
        # 3. CONTROL (Synchronized Step)
        # PID is fast, Tau is slow. 
        # By putting them here sequentially, the simulation time 't' 
        # is effectively paused until Tau returns. 
        # This guarantees graph alignment.
        
        self.amp_pid = max(0, min(10, self.amp_pid + self.pid.compute(target, m_p)))
        
        tgt = self.tau_interface.compute(m_t, target)
        if tgt is not None: self.amp_tau = tgt
        
        # 4. BUFFERING & SCROLLING
        self.data_x.append(self.step_idx)
        self.data_target.append(target)
        self.data_pid_v.append(m_p)
        self.data_tau_v.append(m_t)
        self.data_pid_a.append(self.amp_pid)
        self.data_tau_a.append(self.amp_tau)
        
        if len(self.data_x) > self.window_size:
            self.data_x.pop(0)
            self.data_target.pop(0)
            self.data_pid_v.pop(0)
            self.data_tau_v.pop(0)
            self.data_pid_a.pop(0)
            self.data_tau_a.pop(0)
            
            self.ax1.set_xlim(self.data_x[0], self.data_x[-1] + 10)
            self.ax2.set_xlim(self.data_x[0], self.data_x[-1] + 10)

        # 5. RENDER
        self.line_target.set_data(self.data_x, self.data_target)
        self.line_pid.set_data(self.data_x, self.data_pid_v)
        self.line_tau.set_data(self.data_x, self.data_tau_v)
        self.line_pid_a.set_data(self.data_x, self.data_pid_a)
        self.line_tau_a.set_data(self.data_x, self.data_tau_a)
        
        self.step_idx += 1
        self.ani.event_source.interval = int(self.speed_scale.get())

if __name__ == "__main__":
    root = tk.Tk()
    app = TauStudioApp(root)
    root.mainloop()