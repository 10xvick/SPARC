import { useEffect, useState } from 'react'
import { Outlet, Link as RouterLink, useLocation, useNavigate } from 'react-router-dom'
import {
  AppBar,
  Box,
  CssBaseline,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Tooltip,
  Typography,
  Divider,
  Collapse,
  Button,
  Menu,
  MenuItem
} from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import HomeIcon from '@mui/icons-material/Home'
import BusinessIcon from '@mui/icons-material/Business'
import AccountTreeIcon from '@mui/icons-material/AccountTree'
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings'
import SpaceDashboardIcon from '@mui/icons-material/SpaceDashboard'
import SummarizeIcon from '@mui/icons-material/Summarize'
import TuneIcon from '@mui/icons-material/Tune'
import PersonIcon from '@mui/icons-material/Person'
import GroupWorkIcon from '@mui/icons-material/GroupWork'
import GridOnIcon from '@mui/icons-material/GridOn'
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents'
import FactCheckIcon from '@mui/icons-material/FactCheck'
import PestControlIcon from '@mui/icons-material/PestControl'
import AutorenewIcon from '@mui/icons-material/Autorenew'
import ScheduleIcon from '@mui/icons-material/Schedule'
import CommitIcon from '@mui/icons-material/Commit'
import DownloadForOfflineIcon from '@mui/icons-material/DownloadForOffline'
import ManageAccountsIcon from '@mui/icons-material/ManageAccounts'
import SecurityIcon from '@mui/icons-material/Security'
import HistoryIcon from '@mui/icons-material/History'
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive'
import ExpandLess from '@mui/icons-material/ExpandLess'
import ExpandMore from '@mui/icons-material/ExpandMore'
import VpnKeyIcon from '@mui/icons-material/VpnKey'
import LogoutIcon from '@mui/icons-material/Logout'
import AccountCircleIcon from '@mui/icons-material/AccountCircle'
import SwitchAccountIcon from '@mui/icons-material/SwitchAccount'
import FeedbackIcon from '@mui/icons-material/Feedback'
import { useAuth } from '../context/AuthContext'
import { appConfigApi } from '../services/appConfigApi'

