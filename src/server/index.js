require("dotenv").config();
const app = require("./src/app");
const http = require("http");

// Use environment variables for the port
const PORT = process.env.PORT || 8080;

// Create an HTTP server and start listening
const server = http.createServer(app);

server.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});
