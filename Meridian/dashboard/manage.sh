#!/bin/bash

# TeamSight Dashboard Service Manager
# Manages backend and frontend services

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
TEAMSIGHT_ENV_FILE="$SCRIPT_DIR/../teamsight_env.sh"

# Load deployment environment variables if present
if [ -f "$TEAMSIGHT_ENV_FILE" ]; then
    # shellcheck source=/dev/null
    source "$TEAMSIGHT_ENV_FILE"
fi

# PID files
PID_DIR="$SCRIPT_DIR/.pids"
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

# Log files
LOG_DIR="$SCRIPT_DIR/logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# Ports
BACKEND_PORT=8000
FRONTEND_PORT=5173
SERVICE_BIND_HOST="${SERVICE_BIND_HOST:-0.0.0.0}"
BACKEND_HEALTH_URL="http://127.0.0.1:${BACKEND_PORT}/health"
FRONTEND_HEALTH_URL="http://localhost:${FRONTEND_PORT}"

# Create necessary directories
mkdir -p "$PID_DIR" "$LOG_DIR"

# Helper functions
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════${NC}\n"
}

# Check if a process is running
is_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        else
            rm -f "$pid_file"
            return 1
        fi
    fi
    return 1
}

# Check if port is in use
is_port_in_use() {
    local port=$1
    lsof -ti:$port > /dev/null 2>&1
}

# Check if URL is responding
check_url() {
    local url=$1

    if command -v curl > /dev/null 2>&1; then
        curl -fsS --max-time 2 "$url" > /dev/null 2>&1
        return $?
    fi

    if command -v wget > /dev/null 2>&1; then
        wget -q -T 2 -O /dev/null "$url" > /dev/null 2>&1
        return $?
    fi

    if command -v python3 > /dev/null 2>&1; then
        python3 - "$url" <<'PY' > /dev/null 2>&1
import sys
import urllib.request

target_url = sys.argv[1]
with urllib.request.urlopen(target_url, timeout=2) as response:
    status_code = getattr(response, "status", 200)
    if status_code >= 400:
        raise SystemExit(1)
PY
        return $?
    fi

    return 1
}

# Wait for URL to become healthy
wait_for_url() {
    local url=$1
    local timeout_seconds=${2:-30}
    local sleep_seconds=${3:-1}
    local elapsed=0

    while [ "$elapsed" -lt "$timeout_seconds" ]; do
        if check_url "$url"; then
            return 0
        fi

        sleep "$sleep_seconds"
        elapsed=$((elapsed + sleep_seconds))
    done

    return 1
}

