import subprocess
import pandas as pd
import matplotlib.pyplot as plt
import time
import sys

# ==============================================================================
# CONFIGURATION
# ==============================================================================
TAU_EXECUTABLE = "tau"  # or "tau.exe" on Windows
TAU_SCRIPT = "controller.tau"
TARGET_VOLUME = 0.5     # ml
PISTON_FACTOR = 0.1     # 1 mm movement = 0.1 ml volume
MAX_AMP = 10.0          # Max piston travel mm

# Scaling for Tau (0.5ml -> 50 in BitVector)
# We multiply floats by 100 to get integers for the 8-bit solver
SCALE = 100.0 

# ==============================================================================
# 1. THE PHYSICS PLANT (The Motor)
# ==============================================================================
class PistonPump:
    def __init__(self, name):
        self.name = name
        self.amplitude = 0.0 # Current piston stroke in mm
    
    def update(self, target_amp, noise, load):
        # Mechanical lag (motor doesn't move instantly)
        # It moves 50% of the way to the target per step (First order lag)
        self.amplitude += (target_amp - self.amplitude) * 0.5
        
        # Physics Equation
        # Volume = (Amplitude * Factor * Efficiency) + SensorNoise
        actual_volume = (self.amplitude * PISTON_FACTOR * load) + noise
        return max(0, actual_volume)

# ==============================================================================
# 2. CLASSIC PID CONTROLLER
# ==============================================================================
class PID:
    def __init__(self, kp, ki, kd):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.prev_error = 0
        self.integral = 0
        
    def compute(self, setpoint, measured_val):
        error = setpoint - measured_val
        
        # Proportional
        p_out = self.kp * error
        
        # Integral
        self.integral += error
        i_out = self.ki * self.integral
        
        # Derivative
        derivative = error - self.prev_error
        d_out = self.kd * derivative
        
        self.prev_error = error
        
        # Output is the CHANGE in amplitude needed
        output = p_out + i_out + d_out
        return output

