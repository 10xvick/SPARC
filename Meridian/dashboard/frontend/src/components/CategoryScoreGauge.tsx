/**
 * CategoryScoreGauge Component
 * Displays performance scores as circular gauges with ROG status colors
 */
import React from 'react';
import { Box, Card, Typography } from '@mui/material';

interface CategoryScoreGaugeProps {
  category: string;
  score: number;
  maxScore: number;
  rogStatus: 'green' | 'orange' | 'red';
  isOverall?: boolean;
}

const getBackgroundColor = (rogStatus: 'green' | 'orange' | 'red'): string => {
  const colors = {
    green: '#66BB6A',
    orange: '#FFA726',
    red: '#EF5350'
  };
  return colors[rogStatus];
};

export const CategoryScoreGauge: React.FC<CategoryScoreGaugeProps> = ({
  category,
  score,
  maxScore,
  rogStatus,
  isOverall = false
}) => {
  const backgroundColor = getBackgroundColor(rogStatus);
  const percentage = maxScore > 0 ? (score / maxScore) * 100 : 0;
  const size = isOverall ? 140 : 120;
  const strokeWidth = isOverall ? 12 : 10;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percentage / 100) * circumference;

  return (
    <Card
      sx={{
        background: `linear-gradient(135deg, ${backgroundColor}15 0%, ${backgroundColor}05 100%)`,
        border: `2px solid ${backgroundColor}40`,
        height: '100%',
        minHeight: isOverall ? 220 : 200,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        position: 'relative',
        overflow: 'hidden',
        transition: 'transform 0.2s, box-shadow 0.2s, border-color 0.2s',
        '&:hover': {
          transform: 'translateY(-4px)',
          boxShadow: `0 8px 24px ${backgroundColor}40`,
          borderColor: backgroundColor,
        },
      }}
    >
      {/* Content */}
      <Box sx={{ position: 'relative', textAlign: 'center', width: '100%', px: 2 }}>
        {/* Category Name */}
        <Typography
          variant="subtitle2"
          sx={{
            fontWeight: 600,
            fontSize: isOverall ? '0.9rem' : '0.85rem',
            color: 'text.primary',
            mb: 2,
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}
        >
          {category}
        </Typography>

        {/* Circular Gauge */}
        <Box
          sx={{
            position: 'relative',
            display: 'inline-flex',
            mb: 1,
          }}
        >
          <svg width={size} height={size}>
            {/* Background Circle */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="#e0e0e0"
              strokeWidth={strokeWidth}
            />
            {/* Progress Circle */}
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={backgroundColor}
              strokeWidth={strokeWidth}
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              strokeLinecap="round"
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
              style={{
                transition: 'stroke-dashoffset 0.5s ease',
              }}
            />
          </svg>
          {/* Center Text */}
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
            {isOverall ? (
              // Overall Score: Show as number
              <>
                <Typography
                  variant="h3"
                  sx={{
                    fontWeight: 'bold',
                    fontSize: '2rem',
                    color: backgroundColor,
                    lineHeight: 1,
                  }}
                >
                  {score.toFixed(1)}
                </Typography>
                <Typography
                  variant="caption"
                  sx={{
                    fontSize: '0.65rem',
                    color: 'text.secondary',
                    fontWeight: 500,
                    mt: 0.5,
                  }}
                >
                  out of {maxScore}
                </Typography>
              </>
            ) : (
              // Category Scores: Show as percentage
              <Typography
                variant="h3"
                sx={{
                  fontWeight: 'bold',
                  fontSize: '1.75rem',
                  color: backgroundColor,
                  lineHeight: 1,
                }}
              >
                {percentage.toFixed(1)}%
              </Typography>
            )}
          </Box>
        </Box>
      </Box>
    </Card>
  );
};

export default CategoryScoreGauge;
