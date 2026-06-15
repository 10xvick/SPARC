import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Grid,
  Alert,
  CircularProgress,
  Slider,
  Stack,
} from '@mui/material';
import { Save as SaveIcon, Refresh as RefreshIcon } from '@mui/icons-material';
import axios from 'axios';
import LockIcon from '@mui/icons-material/Lock';
import { useAuth } from '../context/AuthContext';

const API_BASE_URL = '';

interface Weightages {
  Input: number;
  Output: number;
  Quality: number;
  Hygiene: number;
}

interface StatusWeights {
  Green: number;
  Orange: number;
  Red: number;
}

interface RoleWeights {
  Primary: number;
  Secondary: number;
  All: number;
  Common: number;
  Other: number;
}

interface AggregationRoleWeights {
  specific: number;
  non_specific: number;
}

interface ROGThresholds {
  green_threshold: number;
  orange_threshold: number;
}

interface ScoreDisplayThresholds {
  green_min: number;
  orange_min: number;
  red_max: number;
}

const defaultWeightages: Weightages = {
  Input: 10,
  Output: 50,
  Quality: 30,
  Hygiene: 10,
};

const defaultStatusWeights: StatusWeights = {
  Green: 1.0,
  Orange: 0.75,
  Red: 0.0,
};

const defaultRoleWeights: RoleWeights = {
  Primary: 20,
  Secondary: 10,
  All: 5,
  Common: 3,
  Other: 1,
};

const defaultAggregationRoleWeights: AggregationRoleWeights = {
  specific: 10,
  non_specific: 5,
};

const defaultROGThresholds: ROGThresholds = {
  green_threshold: 100.0,
  orange_threshold: 70.0,
};

const defaultScoreDisplayThresholds: ScoreDisplayThresholds = {
  green_min: 70.0,
  orange_min: 36.0,
  red_max: 35.0,
};

