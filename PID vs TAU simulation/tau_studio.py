import tkinter as tk
from tkinter import ttk, filedialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import pandas as pd
import numpy as np
import subprocess
import os

# ==============================================================================
# GLOBAL FONT SETTINGS
# ==============================================================================
# Increase Matplotlib font sizes globally
plt.rcParams.update({
    'font.size': 11,
    'axes.titlesize': 14,
    'axes.labelsize': 12,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 11,
    'figure.titlesize': 16
})

# ==============================================================================
# 0. DEFAULT TAU LOGIC
# ==============================================================================
TAU_FILENAME = "controller.tau"
DEFAULT_TAU_CODE = """
"""

def ensure_tau_file():
    if not os.path.exists(TAU_FILENAME):
        with open(TAU_FILENAME, "w") as f:
            f.write(DEFAULT_TAU_CODE.strip())

# ==============================================================================
# 1. PHYSICS & CONTROL CLASSES
# ==============================================================================
class PistonPump:
    def __init__(self):
        self.amp = 0.0
    def update(self, target, noise, load):
        self.amp += (target - self.amp) * 0.5
        vol = (self.amp * 0.1 * load) + noise
        return max(0, vol)

class PID:
    def __init__(self, kp, ki, kd, clamp):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.clamp = clamp
        self.prev_err = 0
        self.integral = 0
        
    def compute(self, setpoint, measure):
        err = setpoint - measure
        self.integral += err
        if self.clamp:
            self.integral = max(-50, min(50, self.integral))
        
        p = self.kp * err
        i = self.ki * self.integral
        d = self.kd * (err - self.prev_err)
        self.prev_err = err
        return p + i + d

