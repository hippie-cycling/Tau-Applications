import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
STEPS = 350
TARGET_VOLUME = 0.5
PISTON_FACTOR = 0.1
MAX_AMP = 10.0
ANIMATION_SPEED = 30  # Faster animation

def generate_disturbances():
    np.random.seed(42)
    data = {
        'step': range(STEPS),
        'noise': np.random.normal(0, 0.005, STEPS), 
        'load_factor': [1.0] * STEPS
    }
    df = pd.DataFrame(data)

    # BLOCKAGE EVENT (Trigger for Integral Wind-up)
    # Between step 100 and 200, the pipe is 90% blocked.
    # The motor will max out, but volume will still be too low.
    # The Integral term will scream "MORE POWER" and accumulate massive numbers.
    df.loc[100:200, 'load_factor'] = 0.15 
    
    return df

# ==============================================================================
# 2. PHYSICS PLANT
# ==============================================================================
class PistonPump:
    def __init__(self):
        self.amplitude = 0.0
    
    def update(self, target_amp, noise, load):
        # Mechanical Lag
        self.amplitude += (target_amp - self.amplitude) * 0.4
        
        # Physics: Vol = Amp * Factor * Load + Noise
        actual_volume = (self.amplitude * PISTON_FACTOR * load) + noise
        return max(0, actual_volume)

# ==============================================================================
# 3. BADLY TUNED PID
# ==============================================================================
class BadPID:
    def __init__(self, kp, ki, kd):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.prev_error = 0
        self.integral = 0
        
    def compute(self, setpoint, measured_val):
        error = setpoint - measured_val
        
        # INTEGRAL WIND-UP TRAP:
        # We removed the "clamp" (max/min). 
        # Now the integral can grow to infinity if the error persists.
        self.integral += error
        
        p = self.kp * error
        i = self.ki * self.integral
        d = self.kd * (error - self.prev_error)
        
        self.prev_error = error
        
        # Return total requested amplitude
        return p + i + d

# ==============================================================================
# 4. REALTIME ANIMATION
# ==============================================================================
def run_animation():
    disturbances = generate_disturbances()
    plant = PistonPump()
    
    # --- TUNING FOR DISASTER ---
    # Kp = 8.0 (Too High -> Causes Oscillation)
    # Ki = 1.5 (Too High + Unclamped -> Causes Wind-up)
    # Kd = 0.0 (No Damping -> Allows Oscillation to run wild)
    pid = BadPID(kp=8.0, ki=1.5, kd=0.0)
    
    current_amp = 0.0
    
    # Data storage
    x_data, vol_data, amp_data = [], [], []
    
    # Setup Figure
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    plt.subplots_adjust(hspace=0.4)
    
    # Plot 1: Volume
    ax1.set_xlim(0, STEPS)
    ax1.set_ylim(0.0, 1.5) # Zoomed out to show the massive overshoot
    ax1.set_title("Result: Flow Volume (ml)")
    ax1.set_ylabel("Volume (ml)")
    ax1.axhline(y=TARGET_VOLUME, color='k', linestyle='--', alpha=0.5, label="Target")
    
    line_vol, = ax1.plot([], [], 'r-', lw=2, label="Measured Flow")
    status_text = ax1.text(0.02, 0.9, "", transform=ax1.transAxes, fontweight='bold')
    
    # Highlight the Blockage Zone
    rect = plt.Rectangle((100, 0), 100, 2.0, color='gray', alpha=0.2)
    ax1.add_patch(rect)
    ax1.text(110, 1.3, "PIPE BLOCKED (Load 90%)", color='gray', fontweight='bold')
    
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)

    # Plot 2: Piston Amplitude
    ax2.set_xlim(0, STEPS)
    ax2.set_ylim(0, 12)
    ax2.set_title("Controller Output: Piston Amplitude")
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
        
        row = disturbances.iloc[frame]
        noise = row['noise']
        load = row['load_factor']
        
        # Physics
        measured_vol = plant.update(current_amp, noise, load)
        
        # PID
        adjustment = pid.compute(TARGET_VOLUME, measured_vol)
        current_amp += adjustment
        current_amp = max(0, min(MAX_AMP, current_amp)) # Mechanical Limit
        
        # Store
        x_data.append(frame)
        vol_data.append(measured_vol)
        amp_data.append(current_amp)
        
        # Update Lines
        line_vol.set_data(x_data, vol_data)
        line_amp.set_data(x_data, amp_data)
        
        # UI Status Updates
        if frame < 100:
            status_text.set_text("STATE: OSCILLATING (High Kp)")
            status_text.set_color("orange")
        elif frame >= 100 and frame < 200:
            status_text.set_text("STATE: SATURATED (Integrator Winding Up...)")
            status_text.set_color("red")
        elif frame >= 200 and measured_vol > 0.6:
            status_text.set_text("STATE: INTEGRAL WIND-UP FAILURE")
            status_text.set_color("purple")
        else:
            status_text.set_text("STATE: RECOVERING")
            status_text.set_color("green")

        return line_vol, line_amp, status_text

    ani = FuncAnimation(fig, update, frames=range(STEPS), 
                        init_func=init, blit=True, interval=ANIMATION_SPEED, repeat=False)
    
    plt.show()

if __name__ == "__main__":
    run_animation()