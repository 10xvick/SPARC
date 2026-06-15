import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Typography,
  Select,
  MenuItem,
  TextField,
  FormControl,
  InputLabel,
  Grid,
  Chip,
  Paper,
  Alert,
} from '@mui/material';
import {
  Schedule as ScheduleIcon,
  Info as InfoIcon,
} from '@mui/icons-material';

interface CronBuilderProps {
  value: string;
  onChange: (cronExpression: string) => void;
  timezoneLabel?: string;
}

type FrequencyType = 'minute' | 'hourly' | 'daily' | 'weekly' | 'monthly' | 'custom';

const daysOfWeek = [
  { value: '0', label: 'Sun' },
  { value: '1', label: 'Mon' },
  { value: '2', label: 'Tue' },
  { value: '3', label: 'Wed' },
  { value: '4', label: 'Thu' },
  { value: '5', label: 'Fri' },
  { value: '6', label: 'Sat' },
];

const CronBuilder: React.FC<CronBuilderProps> = ({ value, onChange, timezoneLabel }) => {
  const isSyncingFromValue = useRef(false);
  const [frequency, setFrequency] = useState<FrequencyType>('daily');
  const [minute, setMinute] = useState<string>('0');
  const [hour, setHour] = useState<string>('2');
  const [dayOfMonth, setDayOfMonth] = useState<string>('1');
  const [selectedDays, setSelectedDays] = useState<string[]>(['1']);
  const [intervalMinutes, setIntervalMinutes] = useState<string>('15');
  const [intervalHours, setIntervalHours] = useState<string>('6');
  const [customExpression, setCustomExpression] = useState<string>('');

  // Parse existing cron expression when component mounts or value changes
  useEffect(() => {
    if (value && value.trim()) {
      isSyncingFromValue.current = true;
      const parts = value.trim().split(/\s+/);
      if (parts.length === 5) {
        const [min, hr, dom, month, dow] = parts;
        
        // Try to detect frequency pattern
        if (dow !== '*' && dom === '*') {
          setFrequency('weekly');
          setMinute(min === '*' ? '0' : min);
          setHour(hr === '*' ? '0' : hr);
          setSelectedDays(dow.split(','));
        } else if (dom !== '*' && dow === '*') {
          setFrequency('monthly');
          setMinute(min === '*' ? '0' : min);
          setHour(hr === '*' ? '0' : hr);
          setDayOfMonth(dom);
        } else if (min.startsWith('*/') && hr === '*' && dom === '*' && dow === '*') {
          setFrequency('minute');
          setIntervalMinutes(min.substring(2));
        } else if (hr.startsWith('*/') && dom === '*' && dow === '*') {
          setFrequency('hourly');
          setMinute(min === '*' ? '0' : min);
          setIntervalHours(hr.substring(2));
        } else if (dom === '*' && dow === '*' && month === '*') {
          setFrequency('daily');
          setMinute(min === '*' ? '0' : min);
          setHour(hr === '*' ? '0' : hr);
        } else {
          setFrequency('custom');
          setCustomExpression(value);
        }
      } else {
        setFrequency('custom');
        setCustomExpression(value);
      }
    }
  }, [value]);

  // Generate cron expression based on current settings
  useEffect(() => {
    if (isSyncingFromValue.current) {
      isSyncingFromValue.current = false;
      return;
    }

    let cron = '';
    
    switch (frequency) {
      case 'minute':
        cron = `*/${intervalMinutes} * * * *`;
        break;
      case 'hourly':
        cron = `${minute} */${intervalHours} * * *`;
        break;
      case 'daily':
        cron = `${minute} ${hour} * * *`;
        break;
      case 'weekly':
        cron = `${minute} ${hour} * * ${[...selectedDays].sort((left, right) => Number(left) - Number(right)).join(',')}`;
        break;
      case 'monthly':
        cron = `${minute} ${hour} ${dayOfMonth} * *`;
        break;
      case 'custom':
        cron = customExpression;
        break;
    }

    if (cron && cron !== value) {
      onChange(cron);
    }
  }, [frequency, minute, hour, dayOfMonth, selectedDays, intervalMinutes, intervalHours, customExpression, value, onChange]);

  const handleDayToggle = (day: string) => {
    setSelectedDays((prev) => {
      if (prev.includes(day)) {
        return prev.filter((d) => d !== day);
      } else {
        return [...prev, day];
      }
    });
  };

  const getHumanReadable = () => {
    switch (frequency) {
      case 'minute':
        return `Every ${intervalMinutes} minute${parseInt(intervalMinutes) > 1 ? 's' : ''}`;
      case 'hourly':
        return `Every ${intervalHours} hour${parseInt(intervalHours) > 1 ? 's' : ''} at minute ${minute}`;
      case 'daily':
        return `Daily at ${hour.padStart(2, '0')}:${minute.padStart(2, '0')} (Local Time)`;
      case 'weekly':
        const dayNames = selectedDays.map(d => daysOfWeek.find(dow => dow.value === d)?.label).join(', ');
        return `Weekly on ${dayNames} at ${hour.padStart(2, '0')}:${minute.padStart(2, '0')} (Local Time)`;
      case 'monthly':
        return `Monthly on day ${dayOfMonth} at ${hour.padStart(2, '0')}:${minute.padStart(2, '0')} (Local Time)`;
      case 'custom':
        return customExpression || 'Custom expression';
      default:
        return '';
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Box display="flex" alignItems="center" mb={2}>
        <ScheduleIcon sx={{ mr: 1 }} color="primary" />
        <Typography variant="subtitle2">Cron Schedule Builder</Typography>
      </Box>

      <FormControl fullWidth sx={{ mb: 2 }}>
        <InputLabel>Frequency</InputLabel>
        <Select
          value={frequency}
          label="Frequency"
          onChange={(e) => setFrequency(e.target.value as FrequencyType)}
        >
          <MenuItem value="minute">Every N Minutes</MenuItem>
          <MenuItem value="hourly">Hourly</MenuItem>
          <MenuItem value="daily">Daily</MenuItem>
          <MenuItem value="weekly">Weekly</MenuItem>
          <MenuItem value="monthly">Monthly</MenuItem>
          <MenuItem value="custom">Custom Expression</MenuItem>
        </Select>
      </FormControl>

      {/* Minute Interval */}
      {frequency === 'minute' && (
        <TextField
          fullWidth
          type="number"
          label="Interval (minutes)"
          value={intervalMinutes}
          onChange={(e) => setIntervalMinutes(e.target.value)}
          inputProps={{ min: 1, max: 59 }}
          helperText="Run every N minutes"
        />
      )}

      {/* Hourly */}
      {frequency === 'hourly' && (
        <Grid container spacing={2}>
          <Grid item xs={6}>
            <TextField
              fullWidth
              type="number"
              label="Every N Hours"
              value={intervalHours}
              onChange={(e) => setIntervalHours(e.target.value)}
              inputProps={{ min: 1, max: 23 }}
            />
          </Grid>
          <Grid item xs={6}>
            <TextField
              fullWidth
              type="number"
              label="Minute"
              value={minute}
              onChange={(e) => setMinute(e.target.value)}
              inputProps={{ min: 0, max: 59 }}
            />
          </Grid>
        </Grid>
      )}

      {/* Daily */}
      {frequency === 'daily' && (
        <Grid container spacing={2}>
          <Grid item xs={6}>
            <TextField
              fullWidth
              type="number"
              label="Hour (24h, local)"
              value={hour}
              onChange={(e) => setHour(e.target.value)}
              inputProps={{ min: 0, max: 23 }}
            />
          </Grid>
          <Grid item xs={6}>
            <TextField
              fullWidth
              type="number"
              label="Minute"
              value={minute}
              onChange={(e) => setMinute(e.target.value)}
              inputProps={{ min: 0, max: 59 }}
            />
          </Grid>
        </Grid>
      )}

      {/* Weekly */}
      {frequency === 'weekly' && (
        <Box>
          <Typography variant="body2" gutterBottom>
            Select Days of Week
          </Typography>
          <Box display="flex" gap={0.5} mb={2} flexWrap="wrap">
            {daysOfWeek.map((day) => (
              <Chip
                key={day.value}
                label={day.label}
                onClick={() => handleDayToggle(day.value)}
                color={selectedDays.includes(day.value) ? 'primary' : 'default'}
                variant={selectedDays.includes(day.value) ? 'filled' : 'outlined'}
              />
            ))}
          </Box>
          <Grid container spacing={2}>
            <Grid item xs={6}>
              <TextField
                fullWidth
                type="number"
                label="Hour (24h, local)"
                value={hour}
                onChange={(e) => setHour(e.target.value)}
                inputProps={{ min: 0, max: 23 }}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                type="number"
                label="Minute"
                value={minute}
                onChange={(e) => setMinute(e.target.value)}
                inputProps={{ min: 0, max: 59 }}
              />
            </Grid>
          </Grid>
        </Box>
      )}

      {/* Monthly */}
      {frequency === 'monthly' && (
        <Box>
          <TextField
            fullWidth
            type="number"
            label="Day of Month"
            value={dayOfMonth}
            onChange={(e) => setDayOfMonth(e.target.value)}
            inputProps={{ min: 1, max: 31 }}
            sx={{ mb: 2 }}
          />
          <Grid container spacing={2}>
            <Grid item xs={6}>
              <TextField
                fullWidth
                type="number"
                label="Hour (24h, local)"
                value={hour}
                onChange={(e) => setHour(e.target.value)}
                inputProps={{ min: 0, max: 23 }}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                type="number"
                label="Minute"
                value={minute}
                onChange={(e) => setMinute(e.target.value)}
                inputProps={{ min: 0, max: 59 }}
              />
            </Grid>
          </Grid>
        </Box>
      )}

      {/* Custom */}
      {frequency === 'custom' && (
        <TextField
          fullWidth
          label="Cron Expression"
          value={customExpression}
          onChange={(e) => setCustomExpression(e.target.value)}
          placeholder="0 2 * * *"
          helperText="Format: minute hour day month day-of-week"
        />
      )}

      {/* Generated Expression Display */}
      <Alert 
        severity="info" 
        icon={<InfoIcon />}
        sx={{ mt: 2 }}
      >
        <Typography variant="body2" fontWeight="medium">
          {getHumanReadable()}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          {timezoneLabel ? `Timezone: ${timezoneLabel}` : 'Timezone: Local Browser Time'}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          Cron: <code>{value || 'Not set'}</code>
        </Typography>
      </Alert>
    </Paper>
  );
};

export default CronBuilder;
