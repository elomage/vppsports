/**
 * Moving average filter — smooths a signal by averaging over a sliding window.
 */
module.exports = {
  id: "movingaverage",
  label: "Mov Avg",
  description:
    "Replaces each sample with the mean of the surrounding window. " +
    "Larger windows produce heavier smoothing at the cost of lag.",
  params: [
    {
      key: "windowSize",
      label: "Window size",
      default: 50,
      min: 2,
      max: 2000,
      step: 1,
      integer: true,
    },
  ],

  apply(readings, params) {
    const windowSize = Math.max(
      2,
      Math.round(Number.isFinite(params.windowSize) ? params.windowSize : 50),
    );
    const axisCount = readings.reduce(
      (max, r) => Math.max(max, Array.isArray(r.data) ? r.data.length : 0),
      0,
    );

    const smoothedAxes = Array.from({ length: axisCount }, (_, axisIndex) => {
      const values = readings.map((r) => r.data?.[axisIndex] ?? 0);
      return values.map((_, i, arr) => {
        const start = Math.max(i - windowSize + 1, 0);
        const subset = arr.slice(start, i + 1);
        return subset.reduce((a, b) => a + b, 0) / subset.length;
      });
    });

    return readings.map((reading, idx) => ({
      ...reading,
      data: Array.isArray(reading.data)
        ? reading.data.map((_, axisIndex) => smoothedAxes[axisIndex][idx])
        : reading.data,
    }));
  },
};
