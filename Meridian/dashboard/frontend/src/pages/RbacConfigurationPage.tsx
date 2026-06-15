import React, { useState } from 'react';
import {
  Box,
  Tabs,
  Tab,
  Typography,
} from '@mui/material';
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
      id={`rbac-tabpanel-${index}`}
      aria-labelledby={`rbac-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 2 }}>{children}</Box>}
    </div>
  );
}

const RbacConfigurationPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState(0);

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          RBAC Configuration
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Manage users and custom role permissions for access control
        </Typography>
      </Box>

      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => setActiveTab(newValue)}
          aria-label="rbac configuration tabs"
        >
          <Tab label="User Management" id="rbac-tab-0" aria-controls="rbac-tabpanel-0" />
          <Tab label="Custom Roles" id="rbac-tab-1" aria-controls="rbac-tabpanel-1" />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0}>
        <UserManagementConfigPage />
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        <CustomRoleManagementPage />
      </TabPanel>
    </Box>
  );
};

export default RbacConfigurationPage;
