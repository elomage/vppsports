const {connectDB, getCollection} = require('../config/db');
const { ObjectId } = require('mongodb');


const getSingleTrack = async (trackid) => {
    const db = await connectDB();
    const coll = await getCollection(db, 'Track');
    const objectId = new ObjectId(String(trackid));
    const result = await coll.findOne({ _id: objectId });
    return result;
};

module.exports ={ 
    getSingleTrack,
};