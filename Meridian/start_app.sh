#!/bin/bash

# Meridian - Complete Application Startup
# This script starts the entire application stack:
# - Regenerates RBAC data from Resources.csv
# - Starts backend server
# - Starts frontend server
# - Opens browser with CORS disabled
# - Displays admin credentials

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Meridian Application Startup"
echo "=========================================="
echo ""

BACKEND_PID_FILE="/tmp/meridian_backend.pid"
FRONTEND_PID_FILE="/tmp/meridian_frontend.pid"

# Step 1: Stop any existing processes for THIS codebase only
echo "1. Stopping existing Meridian processes..."

# Kill by saved PIDs if available
if [ -f "$BACKEND_PID_FILE" ]; then
    OLD_PID=$(cat "$BACKEND_PID_FILE")
    kill "$OLD_PID" 2>/dev/null || true
    rm -f "$BACKEND_PID_FILE"
fi
if [ -f "$FRONTEND_PID_FILE" ]; then
    OLD_PID=$(cat "$FRONTEND_PID_FILE")
    kill "$OLD_PID" 2>/dev/null || true
    rm -f "$FRONTEND_PID_FILE"
fi

# Fallback: also match by path in case PID files are missing
pkill -f "$SCRIPT_DIR/dashboard/backend/venv/bin/python" 2>/dev/null || true
pkill -f "$SCRIPT_DIR/dashboard/frontend/node_modules/.bin/vite" 2>/dev/null || true

sleep 2
echo "✓ Existing Meridian processes stopped"
echo ""

# Step 2: Regenerate RBAC data
echo "2. Regenerating RBAC data from Resources.csv..."
RBAC_OUTPUT=$(dashboard/backend/venv/bin/python dashboard/backend/init_rbac_data.py --force 2>&1)
ADMIN_PASSWORD=$(echo "$RBAC_OUTPUT" | grep "Admin default password:" | awk '{print $NF}')

if [ -z "$ADMIN_PASSWORD" ]; then
    echo "✗ Failed to extract admin password"
    echo "$RBAC_OUTPUT"
    exit 1
fi

USER_COUNT=$(echo "$RBAC_OUTPUT" | grep "Created data/users.json with" | grep -o '[0-9]\+ users' | awk '{print $1}')
echo "✓ RBAC data regenerated ($USER_COUNT users)"
echo ""

# Step 3: Start backend
echo "3. Starting backend server..."
cd dashboard/backend
./venv/bin/python -m uvicorn app.main:app --reload > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$BACKEND_PID_FILE"
cd ../..
echo "✓ Backend starting (PID: $BACKEND_PID)"
echo ""

# Step 4: Wait for backend to be ready
echo "4. Waiting for backend to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ Backend is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "✗ Backend failed to start. Check logs:"
        echo "   tail -f /tmp/backend.log"
        exit 1
    fi
    sleep 1
done
echo ""

# Step 5: Sync users from Resources.csv
echo "5. Syncing users from Resources.csv..."
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"sapid\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "⚠ Warning: Failed to get auth token for user sync"
    echo "  You may need to manually sync users from the dashboard"
else
    SYNC_RESULT=$(curl -s -X POST http://localhost:8000/api/admin/users/sync \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json")
    
    CREATED=$(echo "$SYNC_RESULT" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('created', 0))" 2>/dev/null || echo "0")
    UPDATED=$(echo "$SYNC_RESULT" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('updated', 0))" 2>/dev/null || echo "0")
    echo "✓ Users synced: $CREATED created, $UPDATED updated"
fi
echo ""

# Step 6: Start frontend
echo "6. Starting frontend server..."
cd dashboard/frontend
npm run dev > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > "$FRONTEND_PID_FILE"
cd ../..
echo "✓ Frontend starting (PID: $FRONTEND_PID)"
echo ""

# Step 7: Wait for frontend to be ready - read actual port from Vite log
echo "7. Waiting for frontend to be ready..."
FRONTEND_PORT=""
for i in $(seq 1 30); do
    FRONTEND_PORT=$(grep -o "localhost:[0-9]*" /tmp/frontend.log 2>/dev/null | head -1 | cut -d: -f2)
    if [ -n "$FRONTEND_PORT" ]; then
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "✗ Frontend failed to start. Check logs:"
        echo "   tail -f /tmp/frontend.log"
        exit 1
    fi
    sleep 1
done
echo "✓ Frontend is ready on port $FRONTEND_PORT!"
echo ""

# Step 8: Open browser with CORS disabled
echo "8. Opening browser..."
sleep 2
open -na "Google Chrome" --args --user-data-dir=/tmp/chrome_dev --disable-web-security --disable-site-isolation-trials "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1 &
echo "✓ Browser opened"
echo ""

# Display summary
echo "=========================================="
echo "✅ Application Started Successfully!"
echo "=========================================="
echo ""
echo "📱 Access Points:"
echo "  Frontend:  http://localhost:$FRONTEND_PORT"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "🔐 Admin Credentials:"
echo "  SAPID:     admin"
echo "  Password:  $ADMIN_PASSWORD"
echo ""
echo "📊 System Info:"
echo "  Users:     $USER_COUNT"
echo "  Backend:   PID $BACKEND_PID"
echo "  Frontend:  PID $FRONTEND_PID"
echo ""
echo "📝 Logs:"
echo "  Backend:   tail -f /tmp/backend.log"
echo "  Frontend:  tail -f /tmp/frontend.log"
echo ""
echo "🛑 To stop Meridian services:"
echo "  pkill -f '$SCRIPT_DIR/dashboard/backend/venv/bin/python.*uvicorn'"
echo "  pkill -f '$SCRIPT_DIR/dashboard/frontend'"
echo ""
echo "Press Ctrl+C to stop monitoring (services will continue running)"
echo ""

# Keep script running and show logs
echo "=========================================="
echo "📊 Live Backend Logs (Ctrl+C to exit)"
echo "=========================================="
tail -f /tmp/backend.log
