import { useEffect, useMemo, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  Stack,
  Typography,
} from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import CalculateOutlinedIcon from '@mui/icons-material/CalculateOutlined'

const validationRules = [
  'Category weightages must sum to 100.',
  'Status weights must stay within the range 0 to 1.',
  'Role weights and aggregation role weights must stay within the range 0 to 20.',
  'ROG thresholds must satisfy orange_threshold ≤ green_threshold.',
  'Display thresholds must satisfy red_max < orange_min < green_min.',
]

interface Weightages {
  Input: number
  Output: number
  Quality: number
  Hygiene: number
}

interface StatusWeights {
  Green: number
  Orange: number
  Red: number
}

interface RoleWeights {
  Primary: number
  Secondary: number
  All: number
  Common: number
  Other: number
}

interface AggregationRoleWeights {
  specific: number
  non_specific: number
}

interface ROGThresholds {
  green_threshold: number
  orange_threshold: number
}

interface ScoreDisplayThresholds {
  green_min: number
  orange_min: number
  red_max: number
}

interface ScoringConfig {
  weightages: Weightages
  status_weights: StatusWeights
  role_weights: RoleWeights
  aggregation_role_weights: AggregationRoleWeights
  rog_thresholds: ROGThresholds
  score_display_thresholds: ScoreDisplayThresholds
}

const defaultConfig: ScoringConfig = {
  weightages: {
    Input: 10,
    Output: 50,
    Quality: 30,
    Hygiene: 10,
  },
  status_weights: {
    Green: 1.0,
    Orange: 0.75,
    Red: 0.0,
  },
  role_weights: {
    Primary: 20,
    Secondary: 10,
    All: 5,
    Common: 3,
    Other: 1,
  },
  aggregation_role_weights: {
    specific: 20,
    non_specific: 5,
  },
  rog_thresholds: {
    green_threshold: 100,
    orange_threshold: 70,
  },
  score_display_thresholds: {
    green_min: 70,
    orange_min: 36,
    red_max: 35,
  },
}

function formatValue(value: number): string {
  if (Number.isInteger(value)) {
    return value.toString()
  }

  return value.toFixed(2).replace(/\.0+$|(?<=\.[0-9]*[1-9])0+$/, '')
}

