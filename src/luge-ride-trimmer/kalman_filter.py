import numpy as np

class AccKalmanFilter:
    def __init__(self, q=1e-4, r=1e-2):
        self.q = q
        self.r = r
        self.x = np.zeros((2, 1))
        self.P = np.eye(2)

    def update(self, z, dt):
        A = np.array([[1, dt],
                      [0, 1]])

        Q = self.q * np.array([
            [dt**4 / 4, dt**3 / 2],
            [dt**3 / 2, dt**2]
        ])

        H = np.array([[1, 0]])

        self.x = A @ self.x
        self.P = A @ self.P @ A.T + Q

        z = np.array([[z]])
        y = z - H @ self.x
        S = H @ self.P @ H.T + self.r
        K = self.P @ H.T @ np.linalg.inv(S)

        self.x = self.x + K @ y
        self.P = (np.eye(2) - K @ H) @ self.P

        return self.x[0, 0]


def apply_kalman_axis(signal, t, q=1e-1, r=1e-4):
    kf = AccKalmanFilter(q=q, r=r)
    filtered = np.zeros_like(signal)

    for i in range(len(signal)):
        if i == 0:
            dt = 0.01
        else:
            dt = t[i] - t[i - 1]
            if dt <= 0:
                dt = np.mean(np.diff(t))

        filtered[i] = kf.update(signal[i], dt)

    return filtered
