# Performance Scoring System Implementation

## Overview
Implemented a comprehensive performance scoring system for individual employees, teams, and scrums based on KPI performance across four categories: Input, Output, Quality, and Hygiene.

## Features Implemented

### 1. Scoring Configuration
**File:** `/config/scoring_config.json`
- Configurable weightages for each KPI category
- Default weightages:
  - Input: 10%
  - Output: 50%
  - Quality: 30%
  - Hygiene: 10%
- Total must equal 100%

### 2. Backend Implementation

#### Scoring Service
**File:** `dashboard/backend/app/services/scoring_service.py`
- `ScoringService` class with methods:
  - `calculate_score()`: Calculate individual/team/scrum scores
  - `calculate_aggregate_score()`: Aggregate scores for groups
  - `get_config()`: Get current weightages
  - `save_config()`: Update weightages
- Singleton pattern for efficient reuse

#### API Endpoints
**File:** `dashboard/backend/app/api/scoring.py`
- `GET /api/score-config`: Get current scoring configuration
- `PUT /api/score-config`: Update scoring weightages
  - Validates that weightages sum to 100%
  - Validates all required categories are present

#### Dashboard Enhancements
**Files:**
- `dashboard/backend/app/api/employee_dashboard.py`
- `dashboard/backend/app/api/team_dashboard.py`
- `dashboard/backend/app/api/scrum_dashboard.py`

Each dashboard now includes:
- `goal_type_category` field mapping to Input/Output/Quality/Hygiene
- `Status` field (Green/Orange/Red) for scoring calculation
- `score` object in response with:
  - `overall_score`: Total score (max 100)
  - `max_score`: Maximum possible score (100)
  - `categories`: Breakdown by category with:
    - `total_kpis`: Number of applicable KPIs
    - `green_kpis`: Number of green KPIs
    - `green_percentage`: Percentage of green KPIs
    - `weightage`: Category weightage
    - `score`: Category contribution to overall score
  - `weightages`: Current weightage configuration

### 3. Frontend Implementation

#### ScoreCard Component
**File:** `dashboard/frontend/src/components/ScoreCard.tsx`
- Reusable component for displaying performance scores
- Features:
  - Overall score with color-coded progress bar
  - Category breakdown with individual progress bars
  - Visual indicators for each category (color-coded borders)
  - Score legend (Green ≥80, Orange 60-79, Red <60)
  - Formula explanation
