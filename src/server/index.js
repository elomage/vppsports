require("dotenv").config();
const app = require("./src/app");
const http = require("http");

// Use environment variables for the port
const PORT = process.env.PORT || 8080;
const HOST = process.env.HOST || "0.0.0.0";
const SERVER_PUBLIC_URL = process.env.SERVER_PUBLIC_URL || `http://${HOST}:${PORT}`;

// Create an HTTP server and start listening
const server = http.createServer(app);

server.listen(PORT, HOST, () => {
  console.log(`Server is running on ${SERVER_PUBLIC_URL}`);
});
