import os
import numpy as np


def _load_single_file(filepath):
        data = []
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) != 4:
                        continue
                    try:
                        timestamp, x, y, z = map(float, parts)
                        data.append([timestamp, x, y, z])
                    except ValueError:
                        continue
        except IOError as e:
            print(f"Error reading file {filepath}: {e}")
            return None

        if len(data) == 0:
            return None
        return np.array(data)


class RideDataLoader:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.rides = []

    def load_rides(self):
        rides = []
        files = sorted(os.listdir(self.data_dir))
        for filename in files:
            if filename.endswith(".txt"):
                filepath = os.path.join(self.data_dir, filename)
                ride_data = _load_single_file(filepath)
                if ride_data is not None:
                    rides.append((filename, ride_data))
                else:
                    print(f"Warning: No valid data in file {filename}")
        print(f"Loaded {len(rides)} rides from {self.data_dir}")
        self.rides = rides
        return rides
