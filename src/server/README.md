# VPPSports Server

Here goes the code for the server that hosts database, collects data from the hub and servers data to the client.

## .ENV file structure

PORT=...
MONGODB_URI=...
ALLOWED_ORIGINS=... (allowed origins seperated by a comma)
JWT_ACCESS_SECRET=... (at least 32 chars)
JWT_REFRESH_SECRET=... (at least 32 chars, different from access secret)
ACCESS_TOKEN_TTL=... (optional, default 15m)
REFRESH_TOKEN_TTL=... (optional, default 7d)
JWT_ISSUER=... (optional, default vppsports-api)
JWT_AUDIENCE=... (optional, default vppsports-client)
ADMIN_USERNAME=... (required for `npm run seed:user`)
ADMIN_PASSWORD=... (required for `npm run seed:user`, 12-128 chars)
ADMIN_CONTEXT_ROLES=... (optional, comma-separated `context:role`)

## Seed initial admin user

Run this from `src/server`:

`npm run seed:user`

or

`npm run seed:admin`