const drawerWidth = 240

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [dashboardOpen, setDashboardOpen] = useState(true)
  const [reportsOpen, setReportsOpen] = useState(true)
  const [configOpen, setConfigOpen] = useState(true)
  const [userMenuAnchorEl, setUserMenuAnchorEl] = useState<null | HTMLElement>(null)
  const [teamSightVersion, setTeamSightVersion] = useState('0.1.0')
  const location = useLocation()
  const navigate = useNavigate()
  const { user, hasAnyPermission, logout } = useAuth()

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

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen)
  }

  const handleDashboardClick = () => {
    setDashboardOpen(!dashboardOpen)
  }

  const handleReportsClick = () => {
    setReportsOpen(!reportsOpen)
  }

  const handleConfigClick = () => {
    setConfigOpen(!configOpen)
  }

  const handleUserMenuOpen = (event: React.MouseEvent<HTMLButtonElement>) => {
    setUserMenuAnchorEl(event.currentTarget)
  }

  const handleUserMenuClose = () => {
    setUserMenuAnchorEl(null)
  }

  const handleChangePassword = () => {
    handleUserMenuClose()
    navigate('/account/password')
  }

  const handleSwitchUser = () => {
    handleUserMenuClose()
    logout()
    navigate('/login', { replace: true })
  }

  const handleLogout = () => {
    handleUserMenuClose()
    logout()
  }

  const menuItems = [
    { text: 'Home', icon: <HomeIcon />, path: '/' }
  ]

  const userMenuOpen = Boolean(userMenuAnchorEl)

  const canViewEmployeeDashboard = hasAnyPermission([
    'view:own_employee_dashboard',
    'view:team_employee_dashboard',
    'view:managed_employee_dashboard',
    'view:all_dashboards'
  ])

  const canViewTeamDashboard = hasAnyPermission(['view:team_dashboard', 'view:all_dashboards'])
  const canViewScrumDashboard = hasAnyPermission(['view:scrum_dashboard', 'view:all_dashboards'])
  const canViewReports = hasAnyPermission(['view:reports', 'view:all_dashboards'])
  const canViewGitActivity = canViewReports || user?.role === 'Team Manager'
  const canViewConfig = hasAnyPermission(['view:config'])
  const canViewAuditTrail = hasAnyPermission(['view:audit_trail'])
  const canManageUsers = hasAnyPermission(['manage:users'])
  const canManageRoles = hasAnyPermission(['manage:roles'])
  const canViewAdminMenu = hasAnyPermission(['view:admin_menu'])

  const dashboardItems = [
    ...(canViewTeamDashboard ? [{ text: 'Team', icon: <BusinessIcon />, path: '/dashboard/team' }] : []),
    ...(canViewScrumDashboard ? [{ text: 'Scrum', icon: <GroupWorkIcon />, path: '/dashboard/scrum' }] : []),
    ...(canViewEmployeeDashboard ? [{ text: 'Employee', icon: <PersonIcon />, path: '/dashboard/employee' }] : []),
  ]

  const reportItems = [
    ...(canViewReports ? [
      { text: 'Matrix Report', icon: <GridOnIcon />, path: '/reports/matrix' },
      { text: 'Score Report', icon: <EmojiEventsIcon />, path: '/reports/employee-score-comparison' },
      { text: 'JIRA Epic Tree', icon: <AccountTreeIcon />, path: '/reports/jira-epic-tree' },
      { text: 'Role KPI Applicability', icon: <FactCheckIcon />, path: '/reports/role-kpi-applicability' },
      { text: 'Bug Cycle Time', icon: <PestControlIcon />, path: '/reports/bug-cycle-time' },
      { text: 'Replan Tracker', icon: <AutorenewIcon />, path: '/reports/replan-tracker' },
      { text: 'Assignee Delay', icon: <ScheduleIcon />, path: '/reports/assignee-delay' },
      { text: 'UDE Installations', icon: <DownloadForOfflineIcon />, path: '/reports/ude-installations' },
    ] : []),
    ...(canViewGitActivity ? [
      { text: 'Git Activity', icon: <CommitIcon />, path: '/reports/git-activity' },
    ] : []),
  ]

  const configItems = [
    ...(canViewConfig || canManageRoles ? [
      {
        text: 'TeamSight Users & Roles',
        icon: <ManageAccountsIcon />,
        path: '/config/teamsight',
        selected: location.pathname === '/config/teamsight' || location.pathname === '/employees' || location.pathname === '/roles'
      },
    ] : []),
    ...(canViewConfig || canManageUsers || canManageRoles ? [
      {
        text: 'RBAC Configuration',
        icon: <SecurityIcon />,
        path: '/config/rbac',
        selected: location.pathname === '/config/rbac' || location.pathname === '/config/users' || location.pathname === '/config/custom-roles'
      },
    ] : []),
    ...(canViewConfig || canManageUsers ? [
      {
        text: 'Notifications',
        icon: <NotificationsActiveIcon />,
        path: '/config/notifications',
        selected: location.pathname === '/config/notifications'
      },
    ] : []),
  ]

  const drawer = (
    <Box>
      <Toolbar>
        <Box>
          <Typography variant="h6" noWrap>
            TeamSight
          </Typography>
          <Typography variant="caption" color="text.secondary">
            v{teamSightVersion}
          </Typography>
        </Box>
      </Toolbar>
      <Divider />
      <List>
        {menuItems.map((item) => (
          <ListItem key={item.text} disablePadding>
            <ListItemButton
              component={RouterLink}
              to={item.path}
              selected={location.pathname === item.path}
            >
              <ListItemIcon>
                {item.icon}
              </ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
        
        {dashboardItems.length > 0 && (
          <>
            <ListItem disablePadding>
              <ListItemButton onClick={handleDashboardClick}>
                <ListItemIcon>
                  <SpaceDashboardIcon />
                </ListItemIcon>
                <ListItemText primary="Dashboards" />
                {dashboardOpen ? <ExpandLess /> : <ExpandMore />}
              </ListItemButton>
            </ListItem>
            <Collapse in={dashboardOpen} timeout="auto" unmountOnExit>
              <List component="div" disablePadding>
                {dashboardItems.map((item) => (
                  <ListItem key={item.text} disablePadding>
                    <ListItemButton
                      component={RouterLink}
                      to={item.path}
                      selected={location.pathname === item.path}
                      sx={{ pl: 4 }}
                    >
                      <ListItemIcon>
                        {item.icon}
                      </ListItemIcon>
                      <ListItemText primary={item.text} />
                    </ListItemButton>
                  </ListItem>
                ))}
              </List>
            </Collapse>
          </>
        )}
        
        {reportItems.length > 0 && (
          <>
            <ListItem disablePadding>
              <ListItemButton onClick={handleReportsClick}>
                <ListItemIcon>
                  <SummarizeIcon />
                </ListItemIcon>
                <ListItemText primary="Reports" />
                {reportsOpen ? <ExpandLess /> : <ExpandMore />}
              </ListItemButton>
            </ListItem>
            <Collapse in={reportsOpen} timeout="auto" unmountOnExit>
              <List component="div" disablePadding>
                {reportItems.map((item) => (
                  <ListItem key={item.text} disablePadding>
                    <ListItemButton
                      component={RouterLink}
                      to={item.path}
                      selected={location.pathname === item.path}
                      sx={{ pl: 4 }}
                    >
                      <ListItemIcon>
                        {item.icon}
                      </ListItemIcon>
                      <ListItemText primary={item.text} />
                    </ListItemButton>
                  </ListItem>
                ))}
              </List>
            </Collapse>
          </>
        )}
      </List>
      <Divider />
      <List>
        {configItems.length > 0 && (
          <>
            <ListItem disablePadding>
              <ListItemButton onClick={handleConfigClick}>
                <ListItemIcon>
                  <TuneIcon />
                </ListItemIcon>
                <ListItemText primary="Configuration" />
                {configOpen ? <ExpandLess /> : <ExpandMore />}
              </ListItemButton>
            </ListItem>
            <Collapse in={configOpen} timeout="auto" unmountOnExit>
              <List component="div" disablePadding>
                {configItems.map((item) => (
                  <ListItem key={item.text} disablePadding>
                    <ListItemButton
                      component={RouterLink}
                      to={item.path}
                      selected={item.selected}
                      sx={{ pl: 4 }}
                    >
                      <ListItemIcon>
                        {item.icon}
                      </ListItemIcon>
                      <ListItemText primary={item.text} />
                    </ListItemButton>
                  </ListItem>
                ))}
              </List>
            </Collapse>
          </>
        )}

        {canViewAuditTrail && (
          <ListItem disablePadding>
            <ListItemButton
              component={RouterLink}
              to="/config/audit-trail"
              selected={location.pathname === '/config/audit-trail'}
            >
              <ListItemIcon>
                <HistoryIcon />
              </ListItemIcon>
              <ListItemText primary="Audit Trail" />
            </ListItemButton>
          </ListItem>
        )}

        {canViewAdminMenu && (
          <ListItem disablePadding>
            <ListItemButton
              component={RouterLink}
              to="/admin"
              selected={location.pathname === '/admin'}
            >
              <ListItemIcon>
                <AdminPanelSettingsIcon />
              </ListItemIcon>
              <ListItemText primary="System Admin" />
            </ListItemButton>
          </ListItem>
        )}
      </List>
    </Box>
  )

  return (
    <Box sx={{ display: 'flex' }}>
      <CssBaseline />
      <AppBar
        position="fixed"
        sx={{
          width: { sm: `calc(100% - ${drawerWidth}px)` },
          ml: { sm: `${drawerWidth}px` }
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { sm: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap component="div">
            Employee Metrics Dashboard
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
          <Tooltip title="Report Issue">
            <IconButton
              color="inherit"
              href="https://forms.gle/22ArwUAvVhnonYYe6"
              target="_blank"
              rel="noopener noreferrer"
              sx={{ mr: 1 }}
            >
              <FeedbackIcon />
            </IconButton>
          </Tooltip>
          <Button
            color="inherit"
            startIcon={<AccountCircleIcon />}
            onClick={handleUserMenuOpen}
          >
            {user?.name} ({user?.role})
          </Button>
          <Menu
            anchorEl={userMenuAnchorEl}
            open={userMenuOpen}
            onClose={handleUserMenuClose}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          >
            <MenuItem onClick={handleChangePassword}>
              <ListItemIcon>
                <VpnKeyIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>Change Password</ListItemText>
            </MenuItem>
            <MenuItem onClick={handleSwitchUser}>
              <ListItemIcon>
                <SwitchAccountIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>Switch User</ListItemText>
            </MenuItem>
            <MenuItem onClick={handleLogout}>
              <ListItemIcon>
                <LogoutIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText>Logout</ListItemText>
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>
      <Box
        component="nav"
        sx={{ width: { sm: drawerWidth }, flexShrink: { sm: 0 } }}
      >
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true
          }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth }
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth }
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { sm: `calc(100% - ${drawerWidth}px)` }
        }}
      >
        <Toolbar />
        <Outlet />
      </Box>
    </Box>
  )
}
