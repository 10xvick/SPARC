# TeamSight Dashboard Service Management

This document explains how to use the `manage.sh` script to manage the TeamSight Dashboard services.

## Quick Start

```bash
# Start all services
./manage.sh start

# Check status
./manage.sh status

# Stop all services
./manage.sh stop

# Restart all services
./manage.sh restart
```

## Commands

### Start Services

Start all services (backend + frontend):
```bash
./manage.sh start
# or
./manage.sh start all
```

Start only backend:
```bash
./manage.sh start backend
```

Start only frontend:
```bash
./manage.sh start frontend
```

### Stop Services

Stop all services:
```bash
./manage.sh stop
# or
./manage.sh stop all
```

Stop only backend:
```bash
./manage.sh stop backend
```

Stop only frontend:
```bash
./manage.sh stop frontend
```

### Restart Services

Restart all services:
```bash
./manage.sh restart
# or
./manage.sh restart all
```

Restart only backend:
```bash
./manage.sh restart backend
```

Restart only frontend:
```bash
./manage.sh restart frontend
```

### Check Status

Check the status of all services:
```bash
./manage.sh status
```

This will show:
- Whether each service is running
- Process IDs (PIDs)
- Whether services are responding to requests
- Service URLs

### View Logs

View last 50 lines of backend logs:
```bash
./manage.sh logs backend
```

View last 100 lines of backend logs:
```bash
./manage.sh logs backend 100
```

View frontend logs:
```bash
./manage.sh logs frontend
```

### Follow Logs (Real-time)

Follow backend logs in real-time (Ctrl+C to stop):
```bash
./manage.sh follow backend
```

Follow frontend logs in real-time:
```bash
./manage.sh follow frontend
```

## Service Details

### Backend
- **Port**: 8000
- **URL**: http://127.0.0.1:8000
- **Health Check**: http://127.0.0.1:8000/health
- **Technology**: FastAPI (Python)
- **Log File**: `logs/backend.log`
- **PID File**: `.pids/backend.pid`

### Frontend
- **Port**: 5173
- **URL**: http://localhost:5173
- **Technology**: React + Vite
- **Log File**: `logs/frontend.log`
- **PID File**: `.pids/frontend.pid`

## Troubleshooting

### Services won't start

1. Check if ports are already in use:
   ```bash
   lsof -ti:8000  # Backend
   lsof -ti:5173  # Frontend
   ```

2. Clean up orphaned processes:
   ```bash
   ./manage.sh stop all
   ```

3. Check logs for errors:
   ```bash
   ./manage.sh logs backend
   ./manage.sh logs frontend
   ```

### Backend not responding

1. Check backend status:
   ```bash
   ./manage.sh status
   ```

2. View backend logs:
   ```bash
   ./manage.sh logs backend 100
   ```

3. Restart backend:
   ```bash
   ./manage.sh restart backend
   ```

### Frontend not loading

1. Check frontend status:
   ```bash
   ./manage.sh status
   ```

2. View frontend logs:
   ```bash
   ./manage.sh logs frontend 100
   ```

3. Restart frontend:
   ```bash
   ./manage.sh restart frontend
   ```

### Port conflicts

The script automatically detects and cleans up processes on ports 8000 and 5173 when starting services. If you encounter issues:

```bash
# Stop all services and clean up ports
./manage.sh stop all

# Wait a moment
sleep 2

# Start services again
./manage.sh start all
```

## Development Workflow

### Making Backend Changes

When you modify backend code:
```bash
# Backend has auto-reload, no restart needed
# But if you need to restart:
./manage.sh restart backend
```

### Making Frontend Changes

When you modify frontend code:
```bash
# Frontend has HMR (Hot Module Replacement), no restart needed
# But if you need to restart:
./manage.sh restart frontend
```

### Viewing Live Logs

During development, you might want to see logs in real-time:

```bash
# Terminal 1: Follow backend logs
./manage.sh follow backend

# Terminal 2: Follow frontend logs
./manage.sh follow frontend
```

## File Locations

- **Management Script**: `dashboard/manage.sh`
- **PID Files**: `dashboard/.pids/`
- **Log Files**: `dashboard/logs/`
- **Backend Directory**: `dashboard/backend/`
- **Frontend Directory**: `dashboard/frontend/`

## Examples

### Daily Development Start

```bash
cd /path/to/TeamSight/dashboard
./manage.sh start all
./manage.sh status
```

### End of Day Cleanup

```bash
cd /path/to/TeamSight/dashboard
./manage.sh stop all
```

### Debugging Issues

```bash
# Check what's running
./manage.sh status

# View recent backend errors
./manage.sh logs backend 200 | grep -i error

# Restart problematic service
./manage.sh restart backend

# Follow logs to see what happens
./manage.sh follow backend
```

### Quick Health Check

```bash
# One command to see everything
./manage.sh status
```

Output example:
```
═══════════════════════════════════════
  Service Status
═══════════════════════════════════════

Backend:
✓ Running (PID: 31646)
✓ Responding on http://127.0.0.1:8000

Frontend:
✓ Running (PID: 31662)
✓ Responding on http://localhost:5173
```
