# Equivalent KPI Mechanism

## Overview

The TeamSight system supports **Equivalent KPIs** - KPIs that share the same computation logic and data with a base KPI, but can have independent roles and targets.

## Use Case

When you need to track the same metric for different roles or with different targets, you can create an equivalent KPI instead of duplicating the entire computation logic.

### Example: K8 (Equivalent to K4)

- **K4**: Review Comments for Developers
- **K8**: Review Comments for Architects (same metric, different role/targets)

Both use the same computation (counting GitHub review comments), but:
- K4 targets Developers with Annual Target = 500
- K8 targets Architects with Annual Target = 300 (hypothetical)

## How It Works

### 1. Computation & Data Sharing

Equivalent KPIs reuse the base KPI's:
- **Computation logic**: No need to duplicate code
- **Data file**: K8 reads from `k4-data.csv`
- **Function execution**: Running K8 executes K4's function

### 2. Independent Configuration

Equivalent KPIs maintain their own:
- **Role**: Can target different roles (Developer vs Architect)
- **Targets**: Independent Weekly/Monthly/Quarterly/Annual targets
- **KPI Name**: Separate entry in Roles.csv

## Implementation Guide

### Step 1: Define the Equivalence Mapping

Edit `src/KppEvaluator.py` and add to the `kpi_equivalents` dictionary:

```python
self.kpi_equivalents = {
    'k8': 'k4',    # K8 uses K4's computation and data
    'k15': 'k14',  # K15 uses K14's computation and data
    # Add more as needed
}
```

### Step 2: Register the KPI Function

In the `kpi_functions` registry, point the equivalent KPI to the base function:

```python
self.kpi_functions = {
    # ... existing KPIs ...
    'k4': k4,
    # ... 
    # Equivalent KPIs (use base KPI's function)
    'k8': k4,  # K8 uses K4's computation
    'k15': k14,  # K15 uses K14's computation
}
```

### Step 3: Add Entry to Roles.csv

Create a new row in `config/Roles.csv` with:
- **Index**: k8 (or your new KPI number)
- **Role**: Target role (can be different from base KPI)
- **Targets**: Your specific Weekly/Monthly/Quarterly/Annual targets
- **All other columns**: Configure as needed

Example:
```csv
Index,Role,KPP Goals,Measurement Criteria,Tool,Measure,Type,Aggregation Type,Weekly Target,Quarterly Target,Annual Target,Goal Type
k8,Architect,Code Review Quality: Provide thorough code reviews,Code Quality: Review comments provided,GIT,Review comments provided >,NG,ANG,20,100,300,Quality
```

**Note**: K8 can have the same or different measurement criteria, but typically keeps similar description to K4 while targeting a different role.

## Usage

### Running Equivalent KPIs

Run K8 just like any other KPI:

```bash
# Run K8 (will execute K4's computation)
python src/KppEvaluator.py --kpi k8

# List all KPIs (includes equivalents)
python src/KppEvaluator.py --list

# Generate matrix report (includes K8 with K4's data)
python src/KppEvaluator.py --matrix --period Annual
```

When you run K8:
```
Note: K8 is equivalent to K4 (shares computation and data)
Running K4 computation...
✓ K8: Success
```

### Dashboard Integration

Equivalent KPIs appear in dashboards like any other KPI:
- **Employee Dashboard**: Shows K8 if the employee's role matches "Architect"
- **Team/Scrum Dashboards**: Aggregates K8 separately from K4
- **Matrix Report**: K8 appears as a separate column with K4's values

### API Behavior

The backend APIs handle equivalent KPIs transparently:
- `GET /api/reports/available-kpis`: Returns both k4 and k8
- `GET /api/reports/matrix`: Includes both columns
- `GET /api/employee-dashboard/{name}`: Shows K8 if role matches

Role filtering applies independently:
- K4 shows for Developers (if configured)
- K8 shows for Architects (if configured)
- Targets are evaluated separately

## Technical Details

### Data File Resolution

When reading KPI data, the system resolves equivalents:

```python
def read_kpi_data(self, kpi_name, period='Annual'):
    base_kpi = self.get_base_kpi(kpi_name)  # k8 -> k4
    kpi_file = f'{base_kpi}-data.csv'       # Uses k4-data.csv
    # ...
```

### Role & Target Lookup

Role and target lookups **always use the requested KPI name** (not the base):

```python
# In team_dashboard.py, scrum_dashboard.py, etc.
kpi_info = roles_df[roles_df['Index'] == 'k8']  # Uses k8, not k4
target = kpi_row.get('Annual Target', 0)        # K8's target, not K4's
```

This ensures:
- K8 can target different roles than K4
- K8 can have different targets than K4
- Both appear independently in reports

## Benefits

1. **Code Reuse**: No need to duplicate computation logic
2. **Data Efficiency**: Single data file serves multiple KPIs
3. **Flexibility**: Independent roles and targets per KPI
4. **Maintainability**: Fix bugs once in base KPI
5. **Performance**: No redundant calculations

## Examples of Potential Equivalent KPIs

- **K8 = K4**: Review comments for different roles
- **K10 = K9**: Bug resolution time for different bug priorities
- **K15 = K14**: Code churn for different project types
- **K100 = K3**: Issue count for different issue types

## Adding More Equivalent KPIs

To add a new equivalent KPI:

1. Identify the base KPI to reuse
2. Add to `kpi_equivalents` dict: `'kX': 'kY'`
3. Add to `kpi_functions` registry: `'kX': kY`
4. Create entry in Roles.csv with Index=kX
5. Set independent Role and Targets
6. Test: `python src/KppEvaluator.py --kpi kX`

That's it! No need to create `kpp_kX.py` or duplicate any code.

## Limitations

1. **Must share same data structure**: Base KPI's CSV output format
2. **Must share same data sources**: JIRA, GitHub, or Resources
3. **Cannot modify computation**: If you need different logic, create a new KPI module
4. **Cannot override measure**: Uses base KPI's measure exactly

## Troubleshooting

### K8 shows no data

Check:
1. K4's data file exists: `output/k4-data.csv`
2. K4 has been run: `python src/KppEvaluator.py --kpi k4`
3. K8 is registered in `kpi_equivalents` and `kpi_functions`

### K8 not appearing in dashboard

Check:
1. K8 entry exists in `config/Roles.csv`
2. K8's Role matches the employee's Primary or Secondary Role
3. K8's Goal Type is filled (not empty)
4. Backend has been restarted after Roles.csv changes

### K8 using wrong targets

Verify:
1. `config/Roles.csv` has separate row for k8
2. Row Index is exactly `k8` (lowercase)
3. Weekly/Monthly/Quarterly/Annual Target columns have values
4. Backend reads from latest Roles.csv (restart if needed)
