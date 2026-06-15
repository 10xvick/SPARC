import React, { useState } from 'react';
import {
  Box,
  Tabs,
  Tab,
  Typography,
} from '@mui/material';
import EmployeeManagementPage from './EmployeeManagementPage';
import RoleManagementPage from './RoleManagementPage';

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
      id={`teamsight-tabpanel-${index}`}
      aria-labelledby={`teamsight-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 2 }}>{children}</Box>}
    </div>
  );
}

const TeamSightUsersRolesPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState(0);

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          TeamSight Users & Roles
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Manage employee records and role KPI definitions
        </Typography>
      </Box>

      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => setActiveTab(newValue)}
          aria-label="teamsight users and roles tabs"
        >
          <Tab label="Employee Management" id="teamsight-tab-0" aria-controls="teamsight-tabpanel-0" />
          <Tab label="Role & KPI Management" id="teamsight-tab-1" aria-controls="teamsight-tabpanel-1" />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0}>
        <EmployeeManagementPage />
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        <RoleManagementPage />
      </TabPanel>
    </Box>
  );
};

export default TeamSightUsersRolesPage;
