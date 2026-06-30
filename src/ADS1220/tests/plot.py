import serial
import re
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque

# --- Serial setup ---
# Replace 'COM5' with your Pico's serial port (e.g. '/dev/ttyACM0' on Linux/Mac)
ser = serial.Serial('/dev/tty.usbmodem2101', 115200, timeout=1)

# --- Data setup ---
max_points = 300
data = deque([0]*max_points, maxlen=max_points)

# --- Plot setup ---
fig, ax = plt.subplots()
line, = ax.plot(data)
ax.set_ylim(-8388608, 8388607)  # 24-bit signed ADC range
ax.set_title("ADS1220 Real-Time RAW ADC Values")
ax.set_xlabel("Samples")
ax.set_ylabel("Raw Value")
ax.grid(True, alpha=0.3)

# Regex to extract number after "Raw="
pattern = re.compile(r"Raw=\s*(-?\d+)")

def update(frame):
    # Read multiple lines per update to keep up with serial data
    lines_to_read = 5  # Process up to 5 lines per frame
    for _ in range(lines_to_read):
        if ser.in_waiting:
            line_raw = ser.readline().decode(errors='ignore').strip()
            match = pattern.search(line_raw)
            if match:
                raw = int(match.group(1))
                data.append(raw)
    
    # Update plot
    line.set_ydata(data)
    line.set_xdata(range(len(data)))
    ax.relim()
    ax.autoscale_view(scalex=False, scaley=True)
    
    return line,

# Update every 20ms instead of 100ms for faster refresh
ani = animation.FuncAnimation(fig, update, interval=20, blit=True)
plt.show()
