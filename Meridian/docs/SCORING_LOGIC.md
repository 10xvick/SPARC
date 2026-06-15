# TeamSight Scoring Logic

## Overview

TeamSight calculates a single **Overall Score (0–100)** for each individual, scrum, and team by combining role-weighted KPI statuses across four KPI categories. The scoring is fully configurable through `config/scoring_config.json` and exposed via `GET/PUT /api/score-config`.

---

## KPI Categories and Weightages

Every KPI belongs to one of four goal-type categories. Each category carries a configurable weightage that determines its share of the final 100-point score.

| Category | Default Weightage |
|---|---|
| Input | 10% |
| Output | 50% |
| Quality | 30% |
| Hygiene | 10% |
| **Total** | **100%** |

> The four weightages must always sum to exactly 100. This is enforced at both the API and service validation layers.

---

## KPI Status and Status Credits

Each KPI is evaluated against its target and assigned a Red / Orange / Green status. A configurable **status credit** translates that status into a numeric value used in the scoring formula.

| Status | Default Credit |
|---|---|
| Green | 1.0 |
| Orange | 0.75 |
| Red | 0.0 |

Status credits must be in the range `[0, 1]`.

### ROG Thresholds (individual KPI status determination)

A KPI's performance percentage is compared against two thresholds to determine its status:

| Status | Condition |
|---|---|
| Green | performance% ≥ `green_threshold` (default 100%) |
| Orange | `orange_threshold` ≤ performance% < `green_threshold` (default 70%) |
| Red | performance% < `orange_threshold` |

---

## Role Weights

KPIs have different relevance depending on how they apply to an employee or aggregate. Role weights act as importance multipliers in the scoring formula.

### Individual Dashboard — `role_type`

Each KPI on an individual's dashboard is tagged with a `role_type` reflecting why it is applicable to that person:

| `role_type` | Meaning | Default Weight |
|---|---|---|
| `Primary` | KPI is defined for the employee's primary role | 20 |
| `Secondary` | KPI is defined for the employee's secondary role | 10 |
| `All` | KPI applies to every employee regardless of role | 5 |
| `Common` | KPI applies to the "Common" role group | 3 |
| `Other` | KPI applies via a metric/other mechanism | 1 |

The lookup order when assigning `role_type` is: **Primary Role → Secondary Role → All → Common → Other**.

### Team / Scrum Dashboard — `role_specificity`

When aggregating across members, KPIs are classified into two buckets:

| `role_specificity` | Condition | Default Weight |
|---|---|---|
| `specific` | KPI role is tied to a particular role (not All / Common / Other) | 20 |
| `non_specific` | KPI role is `All`, `Common`, or `Other` | 5 |

All role weights are configurable in the range **0–20**.

---

## Scoring Formula

### Individual Score

For each of the four categories, the category score is calculated as:

$$\text{category\_score} = \frac{\sum_{i}(w_i \times c_i)}{\sum_{i} w_i} \times \text{weightage}$$

Where:
- $w_i$ = role weight of the $i$-th KPI (`role_weights[role_type]`)
- $c_i$ = status credit of the $i$-th KPI (`status_weights[Status]`)
- $\text{weightage}$ = category weightage (e.g., 0.50 for Output)

The **overall score** is the sum of all four category scores:

$$\text{overall\_score} = \sum_{\text{category}} \text{category\_score} \quad (\max = 100)$$

#### Worked Example

An employee has 3 Output KPIs:

| KPI | role_type | Status | role_weight ($w$) | status_credit ($c$) | $w \times c$ |
|---|---|---|---|---|---|
| K1 | Primary | Green | 20 | 1.00 | 20.0 |
| K2 | Secondary | Orange | 10 | 0.75 | 7.5 |
| K3 | All | Red | 5 | 0.00 | 0.0 |

$$\text{Output category score} = \frac{20.0 + 7.5 + 0.0}{20 + 10 + 5} \times 50 = \frac{27.5}{35} \times 50 \approx 39.3$$

### Team / Scrum Score

Identical formula, but $w_i$ is taken from `aggregation_role_weights` keyed by `role_specificity` (`specific` or `non_specific`) instead of `role_weights` keyed by `role_type`.

$$\text{category\_score} = \frac{\sum_{i}(w_i^{\text{agg}} \times c_i)}{\sum_{i} w_i^{\text{agg}}} \times \text{weightage}$$

---

## Score Display Thresholds

The computed overall score (0–100) is mapped to a display colour for gauge indicators:

| Colour | Condition |
|---|---|
| Green | score ≥ `green_min` (default 70) |
| Orange | `orange_min` ≤ score < `green_min` (default 36–69) |
| Red | score ≤ `red_max` (default ≤ 35) |

The ordering constraint `0 ≤ red_max < orange_min < green_min ≤ 100` is enforced on save.

---

## Configuration Reference

All parameters live in `config/scoring_config.json` (current version: 2.2).

```json
{
  "weightages":                { "Input": 10, "Output": 50, "Quality": 30, "Hygiene": 10 },
  "status_weights":            { "Green": 1.0, "Orange": 0.75, "Red": 0.0 },
  "role_weights":              { "Primary": 20, "Secondary": 10, "All": 5, "Common": 3, "Other": 1 },
  "aggregation_role_weights":  { "specific": 20, "non_specific": 5 },
  "rog_thresholds":            { "green_threshold": 100, "orange_threshold": 70 },
  "score_display_thresholds":  { "green_min": 70, "orange_min": 36, "red_max": 35 }
}
```

### Validation Rules

| Parameter | Rule |
|---|---|
| `weightages` | All four keys required; values must sum to 100 |
| `status_weights` | All three keys required; each value in `[0, 1]` |
| `role_weights` | All five keys required; each value in `[0, 20]` |
| `aggregation_role_weights` | Both keys required; each value in `[0, 20]` |
| `rog_thresholds` | `0 ≤ orange_threshold ≤ green_threshold ≤ 200` |
| `score_display_thresholds` | `0 ≤ red_max < orange_min < green_min ≤ 100` |

---

## API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/score-config` | Read current configuration |
| `PUT` | `/api/score-config` | Update one or more configuration blocks |

All fields in the `PUT` request body are optional — only the blocks provided are updated; others retain their current values.

---

## Key Design Decisions

1. **Role weights encode importance, not inclusion.** Only KPIs applicable to a member are included; role weights then determine how much each applicable KPI contributes relative to others.

2. **Individual vs. aggregate weighting are independent.** Individual dashboards use five-level `role_type` weights (Primary → Other). Team/scrum dashboards collapse this to two levels (`specific` / `non_specific`) because individual role detail is not meaningful at the aggregate level.

3. **`non_specific` covers All, Common, and Other.** KPIs that apply broadly (role = `All`, `Common`, or `Other`) receive the lower `non_specific` weight during team/scrum aggregation to prevent universally-applicable KPIs from dominating the score over role-specific ones.

4. **Categories with no KPIs contribute 0.** A member with no Output KPIs gets 0 for Output, not a proportionally redistributed score.

5. **Orange gives partial credit.** Orange status earns 75% of the maximum credit for a KPI, incentivising teams to push marginal performers from Orange to Green rather than treating it as equivalent to Red.
