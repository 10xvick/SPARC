import React from 'react';
import { Box, Card, CardContent, Typography } from '@mui/material';

interface ScoreData {
  overall_score: number;
  max_score: number;
}

interface ScoreGaugeProps {
  score: ScoreData;
  title?: string;
  size?: number;
}

const getScoreColor = (score: number): string => {
  if (score >= 80) return '#4caf50'; // Green
  if (score >= 60) return '#ff9800'; // Orange
  return '#f44336'; // Red
};

const getScoreLabel = (score: number): string => {
  if (score >= 80) return 'Excellent';
  if (score >= 60) return 'Good';
  return 'Needs Work';
};

export const ScoreGauge: React.FC<ScoreGaugeProps> = ({ 
  score, 
  title = 'Performance Score',
  size = 160 
}) => {
  const scoreValue = score.overall_score;
  const scoreColor = getScoreColor(scoreValue);
  const scoreLabel = getScoreLabel(scoreValue);
  const percentage = (scoreValue / score.max_score) * 100;
  
  // Calculate stroke dash array for circular progress
  const radius = (size - 20) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  return (
    <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <CardContent sx={{ 
        display: 'flex', 
        flexDirection: 'column', 
        alignItems: 'center', 
        justifyContent: 'center',
        flex: 1,
        p: 2
      }}>
        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
          {title}
        </Typography>
        
        {/* Circular Gauge */}
        <Box sx={{ position: 'relative', display: 'inline-flex', my: 1 }}>
          <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
            {/* Background circle */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="#e0e0e0"
              strokeWidth="12"
            />
            {/* Progress circle */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={scoreColor}
              strokeWidth="12"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              style={{
                transition: 'stroke-dashoffset 0.5s ease-in-out'
              }}
            />
          </svg>
          
          {/* Score text in center */}
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              bottom: 0,
              right: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Typography 
              variant="h3" 
              sx={{ 
                fontWeight: 'bold', 
                color: scoreColor,
                lineHeight: 1
              }}
            >
              {scoreValue.toFixed(0)}
            </Typography>
            <Typography 
              variant="caption" 
              color="text.secondary"
              sx={{ fontSize: '0.7rem' }}
            >
              out of {score.max_score}
            </Typography>
          </Box>
        </Box>
        
        {/* Score label */}
        <Box 
          sx={{ 
            mt: 1,
            px: 2, 
            py: 0.5, 
            backgroundColor: `${scoreColor}20`,
            borderRadius: 1,
            border: `1px solid ${scoreColor}40`
          }}
        >
          <Typography 
            variant="caption" 
            sx={{ 
              fontWeight: 600,
              color: scoreColor,
              textTransform: 'uppercase',
              letterSpacing: '0.5px'
            }}
          >
            {scoreLabel}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
};

export default ScoreGauge;