export const ScoringConfigPanel: React.FC = () => {
  const { user } = useAuth();
  const isReadOnly = user?.role === 'Admin Viewer';
  const readOnlyMessage = 'Read-only access: Admin Viewer users cannot modify scoring configuration';
  const [weightages, setWeightages] = useState<Weightages>(defaultWeightages);
  const [statusWeights, setStatusWeights] = useState<StatusWeights>(defaultStatusWeights);
  const [roleWeights, setRoleWeights] = useState<RoleWeights>(defaultRoleWeights);
  const [aggregationRoleWeights, setAggregationRoleWeights] = useState<AggregationRoleWeights>(defaultAggregationRoleWeights);
  const [rogThresholds, setROGThresholds] = useState<ROGThresholds>(defaultROGThresholds);
  const [scoreDisplayThresholds, setScoreDisplayThresholds] = useState<ScoreDisplayThresholds>(defaultScoreDisplayThresholds);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/score-config`);
      setWeightages(response.data.weightages);
      setStatusWeights(response.data.status_weights);
      setRoleWeights(response.data.role_weights || defaultRoleWeights);
      setAggregationRoleWeights(response.data.aggregation_role_weights || defaultAggregationRoleWeights);
      setROGThresholds(response.data.rog_thresholds);
      setScoreDisplayThresholds(response.data.score_display_thresholds);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load scoring configuration');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    // Validate weightages total equals 100
    const total = Object.values(weightages).reduce((sum, val) => sum + val, 0);
    if (Math.abs(total - 100) > 0.01) {
      setError(`Total weightage must equal 100% (currently ${total.toFixed(1)}%)`);
      return;
    }

    // Validate status weights are in 0-1 range
    if (Object.values(statusWeights).some(w => w < 0 || w > 1)) {
      setError('Status weights must be between 0 and 1');
      return;
    }

    // Validate role weights are in 0-20 range
    if (Object.values(roleWeights).some(w => w < 0 || w > 20)) {
      setError('Role weights must be between 0 and 20');
      return;
    }

    // Validate aggregation role weights are in 0-20 range
    if (Object.values(aggregationRoleWeights).some(w => w < 0 || w > 20)) {
      setError('Aggregation role weights must be between 0 and 20');
      return;
    }

    // Validate ROG thresholds ordering
    if (rogThresholds.orange_threshold > rogThresholds.green_threshold) {
      setError('Orange threshold must be less than or equal to Green threshold');
      return;
    }

    // Validate score display thresholds ordering
    if (scoreDisplayThresholds.red_max >= scoreDisplayThresholds.orange_min) {
      setError('Red max must be less than Orange min');
      return;
    }
    if (scoreDisplayThresholds.orange_min >= scoreDisplayThresholds.green_min) {
      setError('Orange min must be less than Green min');
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const config = {
        weightages,
        status_weights: statusWeights,
        role_weights: roleWeights,
        aggregation_role_weights: aggregationRoleWeights,
        rog_thresholds: rogThresholds,
        score_display_thresholds: scoreDisplayThresholds,
      };
      await axios.put(`${API_BASE_URL}/api/score-config`, config);
      setSuccess('Scoring configuration updated successfully');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save scoring configuration');
    } finally {
      setSaving(false);
    }
  };

  const handleWeightageChange = (category: keyof Weightages, value: number) => {
    setWeightages((prev) => ({ ...prev, [category]: value }));
    setError(null);
    setSuccess(null);
  };

  const handleStatusWeightChange = (status: keyof StatusWeights, value: number) => {
    setStatusWeights((prev) => ({ ...prev, [status]: value }));
    setError(null);
    setSuccess(null);
  };

  const handleRoleWeightChange = (roleType: keyof RoleWeights, value: number) => {
    setRoleWeights((prev) => ({ ...prev, [roleType]: value }));
    setError(null);
    setSuccess(null);
  };

  const handleAggregationRoleWeightChange = (roleType: keyof AggregationRoleWeights, value: number) => {
    setAggregationRoleWeights((prev) => ({ ...prev, [roleType]: value }));
    setError(null);
    setSuccess(null);
  };

  const handleReset = () => {
    setWeightages(defaultWeightages);
    setStatusWeights(defaultStatusWeights);
    setRoleWeights(defaultRoleWeights);
    setAggregationRoleWeights(defaultAggregationRoleWeights);
    setROGThresholds(defaultROGThresholds);
    setScoreDisplayThresholds(defaultScoreDisplayThresholds);
    setError(null);
    setSuccess(null);
  };

  const total = Object.values(weightages).reduce((sum, val) => sum + val, 0);
  const isValidTotal = Math.abs(total - 100) < 0.01;

  const getCategoryColor = (category: string): string => {
    const colors: { [key: string]: string } = {
      Input: '#2196f3',
      Output: '#4caf50',
      Quality: '#ff9800',
      Hygiene: '#9c27b0',
    };
    return colors[category] || '#757575';
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Performance Scoring Configuration
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Configure weightages for each KPI category. Total must equal 100%.
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {success && (
          <Alert severity="success" sx={{ mb: 2 }}>
            {success}
          </Alert>
        )}

        {isReadOnly && (
          <Alert severity="info" icon={<LockIcon />} sx={{ mb: 2 }}>
            <strong>Read-Only Access:</strong> You can view scoring and threshold configuration but cannot modify it.
          </Alert>
        )}

        <Grid container spacing={3}>
          {(Object.keys(weightages) as Array<keyof Weightages>).map((category) => (
            <Grid item xs={12} md={6} key={category}>
              <Box
                sx={{
                  p: 2,
                  border: '1px solid #e0e0e0',
                  borderRadius: 1,
                  borderLeft: `4px solid ${getCategoryColor(category)}`,
                }}
              >
                <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600 }}>
                  {category}
                </Typography>
                <Stack direction="row" spacing={2} alignItems="center">
                  <Slider
                    value={weightages[category]}
                    onChange={(_, value) => handleWeightageChange(category, value as number)}
                      disabled={isReadOnly}
                    min={0}
                    max={100}
                    step={1}
                    valueLabelDisplay="auto"
                    sx={{
                      flex: 1,
                      '& .MuiSlider-thumb': {
                        backgroundColor: getCategoryColor(category),
                      },
                      '& .MuiSlider-track': {
                        backgroundColor: getCategoryColor(category),
                      },
                      '& .MuiSlider-rail': {
                        backgroundColor: '#e0e0e0',
                      },
                    }}
                  />
                  <TextField
                    value={weightages[category]}
                    disabled={isReadOnly}
                    onChange={(e) => {
                      const value = parseFloat(e.target.value) || 0;
                      handleWeightageChange(category, Math.min(100, Math.max(0, value)));
                    }}
                    type="number"
                    size="small"
                    sx={{ width: 80 }}
                    InputProps={{
                      endAdornment: '%',
                    }}
                  />
                </Stack>
              </Box>
            </Grid>
          ))}
        </Grid>

        {/* Total Display */}
        <Box
          sx={{
            mt: 3,
            p: 2,
            backgroundColor: isValidTotal ? '#e8f5e9' : '#ffebee',
            borderRadius: 1,
            border: `1px solid ${isValidTotal ? '#4caf50' : '#f44336'}`,
          }}
        >
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            Total: {total.toFixed(1)}% {isValidTotal ? '✓' : '✗ Must equal 100%'}
          </Typography>
        </Box>

        {/* Status Weights Configuration */}
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            Status Weights
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Configure credit given for each KPI status (0-1 range). Determines how much each status contributes to the score.
          </Typography>
          <Grid container spacing={3}>
            {(Object.keys(statusWeights) as Array<keyof StatusWeights>).map((status) => (
              <Grid item xs={12} md={4} key={status}>
                <Box
                  sx={{
                    p: 2,
                    border: '1px solid #e0e0e0',
                    borderRadius: 1,
                    borderLeft: `4px solid ${status === 'Green' ? '#4caf50' : status === 'Orange' ? '#ff9800' : '#f44336'}`,
                  }}
                >
                  <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600 }}>
                    {status}
                  </Typography>
                  <Stack direction="row" spacing={2} alignItems="center">
                    <Slider
                      value={statusWeights[status]}
                      onChange={(_, value) => handleStatusWeightChange(status, value as number)}
                      disabled={isReadOnly}
                      min={0}
                      max={1}
                      step={0.05}
                      valueLabelDisplay="auto"
                      valueLabelFormat={(value) => `${(value * 100).toFixed(0)}%`}
                      sx={{
                        flex: 1,
                        '& .MuiSlider-thumb': {
                          backgroundColor: status === 'Green' ? '#4caf50' : status === 'Orange' ? '#ff9800' : '#f44336',
                        },
                        '& .MuiSlider-track': {
                          backgroundColor: status === 'Green' ? '#4caf50' : status === 'Orange' ? '#ff9800' : '#f44336',
                        },
                        '& .MuiSlider-rail': {
                          backgroundColor: '#e0e0e0',
                        },
                      }}
                    />
                    <TextField
                      value={statusWeights[status]}
                      disabled={isReadOnly}
                      onChange={(e) => {
                        const value = parseFloat(e.target.value) || 0;
                        handleStatusWeightChange(status, Math.min(1, Math.max(0, value)));
                      }}
                      type="number"
                      size="small"
                      inputProps={{ step: 0.05, min: 0, max: 1 }}
                      sx={{ width: 80 }}
                    />
                  </Stack>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Box>

        {/* Individual Role Weights Configuration */}
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            Individual Role Weights
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Configure KPI weights by individual applicability: Primary, Secondary, All, Common, and Other (0-20 per field).
          </Typography>
          <Grid container spacing={3}>
            {(Object.keys(roleWeights) as Array<keyof RoleWeights>).map((roleType) => (
              <Grid item xs={12} md={6} key={roleType}>
                <Box
                  sx={{
                    p: 2,
                    border: '1px solid #e0e0e0',
                    borderRadius: 1,
                  }}
                >
                  <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600 }}>
                    {roleType}
                  </Typography>
                  <Stack direction="row" spacing={2} alignItems="center">
                    <Slider
                      value={roleWeights[roleType]}
                      onChange={(_, value) => handleRoleWeightChange(roleType, value as number)}
                      disabled={isReadOnly}
                      min={0}
                      max={20}
                      step={1}
                      valueLabelDisplay="auto"
                      sx={{ flex: 1 }}
                    />
                    <TextField
                      value={roleWeights[roleType]}
                      disabled={isReadOnly}
                      onChange={(e) => {
                        const value = parseFloat(e.target.value) || 0;
                        handleRoleWeightChange(roleType, Math.min(20, Math.max(0, value)));
                      }}
                      type="number"
                      size="small"
                      inputProps={{ step: 1, min: 0, max: 20 }}
                      sx={{ width: 90 }}
                    />
                  </Stack>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Box>

        {/* Team/Scrum Aggregation Role Weights Configuration */}
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            Team/Scrum Aggregation Weights
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Configure weights used when aggregating KPI scores for team and scrum dashboards (0-20 per field).
            <br />"Specific" applies to KPIs tied to a particular role; "Non-Specific" covers KPIs applicable to All, Common, or Other.
          </Typography>
          <Grid container spacing={3}>
            {(Object.keys(aggregationRoleWeights) as Array<keyof AggregationRoleWeights>).map((roleType) => {
              const aggRoleLabels: Record<keyof AggregationRoleWeights, string> = {
                specific: 'Specific',
                non_specific: 'Non-Specific (All / Common / Other)',
              };
              return (
              <Grid item xs={12} md={6} key={roleType}>
                <Box
                  sx={{
                    p: 2,
                    border: '1px solid #e0e0e0',
                    borderRadius: 1,
                  }}
                >
                  <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600 }}>
                    {aggRoleLabels[roleType]}
                  </Typography>
                  <Stack direction="row" spacing={2} alignItems="center">
                    <Slider
                      value={aggregationRoleWeights[roleType]}
                      onChange={(_, value) => handleAggregationRoleWeightChange(roleType, value as number)}
                      disabled={isReadOnly}
                      min={0}
                      max={20}
                      step={1}
                      valueLabelDisplay="auto"
                      sx={{ flex: 1 }}
                    />
                    <TextField
                      value={aggregationRoleWeights[roleType]}
                      disabled={isReadOnly}
                      onChange={(e) => {
                        const value = parseFloat(e.target.value) || 0;
                        handleAggregationRoleWeightChange(roleType, Math.min(20, Math.max(0, value)));
                      }}
                      type="number"
                      size="small"
                      inputProps={{ step: 1, min: 0, max: 20 }}
                      sx={{ width: 90 }}
                    />
                  </Stack>
                </Box>
              </Grid>
              );
            })}
          </Grid>
        </Box>

        {/* ROG Thresholds Configuration */}
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            KPI Status Thresholds (ROG)
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Configure thresholds for determining individual KPI status on a 0-100% scale.
          </Typography>
          <Box
            sx={{
              p: 3,
              border: '1px solid #e0e0e0',
              borderRadius: 1,
            }}
          >
            <Box sx={{ mb: 3 }}>
              <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                KPI Performance Thresholds (%)
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                Drag the handles to set threshold boundaries. Red: &lt; Orange | Orange: ≥ Orange threshold | Green: ≥ Green threshold
              </Typography>
            </Box>
            <Box sx={{ px: 2, mb: 3 }}>
              <Slider
                value={[rogThresholds.orange_threshold, rogThresholds.green_threshold]}
                onChange={(_, value) => {
                  const [orange, green] = value as number[];
                  setROGThresholds({ orange_threshold: orange, green_threshold: green });
                  setError(null);
                  setSuccess(null);
                }}
                disabled={isReadOnly}
                min={0}
                max={100}
                step={5}
                marks={[
                  { value: 0, label: '0%' },
                  { value: 25, label: '25%' },
                  { value: 50, label: '50%' },
                  { value: 75, label: '75%' },
                  { value: 100, label: '100%' },
                ]}
                valueLabelDisplay="on"
                valueLabelFormat={(value) => `${value}%`}
                sx={{
                  '& .MuiSlider-thumb:first-of-type': {
                    backgroundColor: '#ff9800',
                  },
                  '& .MuiSlider-thumb:last-of-type': {
                    backgroundColor: '#4caf50',
                  },
                  '& .MuiSlider-track': {
                    background: 'linear-gradient(to right, #ff9800 0%, #4caf50 100%)',
                  },
                  '& .MuiSlider-rail': {
                    backgroundColor: '#f44336',
                    opacity: 0.3,
                  },
                }}
              />
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Box sx={{ width: 12, height: 12, backgroundColor: '#ff9800', borderRadius: '50%' }} />
                  <Typography variant="caption">Orange: {rogThresholds.orange_threshold}%</Typography>
                </Stack>
              </Grid>
              <Grid item xs={6}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Box sx={{ width: 12, height: 12, backgroundColor: '#4caf50', borderRadius: '50%' }} />
                  <Typography variant="caption">Green: {rogThresholds.green_threshold}%</Typography>
                </Stack>
              </Grid>
            </Grid>
          </Box>
        </Box>

        {/* Score Display Thresholds Configuration */}
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            Score Display Thresholds
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Configure thresholds for gauge color coding on a 0-100 score scale.
          </Typography>
          <Box
            sx={{
              p: 3,
              border: '1px solid #e0e0e0',
              borderRadius: 1,
            }}
          >
            <Box sx={{ mb: 3 }}>
              <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                Score Color Boundaries
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                Drag the handles to set color zone boundaries. Red zone: 0 to first handle | Orange zone: first to second handle | Green zone: second handle to 100
              </Typography>
            </Box>
            <Box sx={{ px: 2, mb: 3 }}>
              <Slider
                value={[scoreDisplayThresholds.orange_min, scoreDisplayThresholds.green_min]}
                onChange={(_, value) => {
                  const [orangeMin, greenMin] = value as number[];
                  setScoreDisplayThresholds({
                    red_max: orangeMin - 1,
                    orange_min: orangeMin,
                    green_min: greenMin,
                  });
                  setError(null);
                  setSuccess(null);
                }}
                disabled={isReadOnly}
                min={1}
                max={100}
                step={1}
                marks={[
                  { value: 0, label: '0' },
                  { value: 25, label: '25' },
                  { value: 50, label: '50' },
                  { value: 75, label: '75' },
                  { value: 100, label: '100' },
                ]}
                valueLabelDisplay="on"
                sx={{
                  '& .MuiSlider-thumb:first-of-type': {
                    backgroundColor: '#ff9800',
                  },
                  '& .MuiSlider-thumb:last-of-type': {
                    backgroundColor: '#4caf50',
                  },
                  '& .MuiSlider-track': {
                    background: 'linear-gradient(to right, #ff9800 0%, #4caf50 100%)',
                  },
                  '& .MuiSlider-rail': {
                    backgroundColor: '#f44336',
                    opacity: 0.3,
                  },
                }}
              />
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={4}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Box sx={{ width: 12, height: 12, backgroundColor: '#f44336', borderRadius: '50%' }} />
                  <Typography variant="caption">Red: 0-{scoreDisplayThresholds.red_max}</Typography>
                </Stack>
              </Grid>
              <Grid item xs={4}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Box sx={{ width: 12, height: 12, backgroundColor: '#ff9800', borderRadius: '50%' }} />
                  <Typography variant="caption">Orange: {scoreDisplayThresholds.orange_min}-{scoreDisplayThresholds.green_min - 1}</Typography>
                </Stack>
              </Grid>
              <Grid item xs={4}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Box sx={{ width: 12, height: 12, backgroundColor: '#4caf50', borderRadius: '50%' }} />
                  <Typography variant="caption">Green: {scoreDisplayThresholds.green_min}-100</Typography>
                </Stack>
              </Grid>
            </Grid>
          </Box>
        </Box>

        {/* Action Buttons */}
        <Box sx={{ mt: 3, display: 'flex', gap: 2 }}>
          <Button
            variant="contained"
            startIcon={saving ? <CircularProgress size={20} /> : <SaveIcon />}
            onClick={handleSave}
            disabled={isReadOnly || saving || !isValidTotal}
            title={isReadOnly ? readOnlyMessage : ''}
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </Button>
          <Button variant="outlined" startIcon={<RefreshIcon />} onClick={handleReset} disabled={isReadOnly} title={isReadOnly ? readOnlyMessage : ''}>
            Reset to Default
          </Button>
          <Button variant="outlined" onClick={loadConfig}>
            Reload
          </Button>
        </Box>

        {/* Formula Information */}
        <Box sx={{ mt: 3, p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
          <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
            <strong>Scoring Formula:</strong>
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            Overall Score = Σ[(Σ(role_weight × status_weight)) / Σ(role_weight) × Category Weightage]
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
            • Status weights (Green/Orange/Red) and role weights are configurable above
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            • KPI status (R/O/G) determined by ROG thresholds
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            • Gauge colors determined by score display thresholds
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            • Maximum score is 100
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            • Changes apply immediately to all dashboards
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
};

export default ScoringConfigPanel;
