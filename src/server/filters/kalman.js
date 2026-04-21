/**
 * Kalman filter — removes noise while tracking a signal over time.
 *
 * Contract:
 *   apply(readings, params) receives Array<{ timestamp: number, data: number[] }>
 *   and returns a NEW array of the same shape (input is not mutated).
 */
const KalmanFilter = require("kalmanjs");

module.exports = {
  id: "kalman",
  label: "Kalman",
  description:
    "Recursive Bayesian filter that balances measurement noise (R) against process noise (Q). " +
    "Higher R trusts the model more; higher Q trusts measurements more.",
  params: [
    {
      key: "R",
      label: "Measurement noise",
      default: 0.01,
      min: 0.0001,
      max: 10,
      step: 0.0001,
    },
    {
      key: "Q",
      label: "Process noise",
      default: 1,
      min: 0.001,
      max: 100,
      step: 0.01,
    },
  ],

  apply(readings, params) {
    const R =
      Number.isFinite(params.R) && params.R > 0 ? params.R : 0.01;
    const Q =
      Number.isFinite(params.Q) && params.Q > 0 ? params.Q : 1;

    const axisCount = readings.reduce(
      (max, r) => Math.max(max, Array.isArray(r.data) ? r.data.length : 0),
      0,
    );
    const filters = Array.from(
      { length: axisCount },
      () => new KalmanFilter({ R, Q }),
    );

    return readings.map((reading) => ({
      ...reading,
      data: Array.isArray(reading.data)
        ? reading.data.map((v, i) => (filters[i] ? filters[i].filter(v) : v))
        : reading.data,
    }));
  },
};