class TauInterface:
    def __init__(self, exe_path):
        self.valid = False
        if not exe_path or not os.path.exists(exe_path):
            return
        try:
            self.process = subprocess.Popen(
                [exe_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            with open(TAU_FILENAME, 'r') as f:
                self.process.stdin.write(f.read() + "\n")
                self.process.stdin.flush()
            self.valid = True
        except Exception as e:
            print(f"Tau Init Error: {e}")

    def compute(self, measure_vol):
        if not self.valid: return None
        
        val_int = int(measure_vol * 100)
        val_int = max(0, min(255, val_int))
        hex_in = f"#x{val_int:02X}\n"
        
        try:
            self.process.stdin.write(hex_in)
            self.process.stdin.flush()
            while True:
                line = self.process.stdout.readline()
                if not line: break
                if "o1[" in line and ":=" in line:
                    val_part = line.split(":=")[1].strip()
                    if "#x" in val_part: res = int(val_part.replace("#x",""), 16)
                    elif "#b" in val_part: res = int(val_part.replace("#b",""), 2)
                    elif "T" in val_part: res = 1
                    else: 
                        try: res = int(val_part)
                        except: res = 0
                    return float(res) / 10.0
        except:
            return None
        return None

    def close(self):
        if self.valid:
            self.process.terminate()

# ==============================================================================
# 2. GUI APPLICATION
# ==============================================================================
class TauStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tau Studio: Hardware-in-Loop Simulator")
        self.root.geometry("1400x900") # Larger window
        
        ensure_tau_file()
        self.ani = None
        
        # --- STYLES ---
        style = ttk.Style()
        style.configure("TLabel", font=("Arial", 12))
        style.configure("TButton", font=("Arial", 12, "bold"))
        style.configure("Header.TLabel", font=("Arial", 14, "bold"))
        style.configure("Status.TLabel", font=("Arial", 16, "bold"))
        
        # --- LEFT PANEL (CONTROLS) ---
        control_frame = ttk.Frame(root, padding="15")
        control_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        # 1. Environment
        ttk.Label(control_frame, text="1. Environment", style="Header.TLabel").pack(pady=10, anchor="w")
        
        self.tau_path = tk.StringVar()
        self.btn_load_tau = ttk.Button(control_frame, text="Locate Tau Executable...", command=self.load_tau_exe)
        self.btn_load_tau.pack(fill=tk.X, pady=5, ipady=5)
        
        self.lbl_tau_status = ttk.Label(control_frame, text="Mode: PID ONLY", foreground="red", font=("Arial", 11, "bold"))
        self.lbl_tau_status.pack(pady=5)

        ttk.Separator(control_frame, orient='horizontal').pack(fill='x', pady=15)

        # 2. PID Tuning
        ttk.Label(control_frame, text="2. PID Tuning", style="Header.TLabel").pack(pady=10, anchor="w")
        self.kp = self.create_input(control_frame, "Kp (Prop):", "4.0")
        self.ki = self.create_input(control_frame, "Ki (Integral):", "0.5")
        self.kd = self.create_input(control_frame, "Kd (Deriv):", "1.0")
        
        self.clamp_var = tk.BooleanVar(value=True)
        chk = ttk.Checkbutton(control_frame, text="Safety Clamp (Anti-Windup)", variable=self.clamp_var)
        # Increase Checkbutton text size via style is tricky in tkinter, sticking to default size or hacking it. 
        # Easier to just pack it cleanly.
        chk.pack(pady=10)

        ttk.Separator(control_frame, orient='horizontal').pack(fill='x', pady=15)

        # 3. Scenario
        ttk.Label(control_frame, text="3. Scenario", style="Header.TLabel").pack(pady=10, anchor="w")
        self.steps = self.create_input(control_frame, "Duration:", "300")
        self.glitches = self.create_input(control_frame, "Glitches:", "4")
        self.speed = self.create_input(control_frame, "Speed (ms):", "30")

        ttk.Separator(control_frame, orient='horizontal').pack(fill='x', pady=25)
        
        # Buttons
        self.btn_run = ttk.Button(control_frame, text="▶ START LIVE SIMULATION", command=self.start_animation)
        self.btn_run.pack(fill=tk.X, ipady=10)
        
        self.btn_stop = ttk.Button(control_frame, text="⏹ STOP", command=self.stop_animation)
        self.btn_stop.pack(fill=tk.X, pady=10)
        
        # Status Label (Fixed Width to prevent resizing glitch)
        self.lbl_status = ttk.Label(control_frame, text="Ready", style="Status.TLabel", width=25, anchor="center")
        self.lbl_status.pack(pady=30)

        # --- RIGHT PANEL (PLOTS) ---
        plot_frame = ttk.Frame(root)
        plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 8))
        self.fig.subplots_adjust(hspace=0.4, top=0.9, bottom=0.1) # More space for titles
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        self.setup_empty_plots()

    def create_input(self, parent, label, default):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=4)
        ttk.Label(frame, text=label, width=15).pack(side=tk.LEFT)
        entry = ttk.Entry(frame, font=("Arial", 11))
        entry.insert(0, default)
        entry.pack(side=tk.RIGHT, expand=True, fill=tk.X)
        return entry

    def load_tau_exe(self):
        filename = filedialog.askopenfilename(title="Select Tau Executable")
        if filename:
            self.tau_path.set(filename)
            self.lbl_tau_status.config(text="Mode: PID vs TAU", foreground="green")

    def setup_empty_plots(self):
        self.ax1.clear()
        self.ax2.clear()
        
        # Top Plot
        self.ax1.set_title("Performance: Stroke Volume", fontweight='bold')
        self.ax1.set_ylabel("Stroke (ml)")
        self.ax1.set_xlabel("Time Step") # Added Axis Label
        self.ax1.set_ylim(-0.2, 1.5)
        self.ax1.axhline(y=0.5, color='k', linestyle='--', alpha=0.5)
        self.ax1.grid(True, alpha=0.3)
        
        # Bottom Plot
        self.ax2.set_title("Controller Output: Motor Amplitude (mm)", fontweight='bold')
        self.ax2.set_ylabel("Amplitude (mm)")
        self.ax2.set_xlabel("Time Step")
        self.ax2.set_ylim(0, 12)
        self.ax2.grid(True, alpha=0.3)
        
        self.canvas.draw()

    def generate_scenario(self, steps, num_glitches):
        np.random.seed(None)
        df = pd.DataFrame({
            'step': range(steps),
            'noise': np.random.normal(0, 0.01, steps),
            'load': [1.0] * steps
        })
        for _ in range(num_glitches):
            t = np.random.randint(30, steps-30)
            kind = np.random.choice(['spike', 'dropout', 'blockage'])
            if kind == 'spike': df.loc[t:t+2, 'noise'] += 1.5
            elif kind == 'dropout': df.loc[t:t+2, 'noise'] -= 0.5
            elif kind == 'blockage': df.loc[t:t+40, 'load'] = 0.2
        return df

    def stop_animation(self):
        if self.ani: self.ani.event_source.stop()

    def start_animation(self):
        try:
            steps = int(self.steps.get())
            speed = int(self.speed.get())
            n_glitch = int(self.glitches.get())
            kp = float(self.kp.get())
            ki = float(self.ki.get())
            kd = float(self.kd.get())
            clamp = self.clamp_var.get()
        except: return

        df = self.generate_scenario(steps, n_glitch)
        plant_pid = PistonPump()
        plant_tau = PistonPump()
        pid = PID(kp, ki, kd, clamp)
        tau = TauInterface(self.tau_path.get())
        
        self.amp_pid = 0.0
        self.amp_tau = 0.0
        self.x_data, self.pid_v_data, self.tau_v_data = [], [], []
        self.pid_a_data, self.tau_a_data = [], []

        self.ax1.clear()
        self.ax2.clear()
        
        # Setup Plot 1
        self.ax1.set_xlim(0, steps)
        self.ax1.set_ylim(-0.5, 2.0)
        self.ax1.set_title("Performance: Stroke Volume", fontweight='bold')
        self.ax1.set_ylabel("Volume (ml)")
        self.ax1.set_xlabel("Time Step") # Explicit Axis
        self.ax1.axhline(y=0.5, color='k', linestyle='--', label="Target")
        
        line_pid_v, = self.ax1.plot([], [], 'r-', alpha=0.8, lw=2, label="PID")
        line_tau_v, = self.ax1.plot([], [], 'b-', alpha=0.9, lw=2.5, label="Tau")
        self.ax1.legend(loc="upper right", frameon=True)
        self.ax1.grid(True, alpha=0.3)
        
        # Setup Plot 2
        self.ax2.set_xlim(0, steps)
        self.ax2.set_ylim(0, 12)
        self.ax2.set_title("Controller Action: Motor Amplitude (mm)", fontweight='bold')
        self.ax2.set_ylabel("Amplitude (mm)")
        self.ax2.set_xlabel("Time Step")
        
        line_pid_a, = self.ax2.plot([], [], 'r-', alpha=0.5, lw=1.5, label="PID Amp")
        line_tau_a, = self.ax2.plot([], [], 'b-', alpha=0.5, lw=1.5, label="Tau Amp")
        self.ax2.legend(loc="upper right", frameon=True)
        self.ax2.grid(True, alpha=0.3)

        def update(frame):
            if frame >= steps: 
                self.stop_animation()
                tau.close()
                return

            row = df.iloc[frame]
            noise = row['noise']
            load = row['load']
            
            # Physics
            meas_p = plant_pid.update(self.amp_pid, noise, load)
            adj = pid.compute(0.5, meas_p)
            self.amp_pid += adj
            self.amp_pid = max(0, min(10, self.amp_pid))
            
            meas_t = plant_tau.update(self.amp_tau, noise, load)
            tgt = tau.compute(meas_t)
            
            if tgt is not None:
                self.amp_tau = tgt
                self.tau_v_data.append(meas_t)
                self.tau_a_data.append(self.amp_tau)
            else:
                self.tau_v_data.append(None)
                self.tau_a_data.append(None)
            
            self.x_data.append(frame)
            self.pid_v_data.append(meas_p)
            self.pid_a_data.append(self.amp_pid)
            
            line_pid_v.set_data(self.x_data, self.pid_v_data)
            line_tau_v.set_data(self.x_data, self.tau_v_data)
            line_pid_a.set_data(self.x_data, self.pid_a_data)
            line_tau_a.set_data(self.x_data, self.tau_a_data)
            
            if abs(noise) > 0.5:
                self.lbl_status.config(text="⚠️ SENSOR GLITCH", foreground="red")
            elif load < 0.9:
                self.lbl_status.config(text="⚠️ LOAD SPIKE", foreground="orange")
            else:
                self.lbl_status.config(text=f"Step {frame}/{steps}", foreground="black")

            return line_pid_v, line_tau_v, line_pid_a, line_tau_a

        self.ani = FuncAnimation(self.fig, update, frames=range(steps+1), 
                                 interval=speed, blit=False, repeat=False)
        self.canvas.draw()

if __name__ == "__main__":
    root = tk.Tk()
    app = TauStudioApp(root)
    root.mainloop()