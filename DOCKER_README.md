# Docker Configuration

This application can be run with either the Flask development server or Gunicorn production server using Docker.

## Environment Variables

- `SERVER_TYPE`: Choose between `flask` (development) or `gunicorn` (production)
  - Default: `flask`

## Usage Examples

### 1. Using Docker Run

**Flask Development Server (default):**

```bash
docker build -t cm-testing-webapp .
docker run -p 5001:5001 cm-testing-webapp
```

**Gunicorn Production Server:**

```bash
docker run -p 5001:5001 -e SERVER_TYPE=gunicorn cm-testing-webapp
```

### 2. Using Docker Compose

**Flask Development Server:**

```bash
docker-compose up webapp-flask
```

**Gunicorn Production Server:**

```bash
docker-compose up webapp-gunicorn
```

### 3. Custom Configuration

You can override the default Gunicorn configuration by setting additional environment variables:

```bash
docker run -p 5001:5001 \
  -e SERVER_TYPE=gunicorn \
  -e GUNICORN_WORKERS=8 \
  -e GUNICORN_TIMEOUT=120 \
  cm-testing-webapp
```

## Server Comparison

| Feature | Flask Dev Server | Gunicorn |
|---------|------------------|----------|
| **Use Case** | Development, debugging | Production |
| **Performance** | Single-threaded | Multi-worker, multi-threaded |
| **Auto-reload** | Yes | No |
| **Debug Mode** | Yes | No |
| **Scalability** | Limited | High |
| **Resource Usage** | Low | Higher |

## Ports

- **5001**: Application port (both Flask and Gunicorn)
- **8000**: Reserved for future use

## Production Recommendations

For production deployments, always use:

- `SERVER_TYPE=gunicorn`
- Appropriate number of workers (typically 2-4 per CPU core)
- Proper logging configuration
- Health checks
- Load balancer in front of multiple instances
