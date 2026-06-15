import { useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  Link,
  Stack,
  Typography,
} from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import WorkspacePremiumIcon from '@mui/icons-material/WorkspacePremium'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import { appConfigApi } from '../services/appConfigApi'

const capabilities = [
  'Tracks KPI performance for employees, scrums, and teams through one connected dashboard experience.',
  'Combines resource, role, JIRA, and GitHub data to produce measurable delivery and quality insights.',
  'Supports role-based KPI applicability, weighted scoring, and drill-down navigation from team to scrum to employee.',
  'Includes assigned-task visibility for employees with due-date awareness, delay flags, and issue type context.',
  'Provides issue transition history views for authorized roles to support delay attribution and ownership analysis.',
  'Enforces RBAC-aware access across dashboards, reports, and contextual actions while preserving self-service employee views.',
  'Provides administration features for configuration, onboarding, data collection, and service monitoring.',
]

export default function AboutPage() {
  const [teamSightVersion, setTeamSightVersion] = useState('0.1.0')
  const currentYear = new Date().getFullYear()

  useEffect(() => {
    let active = true

    const loadVersion = async () => {
      try {
        const config = await appConfigApi.getConfig()
        if (active && config.version) {
          setTeamSightVersion(config.version)
        }
      } catch {
        // Keep default version when config endpoint is unavailable
      }
    }

    loadVersion()

    return () => {
      active = false
    }
  }, [])

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <InfoOutlinedIcon color="primary" />
        <Typography variant="h4" fontWeight="bold">
          About TeamSight
        </Typography>
        <Chip label={`TeamSight v${teamSightVersion}`} color="primary" variant="outlined" />
      </Stack>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 4, maxWidth: 900 }}>
        TeamSight is a product for structured KPI visibility across engineering organizations. It helps leaders and teams
        monitor performance consistently by aligning role-specific expectations, aggregated delivery views, assigned work
        status, and clear operational reporting in one place.
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={7}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Product Summary
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                TeamSight centralizes employee, scrum, and team performance measurement using KPI definitions mapped to
                organizational roles. It evaluates outcomes from connected delivery data sources and turns them into
                actionable dashboards, reports, score views, and assignee-level task intelligence.
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                The platform is designed to support both operational tracking and leadership review by making KPI
                applicability explicit, surfacing trends by group, and enabling drill-down navigation from team to scrum
                to individual contributor views. Recent enhancements include task-level issue type visibility, delay-aware
                assigned task tracking, and transition-history drilldowns for authorized users.
              </Typography>
              <Stack spacing={1.25} sx={{ mt: 2 }}>
                {capabilities.map((capability) => (
                  <Typography key={capability} variant="body2" color="text.secondary">
                    • {capability}
                  </Typography>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={5}>
          <Stack spacing={3}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Core Scope
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Chip label="KPI Dashboards" color="primary" variant="outlined" />
                  <Chip label="Role-Based Scoring" color="primary" variant="outlined" />
                  <Chip label="Assigned Tasks" color="primary" variant="outlined" />
                  <Chip label="Issue Type Insights" color="primary" variant="outlined" />
                  <Chip label="Transition History" color="primary" variant="outlined" />
                  <Chip label="JIRA Insights" color="primary" variant="outlined" />
                  <Chip label="GitHub Insights" color="primary" variant="outlined" />
                  <Chip label="Operational Reports" color="primary" variant="outlined" />
                  <Chip label="RBAC Controls" color="primary" variant="outlined" />
                  <Chip label="Admin Controls" color="primary" variant="outlined" />
                </Stack>
              </CardContent>
            </Card>

            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Contributors
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  TeamSight was ideated and created with contributions from the following:
                </Typography>
                <Stack spacing={1}>
                  <Typography variant="body2">• D.B.Srinivas Rao</Typography>
                  <Typography variant="body2">• Sailesh Chopra</Typography>
                  <Typography variant="body2">• Shashidhar Krishnamurthy</Typography>
                </Stack>

                <Divider sx={{ my: 2 }} />
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                  <WorkspacePremiumIcon color="primary" fontSize="small" />
                  <Typography variant="subtitle2" fontWeight={600}>
                    Endorsement
                  </Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  TeamSight supports the organization\'s AI acceleration journey highlighted in the Microsoft AI First Movers story.
                </Typography>
                <Typography variant="body2" sx={{ mt: 1 }}>
                  <Link
                    href="https://www.microsoft.com/en-in/aifirstmovers/hcltech"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Stack direction="row" spacing={0.5} alignItems="center" component="span">
                      <span>View Microsoft AI First Movers: HCLTech</span>
                      <OpenInNewIcon sx={{ fontSize: 16 }} />
                    </Stack>
                  </Link>
                </Typography>
              </CardContent>
            </Card>

            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" fontWeight="bold" gutterBottom>
                  Version & Legal
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  TeamSight v{teamSightVersion}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  © {currentYear} TeamSight. All rights reserved.
                </Typography>
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