- Color scheme:
  - Input: Blue (#2196f3)
  - Output: Green (#4caf50)
  - Quality: Orange (#ff9800)
  - Hygiene: Purple (#9c27b0)

#### Scoring Configuration Panel
**File:** `dashboard/frontend/src/components/ScoringConfigPanel.tsx`
- Admin interface for managing scoring weightages
- Features:
  - Slider controls for each category (0-100%)
  - Numeric input fields
  - Real-time validation (total must equal 100%)
  - Save, Reset, and Reload buttons
  - Visual feedback for valid/invalid configurations
  - Formula and usage information

#### Dashboard Updates
**Files:**
- `dashboard/frontend/src/pages/EmployeeDashboardPage.tsx`
- `dashboard/frontend/src/pages/TeamDashboardPage.tsx`
- `dashboard/frontend/src/pages/ScrumDashboardPage.tsx`
- `dashboard/frontend/src/pages/AdminPage.tsx`

Each dashboard now displays:
- ScoreCard component showing performance score
- Category-wise breakdown
- Real-time updates when weightages change

## Scoring Formula

```
For each category:
  Category Score = (Green KPIs / Total KPIs) × Category Weightage

Overall Score = Σ(Category Scores)
Maximum Score = 100
```

### Example Calculation
If an employee has:
- Output: 5/7 green KPIs (71.43% green)
- Quality: 1/1 green KPIs (100% green)
- Hygiene: 1/2 green KPIs (50% green)
- Input: 0/0 green KPIs (0% contribution)

With default weightages (10%, 50%, 30%, 10%):
```
Output Score  = (71.43% × 50) = 35.71
Quality Score = (100% × 30)   = 30.00
Hygiene Score = (50% × 10)    = 5.00
Input Score   = (0% × 10)     = 0.00
─────────────────────────────────────
Overall Score = 70.71 / 100
```

## Key Features

### Configurable Weightages
- Administrators can adjust category weightages in real-time
- Changes immediately apply to all dashboards
- Validation ensures weightages sum to 100%

### Multi-Level Scoring
- **Individual**: Employee-level KPI performance
- **Team**: Aggregated performance across all team members
- **Scrum**: Aggregated performance across all scrum members

### Category-Based Analysis
- Four KPI categories: Input, Output, Quality, Hygiene
- Each category shows:
  - Number of green KPIs
  - Total applicable KPIs
  - Green percentage
  - Contribution to overall score

### Visual Representation
- Color-coded progress bars
- Category-specific colors for easy identification
- Score thresholds:
  - Green (≥80): Excellent performance
  - Orange (60-79): Good performance
  - Red (<60): Needs improvement

## API Testing

### Get Current Configuration
```bash
curl -s "http://127.0.0.1:8000/api/score-config" | python3 -m json.tool
```

### Update Configuration
```bash
curl -s -X PUT "http://127.0.0.1:8000/api/score-config" \
  -H "Content-Type: application/json" \
  -d '{"Input": 15, "Output": 45, "Quality": 25, "Hygiene": 15}' \
  | python3 -m json.tool
```

### Get Employee Score
```bash
curl -s "http://127.0.0.1:8000/api/employee-dashboard/[Name]?period=Annual" \
  | python3 -m json.tool
```

## Files Modified/Created

### Created Files
1. `/config/scoring_config.json` - Configuration file
2. `dashboard/backend/app/services/scoring_service.py` - Scoring service
3. `dashboard/backend/app/api/scoring.py` - API endpoints
4. `dashboard/frontend/src/components/ScoreCard.tsx` - Score display component
5. `dashboard/frontend/src/components/ScoringConfigPanel.tsx` - Admin configuration panel

### Modified Files
1. `dashboard/backend/app/main.py` - Registered scoring router
2. `dashboard/backend/app/api/employee_dashboard.py` - Added score calculation
3. `dashboard/backend/app/api/team_dashboard.py` - Added score calculation
4. `dashboard/backend/app/api/scrum_dashboard.py` - Added score calculation
5. `dashboard/frontend/src/pages/EmployeeDashboardPage.tsx` - Added ScoreCard
6. `dashboard/frontend/src/pages/TeamDashboardPage.tsx` - Added ScoreCard
7. `dashboard/frontend/src/pages/ScrumDashboardPage.tsx` - Added ScoreCard
8. `dashboard/frontend/src/pages/AdminPage.tsx` - Added ScoringConfigPanel

## Usage Instructions

### For End Users
1. Navigate to Employee/Team/Scrum Dashboard
2. View the "Performance Score" card showing:
   - Overall score out of 100
   - Category-wise breakdown
   - Green KPI percentages

### For Administrators
1. Navigate to Admin Page
2. Scroll to "Performance Scoring Configuration" section
3. Adjust weightages using sliders or numeric inputs
4. Ensure total equals 100%
5. Click "Save Configuration"
6. Changes apply immediately across all dashboards

## Benefits

1. **Objective Performance Measurement**: Quantified score based on KPI achievement
2. **Configurable**: Administrators can adjust category importance
3. **Multi-Level**: Individual, team, and scrum-level scoring
4. **Transparent**: Clear formula and calculation shown to users
5. **Real-Time**: Immediate updates when weightages change
6. **Visual**: Color-coded displays for easy interpretation
7. **Category Analysis**: Understand which areas need improvement

## Future Enhancements (Optional)

1. Historical score tracking over time
2. Score trends and predictions
3. Comparative analysis (peer comparison)
4. Customizable score thresholds
5. Role-specific weightages
6. Export score reports
7. Score-based notifications/alerts
8. Integration with performance reviews

---

**Implementation Date:** March 12, 2026
**Status:** ✅ Completed and Tested
