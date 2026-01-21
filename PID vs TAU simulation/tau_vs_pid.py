import subprocess
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sys
import time

# ==============================================================================
# CONFIGURATION
# ==============================================================================
TAU_CMD = r"C:\Users\daniel.navarro\Downloads\tau-0.7-win64\tau.exe" # Ensure 'tau' is in your PATH, or use full path like C:/tau/tau.exe
TAU_FILE = "controller.tau"

STEPS = 150
TARGET_VOL = 0.5
SCALE_IN = 100.0  # 0.5ml -> 50
SCALE_OUT = 10.0  # 50 -> 5.0mm

# ==============================================================================
# 1. DISTURBANCE GENERATOR (The "Real World")
# ==============================================================================
def generate_disturbances():
    np.random.seed(42)
    data = {
        'step': range(STEPS),
        'noise': np.random.normal(0, 0.01, STEPS), 
        'load': [1.0] * STEPS
    }
    df = pd.DataFrame(data)

    # GLITCH: Massive Spike at Step 60
    df.loc[60:62, 'noise'] += 1.5 
    
    # DROPOUT: Sensor fail at Step 100
    df.loc[100:102, 'noise'] -= 0.5 
    
    return df

# ==============================================================================
# 2. PHYSICS PLANT
# ==============================================================================
class PistonPump:
    def __init__(self, name):
        self.name = name
        self.amp = 0.0
    
    def update(self, target_amp, noise, load):
        # Motor lag (moves 50% of difference per step)
        self.amp += (target_amp - self.amp) * 0.5
        # Physics: 1mm amp = 0.1ml flow
        vol = (self.amp * 0.1 * load) + noise
        return max(0, vol)

# ==============================================================================
# 3. PID CONTROLLER
# ==============================================================================
class PID:
    def __init__(self, kp, ki, kd):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.prev_err = 0
        self.integral = 0
        
    def compute(self, setpoint, measure):
        err = setpoint - measure
        self.integral += err
        # Clamp integral to reduce windup insanity
        self.integral = max(-5, min(5, self.integral)) 
        
        p = self.kp * err
        i = self.ki * self.integral
        d = self.kd * (err - self.prev_err)
        self.prev_err = err
        
        # Output is CHANGE in amplitude
        return p + i + d

# ==============================================================================
# 4. TAU INTERFACE (The Bridge)
# ==============================================================================
class TauInterface:
    def __init__(self):
        print(f"Launching Tau Subprocess: {TAU_CMD} < {TAU_FILE}...")
        try:
            self.process = subprocess.Popen(
                [TAU_CMD],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1 # Line buffered
            )
            
            # Feed the controller specification immediately
            with open(TAU_FILE, 'r') as f:
                spec = f.read()
                self.process.stdin.write(spec + "\n")
                self.process.stdin.flush()
                
        except FileNotFoundError:
            print("ERROR: Tau executable not found. Please install Tau.")
            sys.exit(1)

    def compute(self, measure_vol):
        # 1. Scale Input: 0.5ml -> 50
        val_int = int(measure_vol * SCALE_IN)
        val_int = max(0, min(255, val_int))
        
        # 2. Format as Hex for Tau
        hex_input = f"#x{val_int:02X}"
        
        # 3. Send to Tau (i1)
        # We define input explicitly for the current step
        # Note: REPL usually just accepts the value if prompted
        try:
            cmd = f"{hex_input}\n"
            self.process.stdin.write(cmd)
            self.process.stdin.flush()
            
            # 4. Read Output (o1)
            # We look for the line containing "o1"
            while True:
                line = self.process.stdout.readline()
                if not line: break
                
                # Debug print raw tau output if needed:
                # print(f"TAU RAW: {line.strip()}")
                
                if "o1[" in line and ":=" in line:
                    # Parse: "o1[0] := 50" or "o1[0] := #x32"
                    val_part = line.split(":=")[1].strip()
                    
                    if "#x" in val_part:
                        res = int(val_part.replace("#x", ""), 16)
                    elif "#b" in val_part:
                        res = int(val_part.replace("#b", ""), 2)
                    elif "T" in val_part: res = 1
                    elif "F" in val_part: res = 0
                    else: 
                        try: res = int(val_part)
                        except: res = 0
                        
                    # Scale Output: 50 -> 5.0mm
                    return float(res) / SCALE_OUT
                    
        except Exception as e:
            print(f"Tau Communication Error: {e}")
            return 0.0
            
    def close(self):
        self.process.terminate()

# ==============================================================================
# 5. RUNNER
# ==============================================================================
def run_comparison():
    df = generate_disturbances()
    
    # Systems
    plant_pid = PistonPump("PID")
    plant_tau = PistonPump("TAU")
    
    # Controllers
    pid = PID(kp=4.0, ki=0.5, kd=1.0) # Tuned PID
    tau = TauInterface()
    
    # State
    amp_pid = 0.0
    amp_tau = 0.0
    
    history = {'time':[], 'pid_vol':[], 'tau_vol':[], 'target':[]}
    
    print("Starting Simulation Loop...")
    
    for i in range(STEPS):
        noise = df.loc[i, 'noise']
        
        # --- PID LOOP ---
        meas_pid = plant_pid.update(amp_pid, noise, 1.0)
        adj_pid = pid.compute(TARGET_VOL, meas_pid)
        amp_pid += adj_pid
        amp_pid = max(0, min(10, amp_pid)) # Clamp motor
        
        # --- TAU LOOP ---
        meas_tau = plant_tau.update(amp_tau, noise, 1.0)
        # Tau returns Absolute Target, not adjustment
        target_amp_tau = tau.compute(meas_tau)
        # In a real motor, we'd move towards target
        amp_tau = target_amp_tau 
        
        # Log
        history['time'].append(i)
        history['pid_vol'].append(meas_pid)
        history['tau_vol'].append(meas_tau)
        history['target'].append(TARGET_VOL)
        
        if i % 10 == 0:
            print(f"Step {i}: PID={meas_pid:.2f} | Tau={meas_tau:.2f}")

    tau.close()
    
    # --- PLOT ---
    plt.figure(figsize=(10, 6))
    plt.plot(history['time'], history['target'], 'k--', alpha=0.3, label="Target")
    plt.plot(history['time'], history['pid_vol'], 'r-', linewidth=1, label="PID (Calculus)")
    plt.plot(history['time'], history['tau_vol'], 'b-', linewidth=2, label="Tau (Logic)")
    
    # Annotate Glitch
    plt.axvspan(60, 62, color='yellow', alpha=0.3, label="Glitch (Spike)")
    plt.axvspan(100, 102, color='orange', alpha=0.3, label="Glitch (Dropout)")

    plt.title("Hardware-in-Loop: PID vs Tau Logic Controller")
    plt.ylabel("Volume (ml)")
    plt.xlabel("Time Step")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.show()

if __name__ == "__main__":
    run_comparison()