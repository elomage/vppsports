const trackService = require("../services/trackService");

const getSingleTrack = async (trackid) => {
  try {
    const run = await trackService.getSingleTrack(trackid);
    return run;
  } catch (error) {
    // throw new Error(error.message);
    return null;
  }
};

module.exports = {
  getSingleTrack,
};
