# Production Deployment Guide (Client + Server)

## Prerequisites

- Docker and Docker Compose installed
- hosted MongoDB instance

## Deployment Steps

### 1. (Locally) Build and Push Images to DockerHub

```bash
# Build backend image
cd src/server
docker build -t dockerhub-username/vppsport-backend:latest .
docker push dockerhub-username/vppsport-backend:latest

# Build frontend image
cd ../client
docker build --build-arg VITE_SERVER_URL=http://adress:port -t dockerhub-username/vppsport-frontend:latest .
docker push dockerhub-username/vppsport-frontend:latest
```

### 2. (On server) Setup server

#### Create compose file ( pull images ) `docker-compose.yml`
```bash
services:
  backend:
    image: dockerhub-username/vppsport-backend:latest
    container_name: vppsport-backend
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - PORT=8080
      - MONGODB_URI=${MONGODB_URI}
      - JWT_ACCESS_SECRET=${JWT_ACCESS_SECRET}
      - JWT_REFRESH_SECRET=${JWT_REFRESH_SECRET}
      - ADMIN_USERNAME=${ADMIN_USERNAME}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - ALLOWED_ORIGINS=${ALLOWED_ORIGINS}
      - NODE_ENV=production
    networks:
      - vppsport-network

  frontend:
    image: dockerhub-username/vppsport-frontend:latest
    container_name: vppsport-frontend
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - backend
    networks:
      - vppsport-network

networks:
  vppsport-network:
    driver: bridge
```

#### Create .env file in the same directory

```bash
# MongoDB Connection
MONGODB_URI= ...

JWT_ACCESS_SECRET= ...
JWT_REFRESH_SECRET= ...

# Single user credentials
ADMIN_USERNAME= ...
ADMIN_PASSWORD= ...

# CORS Origins (comma-separated list)
# Include your production domain/server
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com,http://your-server-ip:port

# Server binding/public URL
HOST= ...
SERVER_PUBLIC_URL= ...

# Frontend backend URL
VITE_SERVER_URL= ...

```

### 3. Start Services

```bash
# Pull images
docker-compose pull
docker-compose up -d

# Check status
docker-compose ps
```

### 6. Seed user (First Time Only)

```bash
docker exec vppsport-backend npm run seed:user
```


## Monitoring & Maintenance

```bash
# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Restart services
docker-compose restart

# Update to latest images
docker-compose pull
docker-compose up -d

# Stop services
docker-compose down

# Remove everything including volumes
docker-compose down -v
```
