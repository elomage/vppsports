/** 
 * This is a test filter to inver x axis 
*/

module.exports = {
  id: "invertx",
  label: "Invert X-axis",
  description: "Inverts the x-axis values of the data.",
  params: [],

  apply: (readings, params) => {
    return readings.map((reading) => ({
      ...reading,
      x: -reading.x
    }));
  }
};