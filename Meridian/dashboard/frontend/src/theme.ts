import { createTheme } from '@mui/material/styles'

const theme = createTheme({
  palette: {
    primary: {
      main: '#1976D2', // Blue
      light: '#42A5F5',
      dark: '#1565C0',
    },
    secondary: {
      main: '#9C27B0', // Purple
      light: '#BA68C8',
      dark: '#7B1FA2',
    },
    success: {
      main: '#66BB6A', // Green for ROG Green
      light: '#81C784',
      dark: '#4CAF50',
    },
    warning: {
      main: '#FFA726', // Orange for ROG Orange
      light: '#FFB74D',
      dark: '#F57C00',
    },
    error: {
      main: '#EF5350', // Red for ROG Red
      light: '#E57373',
      dark: '#D32F2F',
    },
    background: {
      default: '#F5F5F5',
      paper: '#FFFFFF',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h4: {
      fontWeight: 600,
    },
    h5: {
      fontWeight: 500,
    },
    h6: {
      fontWeight: 500,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        },
      },
    },
  },
})

export default theme
