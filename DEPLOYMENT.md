# Production Deployment Guide

## Prerequisites on Server

1. Docker and Docker Compose installed
2. Domain name configured (optional but recommended)
3. SSL certificate (use Let's Encrypt with nginx-proxy or Traefik)

## Deployment Steps

### 1. Build and Push Images to DockerHub

```bash
# Build backend image
cd src/server
docker build -t your-dockerhub-username/vppsport-backend:latest .
docker push your-dockerhub-username/vppsport-backend:latest

# Build frontend image (with production backend URL)
cd ../client
docker build --build-arg VITE_SERVER_URL=https://api.yourdomain.com -t your-dockerhub-username/vppsport-frontend:latest .
docker push your-dockerhub-username/vppsport-frontend:latest
```

### 2. Server Setup

```bash
# On your production server
mkdir vppsport
cd vppsport

# Copy docker-compose.prod.yml to the server
wget https://your-repo/docker-compose.prod.yml -O docker-compose.yml

# Create .env file
nano .env
```

### 3. Configure Environment Variables

Copy `.env.production` template and update with your production values:

**Required Variables:**

| Variable | Description | Example |
|----------|-------------|---------|
| `MONGODB_URI` | MongoDB connection string | `mongodb+srv://...` or `mongodb://localhost:27017/db` |
| `JWT_ACCESS_SECRET` | Secret for access tokens (min 32 chars) | Random string |
| `JWT_REFRESH_SECRET` | Secret for refresh tokens (min 32 chars) | Random string |
| `ADMIN_USERNAME` | Admin user username | `admin` |
| `ADMIN_PASSWORD` | Admin user password (min 12 chars) | Strong password |
| `ALLOWED_ORIGINS` | Comma-separated allowed origins | `https://yourdomain.com,https://api.yourdomain.com` |

**Important Security Notes:**
- Generate strong random secrets for JWT tokens
- Use HTTPS in production (update ALLOWED_ORIGINS accordingly)
- Use a strong admin password
- Never commit `.env` to version control

### 4. Update docker-compose.prod.yml

Replace `your-dockerhub-username` with your actual DockerHub username:

```yaml
image: your-dockerhub-username/vppsport-backend:latest
image: your-dockerhub-username/vppsport-frontend:latest
```

Update port mapping if using a reverse proxy:
- Frontend: Change `"80:80"` to `"3000:80"` if using nginx/traefik
- Backend: Port 8080 or as needed

### 5. Start Services

```bash
# Pull latest images and start
docker-compose pull
docker-compose up -d

# Check logs
docker-compose logs -f

# Check status
docker-compose ps
```

### 6. Seed Admin User (First Time Only)

```bash
docker exec vppsport-backend npm run seed:user
```

## Frontend Build Considerations

**Important:** The frontend needs to be built with the correct backend URL.

When building for production, specify the backend URL:

```bash
cd src/client
docker build \
  --build-arg VITE_SERVER_URL=https://api.yourdomain.com \
  -t your-dockerhub-username/vppsport-frontend:latest .
```

Or if backend is on same domain:
```bash
docker build \
  --build-arg VITE_SERVER_URL=https://yourdomain.com \
  -t your-dockerhub-username/vppsport-frontend:latest .
```

## CORS Configuration

The backend will allow requests from origins listed in `ALLOWED_ORIGINS`.

**Example configurations:**

**Same domain (frontend and backend):**
```env
ALLOWED_ORIGINS=https://yourdomain.com
```

**Separate subdomains:**
```env
ALLOWED_ORIGINS=https://app.yourdomain.com,https://api.yourdomain.com
```

**Multiple domains:**
```env
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com,https://backup-domain.com
```

## Reverse Proxy Setup (Recommended)

Use nginx or Traefik as a reverse proxy for:
- SSL termination
- Single entry point
- Load balancing

**Example nginx config:**

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /auth/ {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /run/ {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /sensor/ {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
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

## Troubleshooting

### CORS Errors
- Check `ALLOWED_ORIGINS` includes your frontend URL
- Verify protocol (http vs https)
- Check browser console for exact origin being blocked

### Cannot Connect to Backend
- Verify backend is running: `docker-compose ps`
- Check backend logs: `docker-compose logs backend`
- Ensure MONGODB_URI is correct and accessible
- Test backend directly: `curl http://localhost:8080/api/health`

### Database Connection Failed
- Verify MONGODB_URI is correct
- Check if MongoDB allows connections from your server IP
- Test connection: `docker exec vppsport-backend node -e "require('mongoose').connect(process.env.MONGODB_URI).then(() => console.log('OK'))"`
