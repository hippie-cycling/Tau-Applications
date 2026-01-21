import pandas as pd
import numpy as np

# Simulation settings
steps = 100
normal_noise_std = 0.02 # Small jitter
glitch_magnitude = 2.0  # Massive spike (e.g. sensor wire loose)

# Generate timeline
data = {
    'step': range(steps),
    'noise': np.random.normal(0, normal_noise_std, steps)
}
df = pd.DataFrame(data)

# Inject a massive GLITCH at step 40-42
df.loc[40:42, 'noise'] += glitch_magnitude

# Inject a "Blockage" (Physics drag) at step 70
# This requires the controller to push harder
df['load_factor'] = 1.0
df.loc[70:, 'load_factor'] = 0.8 

df.to_csv('disturbance_profile.csv', index=False)
print("Generated disturbance_profile.csv with glitches.")