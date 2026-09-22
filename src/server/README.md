# VPPSports Server

Here goes the code for the server that hosts database, collects data from the hub and servers data to the client.

# Setup

## Install dependencies

```
npm install
```
## Database
Create a MongoDB database. Copy the connection string.

## .ENV file structure
Create .env file in current directory and add lines described in the .ENV faile structure
```
PORT=... (port that the server will run on, should match the frontend .env port)
HOST=... (adress, that hosts the server, exmaple localhost)
MONGODB_URI=... (database connection string, the name of the database is added after a slash, example, mongodb://localhost:27017/DatabaseName)
ALLOWED_ORIGINS=... (allowed origins seperated by a comma, example, http://localhost:8080)
JWT_ACCESS_SECRET=... (at least 32 chars)
JWT_REFRESH_SECRET=... (at least 32 chars, different from access secret)
ACCESS_TOKEN_TTL=... (optional, default 15m)
REFRESH_TOKEN_TTL=... (optional, default 7d)
JWT_ISSUER=... (optional, default vppsports-api)
JWT_AUDIENCE=... (optional, default vppsports-client)
ADMIN_USERNAME=... (required for `npm run seed:user`)
ADMIN_PASSWORD=... (required for `npm run seed:user`, 12-128 chars)
ADMIN_CONTEXT_ROLES=... (optional, comma-separated `context:role`)
```

## Seed initial admin user

Run this from `src/server`:

`npm run seed:user`

or

`npm run seed:admin`


## Start the server

Run the backend server in dev with
```
node index.js
```
