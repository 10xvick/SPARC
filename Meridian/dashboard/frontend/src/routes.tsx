import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import HomePage from './pages/HomePage'
import EmployeeManagementPage from './pages/EmployeeManagementPage'
import RoleManagementPage from './pages/RoleManagementPage'
import TeamSightUsersRolesPage from './pages/TeamSightUsersRolesPage'
import RbacConfigurationPage from './pages/RbacConfigurationPage'
import MatrixReportPage from './pages/MatrixReportPage'
import EmployeeScoreComparisonReportPage from './pages/EmployeeScoreComparisonReportPage'
import JiraEpicHierarchyReportPage from './pages/JiraEpicHierarchyReportPage'
import RoleKpiApplicabilityReportPage from './pages/RoleKpiApplicabilityReportPage'
import EmployeeDashboardPage from './pages/EmployeeDashboardPage'
import TeamDashboardPage from './pages/TeamDashboardPage'
import ScrumDashboardPage from './pages/ScrumDashboardPage'
import BugCycleTimeReportPage from './pages/BugCycleTimeReportPage'
import ReplanTrackerPage from './pages/ReplanTrackerPage'
import AssigneeDelayReportPage from './pages/AssigneeDelayReportPage'
import GitActivityReportPage from './pages/GitActivityReportPage'
import UdeInstallationsReportPage from './pages/UdeInstallationsReportPage'
import AdminPage from './pages/AdminPage'
import ProjectOnboardingPage from './pages/ProjectOnboardingPage'
import AboutPage from './pages/AboutPage'
import ScoringLogicPage from './pages/ScoringLogicPage'
import LoginPage from './pages/LoginPage'
import ChangePasswordPage from './pages/ChangePasswordPage'
import UserManagementConfigPage from './pages/UserManagementConfigPage'
import CustomRoleManagementPage from './pages/CustomRoleManagementPage'
import AuditTrailPage from './pages/AuditTrailPage'
import NotificationsConfigurationPage from './pages/NotificationsConfigurationPage'
import NotFoundPage from './pages/NotFoundPage'

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/"
        element={(
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        )}
      >
        <Route index element={<HomePage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="scoring-logic" element={<ScoringLogicPage />} />

        <Route
          path="dashboard/employee"
          element={(
            <ProtectedRoute requiredPermissions={[
              'view:own_employee_dashboard',
              'view:team_employee_dashboard',
              'view:managed_employee_dashboard',
              'view:all_dashboards'
            ]}>
              <EmployeeDashboardPage />
            </ProtectedRoute>
          )}
        />

        <Route
          path="dashboard/team"
          element={(
            <ProtectedRoute requiredPermissions={['view:team_dashboard', 'view:all_dashboards']}>
              <TeamDashboardPage />
            </ProtectedRoute>
          )}
        />

        <Route
          path="dashboard/scrum"
          element={(
            <ProtectedRoute requiredPermissions={['view:scrum_dashboard', 'view:all_dashboards']}>
              <ScrumDashboardPage />
            </ProtectedRoute>
          )}
        />

        <Route
          path="reports/matrix"
          element={(
            <ProtectedRoute requiredPermissions={['view:reports', 'view:all_dashboards']}>
              <MatrixReportPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="reports/employee-score-comparison"
          element={(
            <ProtectedRoute requiredPermissions={['view:reports', 'view:all_dashboards']}>
              <EmployeeScoreComparisonReportPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="reports/jira-epic-tree"
          element={(
            <ProtectedRoute requiredPermissions={['view:reports', 'view:all_dashboards']}>
              <JiraEpicHierarchyReportPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="reports/role-kpi-applicability"
          element={(
            <ProtectedRoute requiredPermissions={['view:reports', 'view:all_dashboards']}>
              <RoleKpiApplicabilityReportPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="reports/bug-cycle-time"
          element={(
            <ProtectedRoute requiredPermissions={['view:reports', 'view:all_dashboards']}>
              <BugCycleTimeReportPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="reports/replan-tracker"
          element={(
            <ProtectedRoute requiredPermissions={['view:reports', 'view:all_dashboards']}>
              <ReplanTrackerPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="reports/assignee-delay"
          element={(
            <ProtectedRoute requiredPermissions={['view:reports', 'view:all_dashboards']}>
              <AssigneeDelayReportPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="reports/git-activity"
          element={(
            <ProtectedRoute requiredPermissions={['view:reports', 'view:all_dashboards']} allowedRoles={['Team Manager']}>
              <GitActivityReportPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="reports/ude-installations"
          element={(
            <ProtectedRoute requiredPermissions={['view:reports', 'view:all_dashboards']}>
              <UdeInstallationsReportPage />
            </ProtectedRoute>
          )}
        />

        <Route
          path="employees"
          element={(
            <ProtectedRoute requiredPermissions={['view:config']}>
              <EmployeeManagementPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="roles"
          element={(
            <ProtectedRoute requiredPermissions={['view:config']}>
              <RoleManagementPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="config"
          element={(
            <ProtectedRoute requiredPermissions={['view:config', 'manage:users', 'manage:roles']}>
              <Navigate to="/config/teamsight" replace />
            </ProtectedRoute>
          )}
        />
        <Route
          path="config/teamsight"
          element={(
            <ProtectedRoute requiredPermissions={['view:config', 'manage:roles']}>
              <TeamSightUsersRolesPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="config/rbac"
          element={(
            <ProtectedRoute requiredPermissions={['view:config', 'manage:users', 'manage:roles']}>
              <RbacConfigurationPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="config/users"
          element={(
            <ProtectedRoute requiredPermissions={['manage:users']}>
              <UserManagementConfigPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="config/custom-roles"
          element={(
            <ProtectedRoute requiredPermissions={['manage:roles']}>
              <CustomRoleManagementPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="config/audit-trail"
          element={(
            <ProtectedRoute requiredPermissions={['view:audit_trail']}>
              <AuditTrailPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="config/notifications"
          element={(
            <ProtectedRoute requiredPermissions={['view:config', 'manage:users']}>
              <NotificationsConfigurationPage />
            </ProtectedRoute>
          )}
        />

        <Route
          path="admin"
          element={(
            <ProtectedRoute requiredPermissions={['view:admin_menu']}>
              <AdminPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="admin/project-onboarding"
          element={(
            <ProtectedRoute requiredPermissions={['view:admin_menu']}>
              <ProjectOnboardingPage />
            </ProtectedRoute>
          )}
        />
        <Route
          path="account/password"
          element={(
            <ProtectedRoute>
              <ChangePasswordPage />
            </ProtectedRoute>
          )}
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

export default AppRoutes
