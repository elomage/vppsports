const savitzkyGolay = require("ml-savitzky-golay").default;

module.exports = {
  id: "savitzkygolay",
  label: "Sav-Golay",
  description:
    "Polynomial least-squares smoothing filter. Preserves peak height and shape ",
  params: [
    {
      key: "windowSize",
      label: "Window (odd)",
      default: 51,
      min: 5,
      max: 501,
      step: 2,
      integer: true,
    },
    {
      key: "polynomial",
      label: "Polynomial order",
      default: 3,
      min: 2,
      max: 6,
      step: 1,
      integer: true,
    },
  ],

  apply(readings, params) {
    let windowSize = Math.round(
      Number.isFinite(params.windowSize) ? params.windowSize : 51,
    );
    if (windowSize % 2 === 0) windowSize += 1;
    windowSize = Math.max(5, windowSize);

    const polynomial = Math.max(
      2,
      Math.round(Number.isFinite(params.polynomial) ? params.polynomial : 3),
    );
    const options = { windowSize, polynomial, derivative: 0 };

    const axisCount = readings.reduce(
      (max, r) => Math.max(max, Array.isArray(r.data) ? r.data.length : 0),
      0,
    );

    const smoothedAxes = Array.from({ length: axisCount }, (_, axisIndex) =>
      savitzkyGolay(
        readings.map((r) => r.data?.[axisIndex] ?? 0),
        1,
        options,
      ),
    );

    return readings.map((reading, idx) => ({
      ...reading,
      data: Array.isArray(reading.data)
        ? reading.data.map((_, axisIndex) => smoothedAxes[axisIndex][idx])
        : reading.data,
    }));
  },
};