# Kill process on port
kill_port() {
    local port=$1
    local pids=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$pids" ]; then
        print_info "Killing processes on port $port: $pids"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

# Start backend
start_backend() {
    print_header "Starting Backend"
    
    if is_running "$BACKEND_PID_FILE"; then
        print_warning "Backend is already running (PID: $(cat $BACKEND_PID_FILE))"
        return 0
    fi
    
    # Check if port is in use
    if is_port_in_use $BACKEND_PORT; then
        print_warning "Port $BACKEND_PORT is in use. Cleaning up..."
        kill_port $BACKEND_PORT
    fi
    
    # Check if backend directory exists
    if [ ! -d "$BACKEND_DIR" ]; then
        print_error "Backend directory not found: $BACKEND_DIR"
        return 1
    fi
    
    # Check if venv exists
    if [ ! -f "$BACKEND_DIR/venv/bin/python" ]; then
        print_error "Backend virtual environment not found. Run setup first."
        return 1
    fi
    
    print_info "Starting backend on ${SERVICE_BIND_HOST}:$BACKEND_PORT..."
    cd "$BACKEND_DIR"
    
    # Start backend in background
    nohup ./venv/bin/python -m uvicorn app.main:app --host "$SERVICE_BIND_HOST" --port "$BACKEND_PORT" > "$BACKEND_LOG" 2>&1 &
    local pid=$!
    echo $pid > "$BACKEND_PID_FILE"
    
    if is_running "$BACKEND_PID_FILE"; then
        # Test if backend is responding
        if wait_for_url "$BACKEND_HEALTH_URL" 40 1; then
            print_success "Backend started successfully (PID: $pid)"
            print_info "Backend URL: http://127.0.0.1:$BACKEND_PORT"
            print_info "Backend logs: $BACKEND_LOG"
        else
            print_error "Backend process is running but health check failed after waiting. Check logs: $BACKEND_LOG"
            tail -n 20 "$BACKEND_LOG"
            return 1
        fi
    else
        print_error "Backend failed to start. Check logs: $BACKEND_LOG"
        tail -n 20 "$BACKEND_LOG"
        return 1
    fi
}

# Stop backend
stop_backend() {
    print_header "Stopping Backend"
    
    if is_running "$BACKEND_PID_FILE"; then
        local pid=$(cat "$BACKEND_PID_FILE")
        print_info "Stopping backend (PID: $pid)..."
        kill $pid 2>/dev/null || true
        sleep 1
        
        # Force kill if still running
        if ps -p $pid > /dev/null 2>&1; then
            print_warning "Backend still running, force killing..."
            kill -9 $pid 2>/dev/null || true
            sleep 1
        fi
        
        rm -f "$BACKEND_PID_FILE"
        print_success "Backend stopped"
    else
        print_warning "Backend is not running"
    fi
    
    # Clean up any orphaned processes on the port
    if is_port_in_use $BACKEND_PORT; then
        print_warning "Cleaning up orphaned processes on port $BACKEND_PORT..."
        kill_port $BACKEND_PORT
    fi
}

# Start frontend
start_frontend() {
    print_header "Starting Frontend"
    
    if is_running "$FRONTEND_PID_FILE"; then
        print_warning "Frontend is already running (PID: $(cat $FRONTEND_PID_FILE))"
        return 0
    fi
    
    # Check if port is in use
    if is_port_in_use $FRONTEND_PORT; then
        print_warning "Port $FRONTEND_PORT is in use. Cleaning up..."
        kill_port $FRONTEND_PORT
    fi
    
    # Check if frontend directory exists
    if [ ! -d "$FRONTEND_DIR" ]; then
        print_error "Frontend directory not found: $FRONTEND_DIR"
        return 1
    fi
    
    # Check if node_modules exists
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        print_error "Frontend dependencies not installed. Run 'npm install' first."
        return 1
    fi
    
    print_info "Starting frontend on ${SERVICE_BIND_HOST}:$FRONTEND_PORT..."
    cd "$FRONTEND_DIR"
    
    # Start frontend in background
    nohup npm run dev -- --host "$SERVICE_BIND_HOST" --port "$FRONTEND_PORT" > "$FRONTEND_LOG" 2>&1 &
    local pid=$!
    echo $pid > "$FRONTEND_PID_FILE"
    
    if is_running "$FRONTEND_PID_FILE"; then
        # Test if frontend is responding
        if wait_for_url "$FRONTEND_HEALTH_URL" 40 1; then
            print_success "Frontend started successfully (PID: $pid)"
            print_info "Frontend URL: http://localhost:$FRONTEND_PORT"
            print_info "Frontend logs: $FRONTEND_LOG"
        else
            print_error "Frontend process is running but health check failed after waiting. Check logs: $FRONTEND_LOG"
            tail -n 20 "$FRONTEND_LOG"
            return 1
        fi
    else
        print_error "Frontend failed to start. Check logs: $FRONTEND_LOG"
        tail -n 20 "$FRONTEND_LOG"
        return 1
    fi
}

# Stop frontend
stop_frontend() {
    print_header "Stopping Frontend"
    
    if is_running "$FRONTEND_PID_FILE"; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        print_info "Stopping frontend (PID: $pid)..."
        
        # Kill the process and all its children
        pkill -P $pid 2>/dev/null || true
        kill $pid 2>/dev/null || true
        sleep 1
        
        # Force kill if still running
        if ps -p $pid > /dev/null 2>&1; then
            print_warning "Frontend still running, force killing..."
            kill -9 $pid 2>/dev/null || true
            pkill -9 -P $pid 2>/dev/null || true
            sleep 1
        fi
        
        rm -f "$FRONTEND_PID_FILE"
        print_success "Frontend stopped"
    else
        print_warning "Frontend is not running"
    fi
    
    # Clean up any orphaned processes on the port
    if is_port_in_use $FRONTEND_PORT; then
        print_warning "Cleaning up orphaned processes on port $FRONTEND_PORT..."
        kill_port $FRONTEND_PORT
    fi
}

# Get service status
status() {
    print_header "Service Status"
    
    # Backend status
    echo -e "${BLUE}Backend:${NC}"
    if is_running "$BACKEND_PID_FILE"; then
        local pid=$(cat "$BACKEND_PID_FILE")
        print_success "Running (PID: $pid)"
        if check_url "$BACKEND_HEALTH_URL"; then
            print_success "Responding on http://127.0.0.1:$BACKEND_PORT"
        else
            print_warning "Process running but not responding"
        fi
    else
        print_error "Not running"
    fi
    
    echo ""
    
    # Frontend status
    echo -e "${BLUE}Frontend:${NC}"
    if is_running "$FRONTEND_PID_FILE"; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        print_success "Running (PID: $pid)"
        if check_url "$FRONTEND_HEALTH_URL"; then
            print_success "Responding on http://localhost:$FRONTEND_PORT"
        else
            print_warning "Process running but not responding"
        fi
    else
        print_error "Not running"
    fi
    
    echo ""
}

# Show logs
logs() {
    local service=$1
    local lines=${2:-50}
    
    case $service in
        backend)
            print_header "Backend Logs (last $lines lines)"
            if [ -f "$BACKEND_LOG" ]; then
                tail -n $lines "$BACKEND_LOG"
            else
                print_warning "No backend logs found"
            fi
            ;;
        frontend)
            print_header "Frontend Logs (last $lines lines)"
            if [ -f "$FRONTEND_LOG" ]; then
                tail -n $lines "$FRONTEND_LOG"
            else
                print_warning "No frontend logs found"
            fi
            ;;
        *)
            print_error "Unknown service: $service"
            echo "Usage: $0 logs [backend|frontend] [lines]"
            return 1
            ;;
    esac
}