function formatLabel(label: string): string {
  return label.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

export default function ScoringLogicPage() {
  const [config, setConfig] = useState<ScoringConfig>(defaultConfig)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const loadConfig = async () => {
      setLoading(true)
      setError(null)

      try {
        const response = await fetch('/api/score-config')

        if (!response.ok) {
          throw new Error(`Failed to load scoring configuration (${response.status})`)
        }

        const data = (await response.json()) as Partial<ScoringConfig>

        setConfig({
          weightages: { ...defaultConfig.weightages, ...(data.weightages ?? {}) },
          status_weights: { ...defaultConfig.status_weights, ...(data.status_weights ?? {}) },
          role_weights: { ...defaultConfig.role_weights, ...(data.role_weights ?? {}) },
          aggregation_role_weights: {
            ...defaultConfig.aggregation_role_weights,
            ...(data.aggregation_role_weights ?? {}),
          },
          rog_thresholds: { ...defaultConfig.rog_thresholds, ...(data.rog_thresholds ?? {}) },
          score_display_thresholds: {
            ...defaultConfig.score_display_thresholds,
            ...(data.score_display_thresholds ?? {}),
          },
        })
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to load scoring configuration'
        setError(`${message}. Showing the current default display values.`)
      } finally {
        setLoading(false)
      }
    }

    loadConfig()
  }, [])

  const totalWeightage = useMemo(
    () => Object.values(config.weightages).reduce((sum, value) => sum + value, 0),
    [config.weightages]
  )

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="50vh">
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <CalculateOutlinedIcon color="primary" />
        <Typography variant="h4" fontWeight="bold">
          Scoring Logic
        </Typography>
      </Stack>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 4, maxWidth: 960 }}>
        TeamSight calculates an overall score out of 100 for employees, scrums, and teams by combining KPI status,
        category weightage, and role-based importance. This page reflects the live scoring configuration currently
        loaded into the application, including prorated-target logic for quarterly and annual KPIs and
        partial-period handling using employee Start Date.
      </Typography>

      <Alert severity="info" sx={{ mb: 3 }}>
        Proration update: Employee dashboards now compute quarterly and annual prorated targets from the later of
        period start and employee Start Date for mid-period joiners.
      </Alert>

      {error && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <Stack spacing={3}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Category Weightages
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  Every KPI contributes through one of four categories. These category weightages must always total 100.
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {Object.entries(config.weightages).map(([label, value]) => (
                    <Chip
                      key={label}
                      label={`${label}: ${formatValue(value)}%`}
                      color="primary"
                      variant="outlined"
                    />
                  ))}
                </Stack>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                  Current total weightage: {formatValue(totalWeightage)}%
                </Typography>
              </CardContent>
            </Card>

            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Status Credits
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  KPI status translates into numeric credit before score aggregation.
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
                  <Chip label={`Green = ${formatValue(config.status_weights.Green)}`} color="success" variant="outlined" />
                  <Chip label={`Orange = ${formatValue(config.status_weights.Orange)}`} color="warning" variant="outlined" />
                  <Chip label={`Red = ${formatValue(config.status_weights.Red)}`} color="error" variant="outlined" />
                </Stack>
                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
                  ROG Thresholds
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Green applies when performance reaches {formatValue(config.rog_thresholds.green_threshold)}% or more
                  of target. Orange applies from {formatValue(config.rog_thresholds.orange_threshold)}% up to below{' '}
                  {formatValue(config.rog_thresholds.green_threshold)}%. Red applies below{' '}
                  {formatValue(config.rog_thresholds.orange_threshold)}%.
                </Typography>
              </CardContent>
            </Card>

            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Formula Summary
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  For each category, TeamSight computes a weighted average of KPI status credits and then scales that
                  result by the category weightage.
                </Typography>
                <Box
                  sx={{
                    p: 2,
                    borderRadius: 1,
                    bgcolor: 'grey.100',
                    fontFamily: 'monospace',
                    fontSize: '0.9rem',
                    overflowX: 'auto',
                  }}
                >
                  category_score = sum(role_weight × status_credit) / sum(role_weight) × category_weightage
                  <br />
                  overall_score = sum of all category scores
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                  Individual scores use `role_type` weights, while team and scrum scores use `role_specificity`
                  weights from the current configuration.
                </Typography>
              </CardContent>
            </Card>

            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Target Proration Rules
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  ROG status compares actual values against a prorated target when prorating is enabled for the KPI.
                  Not all targets are prorated: weekly and monthly targets are kept as configured, and KPIs with
                  prorating disabled (for example logical gating, percentage, or score-style measures) also use
                  unprorated targets to preserve their intended behavior.
                </Typography>
                <Stack spacing={1} sx={{ mb: 2 }}>
                  <Typography variant="body2" color="text.secondary">
                    • Quarterly: target × (elapsed_weeks / 13)
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    • Annual: target × (elapsed_weeks / 52)
                  </Typography>
                </Stack>
                <Divider sx={{ my: 2 }} />
                <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
                  Partial-Period Logic for New Joiners
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  For employee dashboards, proration starts from the later of fiscal/quarter start and the employee Start
                  Date. This ensures fair targets for employees who join after the period has already begun.
                </Typography>
              </CardContent>
            </Card>

            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Score Display Thresholds
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  Overall and category score gauges use the following threshold bands.
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Chip
                    label={`Green ≥ ${formatValue(config.score_display_thresholds.green_min)}`}
                    color="success"
                    variant="outlined"
                  />
                  <Chip
                    label={`Orange ≥ ${formatValue(config.score_display_thresholds.orange_min)} and < ${formatValue(config.score_display_thresholds.green_min)}`}
                    color="warning"
                    variant="outlined"
                  />
                  <Chip
                    label={`Red ≤ ${formatValue(config.score_display_thresholds.red_max)}`}
                    color="error"
                    variant="outlined"
                  />
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        </Grid>

        <Grid item xs={12} md={5}>
          <Stack spacing={3}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Individual Role Weights
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  Individual dashboards assign KPI importance based on how the KPI applies to the employee.
                </Typography>
                <Stack spacing={1}>
                  {Object.entries(config.role_weights).map(([role, weight]) => (
                    <Typography key={role} variant="body2">
                      • {role}: {formatValue(weight)}
                    </Typography>
                  ))}
                </Stack>
              </CardContent>
            </Card>

            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Team / Scrum Role Weights
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  Aggregate dashboards simplify KPI applicability into specific and non-specific buckets.
                </Typography>
                <Stack spacing={1}>
                  {Object.entries(config.aggregation_role_weights).map(([role, weight]) => (
                    <Typography key={role} variant="body2">
                      • {formatLabel(role)}: {formatValue(weight)}
                    </Typography>
                  ))}
                </Stack>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                  The non-specific bucket covers KPIs marked as All, Common, or Other.
                </Typography>
              </CardContent>
            </Card>

            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Validation Rules
                </Typography>
                <Stack spacing={1}>
                  {validationRules.map((rule) => (
                    <Typography key={rule} variant="body2" color="text.secondary">
                      • {rule}
                    </Typography>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>

      <Box sx={{ mt: 4 }}>
        <Button component={RouterLink} to="/" startIcon={<ArrowBackIcon />}>
          Back to Home
        </Button>
      </Box>
    </Box>
  )
}
