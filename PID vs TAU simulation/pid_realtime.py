import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
STEPS = 300
TARGET_VOLUME = 0.5
PISTON_FACTOR = 0.1
MAX_AMP = 10.0
ANIMATION_SPEED = 50  # Milliseconds per frame (Lower = Faster)

def generate_disturbances():
    np.random.seed(42)
    data = {
        'step': range(STEPS),
        'noise': np.random.normal(0, 0.015, STEPS), 
        'load_factor': [1.0] * STEPS
    }
    df = pd.DataFrame(data)

    # GLITCH 1: SPIKE (Step 120)
    df.loc[120:122, 'noise'] += 2.0
    
    # GLITCH 2: DROPOUT (Step 200)
    df.loc[200:202, 'noise'] -= 0.5
    
    # GLITCH 3: NOISE BURST (Step 260)
    df.loc[260:270, 'noise'] += np.random.normal(0, 0.3, 11)
    
    return df

# ==============================================================================
# 2. PHYSICS & CONTROL CLASSES
# ==============================================================================
class PistonPump:
    def __init__(self):
        self.amplitude = 0.0
    
    def update(self, target_amp, noise, load):
        self.amplitude += (target_amp - self.amplitude) * 0.4
        return max(0, (self.amplitude * PISTON_FACTOR * load) + noise)

class PID:
    def __init__(self, kp, ki, kd):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.prev_error = 0
        self.integral = 0
        
    def compute(self, setpoint, measured_val):
        error = setpoint - measured_val
        self.integral += error
        self.integral = max(-50, min(50, self.integral)) # Anti-windup clamp
        
        p = self.kp * error
        i = self.ki * self.integral
        d = self.kd * (error - self.prev_error)
        
        self.prev_error = error
        return p + i + d

# ==============================================================================
# 3. REALTIME SIMULATION
# ==============================================================================
def run_animation():
    # Simulation State
    disturbances = generate_disturbances()
    plant = PistonPump()
    pid = PID(kp=10.0, ki=4.2, kd=2.5)
    
    current_amp = 0.0
    
    # Data storage for plotting
    x_data = []
    vol_data = []
    amp_data = []
    
    # Setup Figure
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    plt.subplots_adjust(hspace=0.3)
    
    # Plot 1: Volume
    ax1.set_xlim(0, STEPS)
    ax1.set_ylim(-0.5, 3.0)
    ax1.set_title("Live Sensor Data (Volume)")
    ax1.set_ylabel("Volume (ml)")
    ax1.axhline(y=TARGET_VOLUME, color='k', linestyle='--', alpha=0.5, label="Target")
    
    line_vol, = ax1.plot([], [], 'r-', lw=2, label="Measured Flow")
    status_text = ax1.text(0.02, 0.9, "", transform=ax1.transAxes, fontweight='bold')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)

    # Plot 2: Piston Amplitude
    ax2.set_xlim(0, STEPS)
    ax2.set_ylim(0, 12)
    ax2.set_title("PID Controller Action (Piston)")
    ax2.set_ylabel("Amplitude (mm)")
    ax2.set_xlabel("Time Step")
    
    line_amp, = ax2.plot([], [], 'b-', lw=2, label="Piston Position")
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)

    def init():
        line_vol.set_data([], [])
        line_amp.set_data([], [])
        return line_vol, line_amp, status_text

    def update(frame):
        nonlocal current_amp
        
        # 1. Get Environment
        row = disturbances.iloc[frame]
        noise = row['noise']
        load = row['load_factor']
        
        # 2. Physics Step
        measured_vol = plant.update(current_amp, noise, load)
        
        # 3. PID Step
        adjustment = pid.compute(TARGET_VOLUME, measured_vol)
        current_amp += adjustment
        current_amp = max(0, min(MAX_AMP, current_amp))
        
        # 4. Update Data Lists
        x_data.append(frame)
        vol_data.append(measured_vol)
        amp_data.append(current_amp)
        
        # 5. Update Lines
        line_vol.set_data(x_data, vol_data)
        line_amp.set_data(x_data, amp_data)
        
        # 6. Detect Glitches for UI
        # We know the glitches are roughly > 1.5 or < 0.1 or chaotic
        # Or we can just peek at the noise value for the UI label
        if noise > 1.0 or noise < -0.4:
            status_text.set_text("⚠️ CRITICAL SENSOR FAILURE ⚠️")
            status_text.set_color("red")
            ax1.set_facecolor("#ffe0e0") # Flash background red
        elif frame >= 260 and frame <= 270:
            status_text.set_text("⚠️ SIGNAL NOISE ⚠️")
            status_text.set_color("orange")
            ax1.set_facecolor("white")
        else:
            status_text.set_text("SYSTEM NORMAL")
            status_text.set_color("green")
            ax1.set_facecolor("white")

        return line_vol, line_amp, status_text, ax1

    # Run Animation
    ani = FuncAnimation(fig, update, frames=range(STEPS), 
                        init_func=init, blit=False, interval=ANIMATION_SPEED, repeat=False)
    
    plt.show()

if __name__ == "__main__":
    run_animation()