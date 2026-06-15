import React, { useState } from 'react';
import {
  Container,
  Typography,
  Box,
  Tabs,
  Tab,
  Card,
  CardContent,
} from '@mui/material';
import EmployeeManagementPage from './EmployeeManagementPage';
import RoleManagementPage from './RoleManagementPage';
import UserManagementConfigPage from './UserManagementConfigPage';
import CustomRoleManagementPage from './CustomRoleManagementPage';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`config-tabpanel-${index}`}
      aria-labelledby={`config-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ pt: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

interface SubTabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function SubTabPanel(props: SubTabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`config-subtabpanel-${index}`}
      aria-labelledby={`config-subtab-${index}`}
      {...other}
    >
      {value === index && (
        <Box>
          {children}
        </Box>
      )}
    </div>
  );
}

const ConfigurationPage: React.FC = () => {
  const [mainTab, setMainTab] = useState(0);
  const [teamSightTab, setTeamSightTab] = useState(0);
  const [rbacTab, setRbacTab] = useState(0);

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            Configuration Management
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Manage TeamSight users, roles, RBAC settings, and custom role configurations
          </Typography>
        </Box>
      </Box>

      {/* Main Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs
          value={mainTab}
          onChange={(_, newValue) => setMainTab(newValue)}
          aria-label="configuration tabs"
        >
          <Tab label="TeamSight Users & Roles" />
          <Tab label="RBAC Configuration" />
        </Tabs>
      </Box>

      {/* TAB 0: TeamSight Users & Roles */}
      <TabPanel value={mainTab} index={0}>
        <Card sx={{ mb: 3 }}>
          <CardContent>
            {/* Sub-tabs for TeamSight section */}
            <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
              <Tabs
                value={teamSightTab}
                onChange={(_, newValue) => setTeamSightTab(newValue)}
                aria-label="teamsight subtabs"
              >
                <Tab label="Employee Management" />
                <Tab label="Role & KPI Management" />
              </Tabs>
            </Box>

            {/* Employee Management */}
            <SubTabPanel value={teamSightTab} index={0}>
              <Box sx={{ bgcolor: 'background.paper', borderRadius: 1, p: 2 }}>
                <EmployeeManagementPage />
              </Box>
            </SubTabPanel>

            {/* Role & KPI Management */}
            <SubTabPanel value={teamSightTab} index={1}>
              <Box sx={{ bgcolor: 'background.paper', borderRadius: 1, p: 2 }}>
                <RoleManagementPage />
              </Box>
            </SubTabPanel>
          </CardContent>
        </Card>
      </TabPanel>

      {/* TAB 1: RBAC Configuration */}
      <TabPanel value={mainTab} index={1}>
        <Card sx={{ mb: 3 }}>
          <CardContent>
            {/* Sub-tabs for RBAC section */}
            <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
              <Tabs
                value={rbacTab}
                onChange={(_, newValue) => setRbacTab(newValue)}
                aria-label="rbac subtabs"
              >
                <Tab label="User Management" />
                <Tab label="Custom Roles" />
              </Tabs>
            </Box>

            {/* User Management */}
            <SubTabPanel value={rbacTab} index={0}>
              <Box sx={{ bgcolor: 'background.paper', borderRadius: 1, p: 2 }}>
                <UserManagementConfigPage />
              </Box>
            </SubTabPanel>

            {/* Custom Roles */}
            <SubTabPanel value={rbacTab} index={1}>
              <Box sx={{ bgcolor: 'background.paper', borderRadius: 1, p: 2 }}>
                <CustomRoleManagementPage />
              </Box>
            </SubTabPanel>
          </CardContent>
        </Card>
      </TabPanel>
    </Container>
  );
};

export default ConfigurationPage;
