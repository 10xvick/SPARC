#!/bin/bash

# TeamSight Dashboard - Shell Aliases Setup
# Run: source dashboard/aliases.sh

DASHBOARD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Define aliases
alias ts-start="$DASHBOARD_DIR/manage.sh start all"
alias ts-stop="$DASHBOARD_DIR/manage.sh stop all"
alias ts-restart="$DASHBOARD_DIR/manage.sh restart all"
alias ts-status="$DASHBOARD_DIR/manage.sh status"
alias ts-logs-backend="$DASHBOARD_DIR/manage.sh logs backend"
alias ts-logs-frontend="$DASHBOARD_DIR/manage.sh logs frontend"
alias ts-follow-backend="$DASHBOARD_DIR/manage.sh follow backend"
alias ts-follow-frontend="$DASHBOARD_DIR/manage.sh follow frontend"

# Convenience aliases
alias ts-be-start="$DASHBOARD_DIR/manage.sh start backend"
alias ts-be-stop="$DASHBOARD_DIR/manage.sh stop backend"
alias ts-be-restart="$DASHBOARD_DIR/manage.sh restart backend"
alias ts-fe-start="$DASHBOARD_DIR/manage.sh start frontend"
alias ts-fe-stop="$DASHBOARD_DIR/manage.sh stop frontend"
alias ts-fe-restart="$DASHBOARD_DIR/manage.sh restart frontend"

# Print confirmation
echo "TeamSight Dashboard aliases loaded!"
echo ""
echo "Quick commands:"
echo "  ts-start          - Start all services"
echo "  ts-stop           - Stop all services"
echo "  ts-restart        - Restart all services"
echo "  ts-status         - Check service status"
echo "  ts-logs-backend   - View backend logs"
echo "  ts-logs-frontend  - View frontend logs"
echo ""
echo "Backend commands:"
echo "  ts-be-start       - Start backend only"
echo "  ts-be-stop        - Stop backend only"
echo "  ts-be-restart     - Restart backend only"
echo ""
echo "Frontend commands:"
echo "  ts-fe-start       - Start frontend only"
echo "  ts-fe-stop        - Stop frontend only"
echo "  ts-fe-restart     - Restart frontend only"
echo ""