# Follow logs
follow_logs() {
    local service=$1
    
    case $service in
        backend)
            print_header "Following Backend Logs (Ctrl+C to stop)"
            if [ -f "$BACKEND_LOG" ]; then
                tail -f "$BACKEND_LOG"
            else
                print_warning "No backend logs found"
            fi
            ;;
        frontend)
            print_header "Following Frontend Logs (Ctrl+C to stop)"
            if [ -f "$FRONTEND_LOG" ]; then
                tail -f "$FRONTEND_LOG"
            else
                print_warning "No frontend logs found"
            fi
            ;;
        *)
            print_error "Unknown service: $service"
            echo "Usage: $0 follow [backend|frontend]"
            return 1
            ;;
    esac
}

# Main command handler
case "${1:-}" in
    start)
        case "${2:-all}" in
            backend)
                start_backend
                ;;
            frontend)
                start_frontend
                ;;
            all)
                start_backend
                start_frontend
                ;;
            *)
                print_error "Unknown service: $2"
                echo "Usage: $0 start [backend|frontend|all]"
                exit 1
                ;;
        esac
        ;;
    
    stop)
        case "${2:-all}" in
            backend)
                stop_backend
                ;;
            frontend)
                stop_frontend
                ;;
            all)
                stop_frontend
                stop_backend
                ;;
            *)
                print_error "Unknown service: $2"
                echo "Usage: $0 stop [backend|frontend|all]"
                exit 1
                ;;
        esac
        ;;
    
    restart)
        case "${2:-all}" in
            backend)
                stop_backend
                sleep 1
                start_backend
                ;;
            frontend)
                stop_frontend
                sleep 1
                start_frontend
                ;;
            all)
                stop_frontend
                stop_backend
                sleep 1
                start_backend
                start_frontend
                ;;
            *)
                print_error "Unknown service: $2"
                echo "Usage: $0 restart [backend|frontend|all]"
                exit 1
                ;;
        esac
        ;;
    
    status)
        status
        ;;
    
    logs)
        logs "${2:-backend}" "${3:-50}"
        ;;
    
    follow)
        follow_logs "${2:-backend}"
        ;;
    
    *)
        echo -e "${BLUE}TeamSight Dashboard Service Manager${NC}"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs|follow} [service] [options]"
        echo ""
        echo "Commands:"
        echo "  start [backend|frontend|all]     Start services"
        echo "  stop [backend|frontend|all]      Stop services"
        echo "  restart [backend|frontend|all]   Restart services"
        echo "  status                            Show service status"
        echo "  logs [backend|frontend] [lines]  Show service logs"
        echo "  follow [backend|frontend]        Follow service logs"
        echo ""
        echo "Examples:"
        echo "  $0 start                 Start all services"
        echo "  $0 start backend         Start only backend"
        echo "  $0 stop frontend         Stop only frontend"
        echo "  $0 restart all           Restart all services"
        echo "  $0 status                Check service status"
        echo "  $0 logs backend 100      Show last 100 lines of backend logs"
        echo "  $0 follow frontend       Follow frontend logs in real-time"
        echo ""
        exit 1
        ;;
esac