# ==============================================================================
# 3. TAU CONTROLLER WRAPPER
# ==============================================================================
class TauController:
    def __init__(self):
        # Start the Tau process
        self.process = subprocess.Popen(
            [TAU_EXECUTABLE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        # Feed the spec file content via stdin (or load file if preferred)
        # Here we assume we run `tau < controller.tau` style logic
        # But for interactive, we'll pipe the spec first.
        with open(TAU_SCRIPT, 'r') as f:
            spec = f.read()
            self.process.stdin.write(spec + "\n")
            self.process.stdin.flush()
            
    def compute(self, measured_val):
        # 1. Convert float measurement to Hex BitVector (0.54 -> 54 -> #x36)
        int_val = int(measured_val * SCALE)
        int_val = max(0, min(255, int_val)) # Clamp to 8-bit
        hex_val = f"#x{int_val:02X}"
        
        # 2. Send Input to Tau: "i1[t] := #x36"
        # Note: The Tau REPL usually prompts. We blindly write to stdin.
        # This part depends heavily on the REPL version. 
        # For the alpha REPL, we usually pipe the full logic file first, 
        # then it waits for input.
        
        try:
            # Send input
            # We assume the REPL is asking for i1
            # Format depends on your specific REPL prompt interaction
            input_str = f"{hex_val}\n"
            self.process.stdin.write(input_str)
            self.process.stdin.flush()
            
            # 3. Read Output
            # We need to parse the line "o1[t] := #x..."
            while True:
                line = self.process.stdout.readline()
                if "o1[" in line:
                    # Parse output
                    # Example: "o1[0] := 13" or "o1[0] := #x0D"
                    parts = line.split(":= ")
                    if len(parts) > 1:
                        val_str = parts[1].strip()
                        # Handle Hex or Decimal
                        if "#x" in val_str:
                            val = int(val_str.replace("#x", ""), 16)
                        elif "#b" in val_str:
                            val = int(val_str.replace("#b", ""), 2)
                        elif val_str == "T": val = 1
                        elif val_str == "F": val = 0
                        else:
                            # Sometimes it might return a raw number
                            try:
                                val = int(val_str)
                            except:
                                val = 0 # Fallback
                        
                        # Convert back to float scale
                        return float(val) / SCALE * 10.0 # scaling factor back to mm logic
                
                # Break if process died
                if not line and self.process.poll() is not None:
                    break
        except Exception as e:
            print(f"Tau Error: {e}")
            return 0.0
            
    def close(self):
        self.process.terminate()

# ==============================================================================
# MAIN SIMULATION LOOP
# ==============================================================================
def run_simulation():
    # Load Disturbances
    disturbances = pd.read_csv('disturbance_profile.csv')
    
    # Init Plants
    plant_pid = PistonPump("PID_System")
    plant_tau = PistonPump("Tau_System")
    
    # Init Controllers
    # Tuned PID (Guesswork)
    pid = PID(kp=2.0, ki=0.1, kd=0.05) 
    tau = TauController()
    
    # Storage for Plotting
    history = {
        'time': [],
        'pid_vol': [], 'pid_amp': [],
        'tau_vol': [], 'tau_amp': [],
        'target': [], 'noise': []
    }
    
    # Initial Conditions
    current_amp_pid = 0.0
    current_amp_tau = 0.0
    
    print("Starting Simulation...")
    
    for i, row in disturbances.iterrows():
        noise = row['noise']
        load = row['load_factor']
        
        # --- PID LOOP ---
        # 1. Measure
        meas_pid = plant_pid.update(current_amp_pid, noise, load)
        # 2. Compute (PID returns adjustment)
        adjustment = pid.compute(TARGET_VOLUME, meas_pid)
        current_amp_pid += adjustment
        # Clamp
        current_amp_pid = max(0, min(MAX_AMP, current_amp_pid))
        
        # --- TAU LOOP ---
        # 1. Measure
        meas_tau = plant_tau.update(current_amp_tau, noise, load)
        # 2. Compute (Tau returns Absolute Target usually, or we can make it return adjustment)
        # Let's assume Tau logic returns the Desired Amplitude directly.
        tau_out = tau.compute(meas_tau)
        
        # Tau logic usually defines absolute states (0, 50, 100 power). 
        # We will map 0-100 output to 0-10mm Amplitude.
        # But wait, our previous Tau code output "Heater Power". 
        # For a piston, let's say Tau controls the "Throttle" (Amplitude).
        current_amp_tau = tau_out 

        # --- LOGGING ---
        history['time'].append(i)
        history['pid_vol'].append(meas_pid)
        history['pid_amp'].append(current_amp_pid)
        history['tau_vol'].append(meas_tau)
        history['tau_amp'].append(current_amp_tau)
        history['target'].append(TARGET_VOLUME)
        history['noise'].append(noise)
        
        if i % 10 == 0:
            print(f"Step {i}: PID={meas_pid:.2f}ml | Tau={meas_tau:.2f}ml")

    tau.close()
    
    # --- PLOTTING ---
    plt.figure(figsize=(12, 6))
    
    # Subplot 1: Volume (Performance)
    plt.subplot(2, 1, 1)
    plt.plot(history['time'], history['target'], 'k--', label='Target (0.5ml)')
    plt.plot(history['time'], history['pid_vol'], 'r-', label='PID Control', alpha=0.7)
    plt.plot(history['time'], history['tau_vol'], 'b-', label='Tau Control', linewidth=2)
    plt.title('Performance: PID vs Tau Logic')
    plt.ylabel('Stroke Volume (ml)')
    plt.legend()
    plt.grid(True)
    
    # Subplot 2: Controller Action (Amplitude)
    plt.subplot(2, 1, 2)
    plt.plot(history['time'], history['pid_amp'], 'r-', label='PID Action (mm)', alpha=0.5)
    plt.plot(history['time'], history['tau_amp'], 'b-', label='Tau Action (mm)', alpha=0.5)
    # Highlight Glitch Area
    plt.axvspan(40, 42, color='yellow', alpha=0.3, label='Sensor Glitch')
    plt.ylabel('Piston Amp (mm)')
    plt.xlabel('Time Step')
    plt.legend()
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_simulation()