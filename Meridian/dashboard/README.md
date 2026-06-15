# TeamSight Dashboard

A modern employee metrics dashboard for tracking KPIs, managing resources, and visualizing team performance.

## Quick Start

### Starting the Application

```bash
# Navigate to dashboard directory
cd /path/to/TeamSight/dashboard

# Start all services
./manage.sh start

# Check status
./manage.sh status
```

Local development URLs:
- **Frontend (Vite)**: http://localhost:5173
- **Backend API**: http://127.0.0.1:8000
- **API Docs**: http://127.0.0.1:8000/docs

### Remote Ubuntu Access (recommended)

If port `5173` is not reachable remotely, build the frontend and serve UI from backend port `8000`:

```bash
# From TeamSight project root (example deployment path)
cd /opt/teamsight/teamsight/dashboard/frontend
npm run build

cd /opt/teamsight/teamsight
./dashboard/manage.sh restart backend

# Optional: stop Vite if not needed
./dashboard/manage.sh stop frontend
```

Open:
- **UI**: http://<server-ip>:8000
- **API Docs**: http://<server-ip>:8000/docs

### Stopping the Application

```bash
./manage.sh stop
```

## Service Management

Use the `manage.sh` script for all service operations:

```bash
# Start services
./manage.sh start [all|backend|frontend]

# Stop services
./manage.sh stop [all|backend|frontend]

# Restart services
./manage.sh restart [all|backend|frontend]

# Check status
./manage.sh status

# View logs
./manage.sh logs [backend|frontend] [number_of_lines]

# Follow logs in real-time
./manage.sh follow [backend|frontend]
```

For detailed documentation, see [SERVICE_MANAGEMENT.md](SERVICE_MANAGEMENT.md)

### Frontend Build

```bash
cd frontend
npm install
npm run build
```

Build output is generated under `frontend/dist`.

## Features

- ✅ Employee KPI tracking with ROG status (Red/Orange/Green)
- ✅ Team and Scrum aggregation views
- ✅ Goal Type grouping (Input/Output/Quality/Hygiene)
- ✅ Drill-down from team → individual employee
- ✅ Role-based KPI assignment
- ✅ Employee Management (CSV import/export)
- ✅ Role Management (Target editing, CSV import)
- ✅ Employee KPI Reports with color-coded cells
- ✅ PDF/Excel export

## Technology Stack

| Component | Technology | License |
|-----------|-----------|---------|
| Frontend Framework | React 18 | MIT |
| Language | TypeScript | Apache 2.0 |
| Build Tool | Vite | MIT |
| UI Library | Material-UI v5 | MIT |
| Charts | Apache ECharts | Apache 2.0 |
| Backend Framework | FastAPI | MIT |
| Backend Language | Python 3.11 | PSF |
| Data Processing | Pandas | BSD |
| Authentication | JWT | MIT |

## Development Phases

1. ✅ **Phase 1**: Development environment setup (Current)
2. **Phase 2**: Core API development
3. **Phase 3**: Frontend basic views
4. **Phase 4**: Advanced features (charts, drill-down)
5. **Phase 5**: Configuration pages (Employee/Role Management)
6. **Phase 6**: Reports and export
7. **Phase 7**: Polish, testing, deployment

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License

Internal use - HCL Software

## Support

For questions, contact the dashboard development team.
