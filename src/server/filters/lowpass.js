/**
 * First-order exponential low-pass (EMA) filter.
 * Passes low-frequency content, attenuates high-frequency noise.
 */
module.exports = {
  id: "lowpass",
  label: "Low-pass",
  description:
    "Exponential moving average filter. Alpha near 0 = heavy smoothing " +
    "(passes only very low frequencies). Alpha near 1 = minimal smoothing.",
  params: [
    {
      key: "alpha",
      label: "Smoothing α (0–1)",
      default: 0.1,
      min: 0.001,
      max: 0.999,
      step: 0.001,
    },
  ],

  apply(readings, params) {
    const alpha = Math.min(
      0.9999,
      Math.max(0.0001, Number.isFinite(params.alpha) ? params.alpha : 0.1),
    );
    const axisCount = readings.reduce(
      (max, r) => Math.max(max, Array.isArray(r.data) ? r.data.length : 0),
      0,
    );
    const prev = new Array(axisCount).fill(null);

    return readings.map((reading) => {
      if (!Array.isArray(reading.data)) return { ...reading };
      const filtered = reading.data.map((value, i) => {
        const out =
          prev[i] === null ? value : alpha * value + (1 - alpha) * prev[i];
        prev[i] = out;
        return out;
      });
      return { ...reading, data: filtered };
    });
  },
};
