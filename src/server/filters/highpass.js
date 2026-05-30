module.exports = {
  id: "highpass",
  label: "High-pass",
  description:
    "Removes slow drift",
  params: [
    {
      key: "cutoffHz",
      label: "Cutoff frequency (Hz)",
      default: 0.1,
      min: 0.001,
      max: 100,
      step: 0.001,
    },
  ],

  apply(readings, params) {
    if (!readings || readings.length < 2) return readings;

    const cutoffHz = Number.isFinite(params.cutoffHz) && params.cutoffHz > 0
      ? params.cutoffHz
      : 0.1;

    let dtSum = 0;
    let dtCount = 0;
    for (let i = 1; i < readings.length; i++) {
      const delta = (readings[i].timestamp - readings[i - 1].timestamp) / 1000;
      if (delta > 0) { dtSum += delta; dtCount++; }
    }
    const dt = dtCount > 0 ? dtSum / dtCount : 0.01;

    const alpha = Math.min(0.9999, Math.max(0.0001, 1 / (1 + 2 * Math.PI * cutoffHz * dt)));

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
