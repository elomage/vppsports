# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Accept build argument for backend URL
ARG VITE_SERVER_URL=http://localhost:8080

COPY package*.json ./

RUN npm ci --force

COPY . .

# Build with the environment variable
ENV VITE_SERVER_URL=${VITE_SERVER_URL}
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
