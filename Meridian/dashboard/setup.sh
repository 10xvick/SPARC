#!/bin/bash

# Employee Metrics Dashboard - Quick Setup Script
# This script sets up both frontend and backend for development

set -e

echo "=========================================="
echo "Employee Metrics Dashboard - Setup"
echo "=========================================="
echo ""

# Check prerequisites
command -v node >/dev/null 2>&1 || { echo "Error: Node.js is required but not installed. Please install Node.js 18+"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Error: Python 3 is required but not installed. Please install Python 3.11+"; exit 1; }

echo "✓ Prerequisites check passed"
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Backend Setup
echo "Setting up Backend..."
cd backend

if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Installing Python dependencies..."
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt

echo "Creating .env file from template..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "⚠️  Please edit backend/.env and update SECRET_KEY before deploying to production"
fi

cd "$SCRIPT_DIR"
echo "✓ Backend setup complete"
echo ""

# Frontend Setup
echo "Setting up Frontend..."
cd frontend

echo "Installing npm dependencies..."
npm install

cd "$SCRIPT_DIR"
echo "✓ Frontend setup complete"
echo ""

echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To start the application:"
echo ""
echo "1. Start Backend (Terminal 1):"
echo "   cd $(pwd)/backend"
echo "   ./venv/bin/python -m uvicorn app.main:app --reload"
echo ""
echo "2. Start Frontend (Terminal 2):"
echo "   cd $(pwd)/frontend"
echo "   npm run dev"
echo ""
echo "3. Open your browser:"
echo "   Frontend: http://localhost:5173"
echo "   Backend API: http://localhost:8000/docs"
echo ""
echo "=========================================="
