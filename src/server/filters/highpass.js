/**
 * First-order high-pass filter.
 * Passes high-frequency content, removes slow drift and DC offset.
 */
module.exports = {
  id: "highpass",
  label: "High-pass",
  description:
    "Removes slow drift and DC offset. Alpha near 1 = passes most frequencies " +
    "(gentle high-pass). Alpha near 0 = only the fastest changes pass through.",
  params: [
    {
      key: "alpha",
      label: "Cutoff α (0–1)",
      default: 0.9,
      min: 0.001,
      max: 0.999,
      step: 0.001,
    },
  ],

  apply(readings, params) {
    const alpha = Math.min(
      0.9999,
      Math.max(0.0001, Number.isFinite(params.alpha) ? params.alpha : 0.9),
    );
    const axisCount = readings.reduce(
      (max, r) => Math.max(max, Array.isArray(r.data) ? r.data.length : 0),
      0,
    );
    const prevRaw = new Array(axisCount).fill(null);
    const prevHP = new Array(axisCount).fill(0);

    return readings.map((reading) => {
      if (!Array.isArray(reading.data)) return { ...reading };
      const filtered = reading.data.map((value, i) => {
        const out =
          prevRaw[i] === null
            ? 0
            : alpha * (prevHP[i] + value - prevRaw[i]);
        prevRaw[i] = value;
        prevHP[i] = out;
        return out;
      });
      return { ...reading, data: filtered };
    });
  },
};
