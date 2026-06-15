import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Dialog,
  Drawer,
  Divider,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  MenuItem,
  Typography,
  IconButton
} from '@mui/material'
import { useTheme } from '@mui/material/styles'
import RefreshIcon from '@mui/icons-material/Refresh'
import AccountTreeIcon from '@mui/icons-material/AccountTree'
import KeyboardArrowRightIcon from '@mui/icons-material/KeyboardArrowRight'
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown'
import CloseIcon from '@mui/icons-material/Close'
import InsightsIcon from '@mui/icons-material/Insights'
import VisibilityIcon from '@mui/icons-material/Visibility'
import ZoomInIcon from '@mui/icons-material/ZoomIn'
import ZoomOutIcon from '@mui/icons-material/ZoomOut'
import RestartAltIcon from '@mui/icons-material/RestartAlt'
import { DataSet, Network } from 'vis-network/standalone'
import {
  Brush,
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'
import {
  JiraEpicListItem,
  JiraEpicTreeNode,
  JiraEpicsListResponse,
  JiraEpicDetailsResponse,
  JiraEpicChildTiming,
  JiraIssueTransitionsResponse,
  reportsApi
} from '../services/reportsApi'

type FilterOptions = JiraEpicsListResponse['filters']

type FlatTreeRow = {
  node: JiraEpicTreeNode
  level: number
}

type HierarchyGraphNode = {
  key: string
  parent: string | null
  issueType: string
  assignee: string
  status: string
  delayDays: number
  level: number
}

const MAX_HIERARCHY_GRAPH_NODES = 220
const MAX_PLANNED_CHART_ROWS = 120
const DEFAULT_PLANNED_CHART_WINDOW = 24
const DEFAULT_EPICS_PAGE_SIZE = 25
const EPIC_PAGE_SIZE_OPTIONS = [10, 25, 50]

const emptyFilterOptions: FilterOptions = {
  teams: [],
  states: [],
  sprints: [],
  assignees: [],
  components: []
}

function statusChipColor(status: string): 'default' | 'success' | 'warning' | 'info' {
  const normalized = status.trim().toLowerCase()

  if (['done', 'closed', 'resolved', 'completed'].includes(normalized)) {
    return 'success'
  }

  if (['in progress', 'approved', 'code review', 'review', 'testing', 'in test'].includes(normalized)) {
    return 'warning'
  }

  if (['new', 'to do', 'open', 'backlog'].includes(normalized)) {
    return 'info'
  }

  return 'default'
}

function delayChipColor(delayDays: number): 'success' | 'warning' | 'error' {
  if (delayDays >= 7) {
    return 'error'
  }

  if (delayDays > 0) {
    return 'warning'
  }

  return 'success'
}

function formatDateAsYyyyMmDd(value: string): string {
  const rawValue = String(value || '').trim()
  if (!rawValue) {
    return 'NA'
  }

  const isoPrefixMatch = rawValue.match(/^(\d{4}-\d{2}-\d{2})/)
  if (isoPrefixMatch) {
    return isoPrefixMatch[1]
  }

  const parsedDate = new Date(rawValue)
  if (Number.isNaN(parsedDate.getTime())) {
    return rawValue
  }

  return parsedDate.toISOString().slice(0, 10)
}

function formatDelayInDays(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'NA'
  }

  if (value < 0) {
    return 'NA'
  }

  return value.toFixed(1)
}

function formatDelayWithUnit(value: number | null | undefined): string {
  const formattedDelay = formatDelayInDays(value)
  if (formattedDelay === 'NA') {
    return 'NA'
  }

  return `${formattedDelay}d`
}

function formatPlanningDelayInDays(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'NA'
  }

  if (value < 0) {
    return 'NA'
  }

  return value.toFixed(1)
}

export default function JiraEpicHierarchyReportPage() {
  const theme = useTheme()
  const [searchParams] = useSearchParams()

  const [epics, setEpics] = useState<JiraEpicListItem[]>([])
  const [filterOptions, setFilterOptions] = useState<FilterOptions>(emptyFilterOptions)
  const [selectedEpicKey, setSelectedEpicKey] = useState('')
  const [selectedEpicDetails, setSelectedEpicDetails] = useState<JiraEpicDetailsResponse | null>(null)
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({})
  const [focusedIssueKey, setFocusedIssueKey] = useState('')
  const [pendingScrollIssueKey, setPendingScrollIssueKey] = useState('')
  const [hierarchyZoomLevel, setHierarchyZoomLevel] = useState(1)
  const [plannedChartRange, setPlannedChartRange] = useState({
    startIndex: 0,
    endIndex: DEFAULT_PLANNED_CHART_WINDOW
  })
  const [insightsViewMode, setInsightsViewMode] = useState<'full' | 'split'>('split')
  const [insightsDrawerOpen, setInsightsDrawerOpen] = useState(false)
  const [issueHistoryDialogOpen, setIssueHistoryDialogOpen] = useState(false)
  const [selectedTransitionIssueKey, setSelectedTransitionIssueKey] = useState('')
  const [issueTransitionsDetails, setIssueTransitionsDetails] = useState<JiraIssueTransitionsResponse | null>(null)
  const [loadingIssueTransitions, setLoadingIssueTransitions] = useState(false)
  const [issueTransitionsError, setIssueTransitionsError] = useState<string | null>(null)
  const treeRowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const hierarchyNetworkContainerRef = useRef<HTMLDivElement | null>(null)
  const hierarchyNetworkRef = useRef<Network | null>(null)
  const pendingOpenInsightsRef = useRef(false)

  const [teamFilter, setTeamFilter] = useState('')
  const [stateFilter, setStateFilter] = useState('')
  const [sprintFilter, setSprintFilter] = useState('')
  const [assigneeFilter, setAssigneeFilter] = useState('')
  const [componentFilter, setComponentFilter] = useState('')
  const [searchFilter, setSearchFilter] = useState('')
  const [epicPage, setEpicPage] = useState(0)
  const [epicPageSize, setEpicPageSize] = useState(DEFAULT_EPICS_PAGE_SIZE)
  const [totalEpics, setTotalEpics] = useState(0)
  const [availableTeams, setAvailableTeams] = useState<string[]>([])

  const [loadingEpics, setLoadingEpics] = useState(true)
  const [loadingEpicDetails, setLoadingEpicDetails] = useState(false)
  const [epicsError, setEpicsError] = useState<string | null>(null)
  const [detailsError, setDetailsError] = useState<string | null>(null)

  // Pre-select an epic when navigated here via ?epic=<key>&insights=true
  useEffect(() => {
    const epicParam = searchParams.get('epic')
    const openInsights = searchParams.get('insights') === 'true'
    if (epicParam) {
      pendingOpenInsightsRef.current = openInsights
      setSelectedEpicKey(epicParam)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadEpics()
  }, [teamFilter, stateFilter, sprintFilter, assigneeFilter, componentFilter, searchFilter, epicPage, epicPageSize])

  useEffect(() => {
    if (!selectedEpicKey) {
      setSelectedEpicDetails(null)
      setExpandedNodes({})
      setFocusedIssueKey('')
      setPendingScrollIssueKey('')
      setIssueHistoryDialogOpen(false)
      setSelectedTransitionIssueKey('')
      setIssueTransitionsDetails(null)
      setIssueTransitionsError(null)
      setHierarchyZoomLevel(1)
      setPlannedChartRange({ startIndex: 0, endIndex: DEFAULT_PLANNED_CHART_WINDOW })
      setInsightsViewMode('split')
      setInsightsDrawerOpen(false)
      return
    }

    setSelectedEpicDetails(null)
    setExpandedNodes({})
    setFocusedIssueKey('')
    setPendingScrollIssueKey('')
    setIssueHistoryDialogOpen(false)
    setSelectedTransitionIssueKey('')
    setIssueTransitionsDetails(null)
    setIssueTransitionsError(null)
    setHierarchyZoomLevel(1)
    setPlannedChartRange({ startIndex: 0, endIndex: DEFAULT_PLANNED_CHART_WINDOW })
    setInsightsViewMode('split')
    setDetailsError(null)

    // Auto-open insights workspace when navigated here via ?insights=true
    if (pendingOpenInsightsRef.current) {
      pendingOpenInsightsRef.current = false
      setInsightsDrawerOpen(true)
      loadEpicDetails(selectedEpicKey)
    }
  }, [selectedEpicKey])

  const treeRows = useMemo<FlatTreeRow[]>(() => {
    if (!selectedEpicDetails?.tree) {
      return []
    }

    const rows: FlatTreeRow[] = []

    const flatten = (node: JiraEpicTreeNode, level: number) => {
      rows.push({ node, level })

      if (!expandedNodes[node.key]) {
        return
      }

      node.children.forEach((child) => flatten(child, level + 1))
    }

    flatten(selectedEpicDetails.tree, 0)
    return rows
  }, [selectedEpicDetails, expandedNodes])

  const parentByIssueKey = useMemo<Record<string, string | null>>(() => {
    if (!selectedEpicDetails?.tree) {
      return {}
    }

    const parentMap: Record<string, string | null> = {}

    const walkTree = (node: JiraEpicTreeNode, parentKey: string | null) => {
      parentMap[node.key] = parentKey
      node.children.forEach((childNode) => walkTree(childNode, node.key))
    }

    walkTree(selectedEpicDetails.tree, null)
    return parentMap
  }, [selectedEpicDetails])

  useEffect(() => {
    if (!pendingScrollIssueKey) {
      return
    }

    const rowElement = treeRowRefs.current[pendingScrollIssueKey]
    if (!rowElement) {
      return
    }

    rowElement.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setPendingScrollIssueKey('')
  }, [pendingScrollIssueKey, treeRows])

  const childTimingChartData = useMemo(() => {
    if (!selectedEpicDetails?.analysis.child_timing) {
      return []
    }

    return [...selectedEpicDetails.analysis.child_timing]
      .sort((firstIssue: JiraEpicChildTiming, secondIssue: JiraEpicChildTiming) => {
        const secondSlippage = secondIssue.slippage_days ?? Number.NEGATIVE_INFINITY
        const firstSlippage = firstIssue.slippage_days ?? Number.NEGATIVE_INFINITY
        return secondSlippage - firstSlippage
      })
      .slice(0, MAX_PLANNED_CHART_ROWS)
      .map((issue) => ({
        key: issue.key,
        planned_days: issue.planned_days ?? 0,
        actual_days: issue.actual_days ?? 0,
        slippage_days: issue.slippage_days ?? 0
      }))
  }, [selectedEpicDetails])

  useEffect(() => {
    const maxIndex = Math.max(0, childTimingChartData.length - 1)
    const defaultEndIndex = Math.min(maxIndex, DEFAULT_PLANNED_CHART_WINDOW)

    setPlannedChartRange({
      startIndex: 0,
      endIndex: defaultEndIndex
    })
  }, [childTimingChartData.length, selectedEpicKey])

  const hierarchyDelayGraph = useMemo(() => {
    if (!selectedEpicDetails?.tree) {
      return null
    }

    const countNodes = (node: JiraEpicTreeNode): number => (
      1 + node.children.reduce((count, child) => count + countNodes(child), 0)
    )

    const totalNodes = countNodes(selectedEpicDetails.tree)
    const traversalQueue: Array<{ node: JiraEpicTreeNode, parentKey: string | null, level: number }> = [
      { node: selectedEpicDetails.tree, parentKey: null, level: 0 }
    ]
    const graphNodes: HierarchyGraphNode[] = []

    while (traversalQueue.length > 0 && graphNodes.length < MAX_HIERARCHY_GRAPH_NODES) {
      const current = traversalQueue.shift()
      if (!current) {
        continue
      }

      graphNodes.push({
        key: current.node.key,
        parent: current.parentKey,
        issueType: current.node.issue_type,
        assignee: current.node.assignee,
        status: current.node.status,
        delayDays: current.node.delay_days,
        level: current.level
      })

      const sortedChildren = [...current.node.children]
        .sort((firstChild, secondChild) => secondChild.delay_days - firstChild.delay_days)

      sortedChildren.forEach((child) => {
        traversalQueue.push({
          node: child,
          parentKey: current.node.key,
          level: current.level + 1
        })
      })
    }

    const delayColor = (delayValue: number): string => {
      if (delayValue >= 7) {
        return theme.palette.error.main
      }

      if (delayValue > 0) {
        return theme.palette.warning.main
      }

      return theme.palette.success.main
    }

    const nodesByKey = new Map(graphNodes.map((node) => [node.key, node]))

    const layoutProfile = (() => {
      if (graphNodes.length >= 180) {
        return {
          compactLabels: true,
          levelSeparation: 300,
          nodeSpacing: 210,
          treeSpacing: 290,
          maxNodeWidth: 210,
          nodeFontSize: 10,
          edgeFontSize: 9,
          initialScale: 0.82,
          minScale: 0.72
        }
      }

      if (graphNodes.length >= 120) {
        return {
          compactLabels: false,
          levelSeparation: 270,
          nodeSpacing: 175,
          treeSpacing: 255,
          maxNodeWidth: 250,
          nodeFontSize: 11,
          edgeFontSize: 10,
          initialScale: 0.9,
          minScale: 0.78
        }
      }

      return {
        compactLabels: false,
        levelSeparation: 230,
        nodeSpacing: 145,
        treeSpacing: 220,
        maxNodeWidth: 290,
        nodeFontSize: 12,
        edgeFontSize: 11,
        initialScale: 1,
        minScale: 0.86
      }
    })()

    const formatAssigneeForNode = (assigneeName: string): string => {
      if (layoutProfile.compactLabels) {
        return ''
      }

      if (assigneeName.length <= 18) {
        return assigneeName
      }

      return `${assigneeName.slice(0, 15)}...`
    }

    const createTooltipContent = (lines: string[]) => {
      if (typeof document === 'undefined') {
        return lines.join('\n')
      }

      const tooltipElement = document.createElement('div')
      lines.forEach((lineText, lineIndex) => {
        const rowElement = document.createElement('div')
        rowElement.textContent = lineText
        if (lineIndex === 0) {
          rowElement.style.fontWeight = '600'
        }
        tooltipElement.appendChild(rowElement)
      })

      return tooltipElement
    }

    const nodes = graphNodes.map((node) => {
      const assigneeText = node.assignee || 'Unassigned'
      const labelAssignee = formatAssigneeForNode(assigneeText)

      return {
        id: node.key,
        label: labelAssignee ? `${node.key}\n${labelAssignee}` : node.key,
        level: node.level,
        shape: 'box',
        title: createTooltipContent([
          node.key,
          `Type: ${node.issueType}`,
          `Assignee: ${assigneeText}`,
          `Status: ${node.status}`,
          `Cumulative Delay: ${node.delayDays.toFixed(1)}d`
        ]),
        color: {
          background: delayColor(node.delayDays),
          border: theme.palette.divider,
          highlight: {
            background: delayColor(node.delayDays),
            border: theme.palette.primary.main
          },
          hover: {
            background: delayColor(node.delayDays),
            border: theme.palette.primary.main
          }
        },
        font: {
          color: theme.palette.text.primary,
          size: layoutProfile.nodeFontSize
        }
      }
    })

    const edges = graphNodes
      .filter((node) => node.parent && nodesByKey.has(node.parent))
      .map((node) => {
        const parentKey = node.parent as string
        const parentNode = nodesByKey.get(parentKey)
        const parentDelay = parentNode?.delayDays ?? 0
        const legDelay = Number((node.delayDays - parentDelay).toFixed(2))

        return {
          id: `${parentKey}-${node.key}`,
          from: parentKey,
          to: node.key,
          label: `${legDelay.toFixed(1)}d`,
          title: createTooltipContent([
            `${parentKey} → ${node.key}`,
            `Leg Delay: ${legDelay.toFixed(1)}d`
          ]),
          arrows: 'to',
          smooth: {
            enabled: true,
            type: 'cubicBezier',
            roundness: 0.2
          },
          width: Math.min(5, 1.4 + Math.abs(legDelay) / 6),
          color: {
            color: delayColor(legDelay),
            highlight: theme.palette.primary.main,
            hover: theme.palette.primary.main,
            inherit: false
          },
          font: {
            align: 'middle',
            color: theme.palette.text.secondary,
            strokeWidth: 4,
            strokeColor: theme.palette.background.paper,
            size: layoutProfile.edgeFontSize
          }
        }
      })

    return {
      nodes,
      edges,
      shownNodes: graphNodes.length,
      totalNodes,
      truncated: graphNodes.length < totalNodes,
      layoutProfile
    }
  }, [selectedEpicDetails, theme])

  const loadEpics = async () => {
    setLoadingEpics(true)
    setEpicsError(null)

    try {
      const response = await reportsApi.getJiraEpics({
        team: teamFilter || undefined,
        state: stateFilter || undefined,
        sprint: sprintFilter || undefined,
        assignee: assigneeFilter || undefined,
        component: componentFilter || undefined,
        search: searchFilter || undefined,
        page: epicPage + 1,
        page_size: epicPageSize
      })

      setEpics(response.data)
      setFilterOptions(response.filters)
      setAvailableTeams(response.available_teams || [])
      setTotalEpics(response.pagination?.total_items ?? response.total_epics ?? response.data.length)

      const resolvedPageIndex = Math.max(0, (response.pagination?.page ?? (epicPage + 1)) - 1)
      if (resolvedPageIndex !== epicPage) {
        setEpicPage(resolvedPageIndex)
      }

      // Clear team filter if it's no longer in available teams
      if (teamFilter && response.available_teams && !response.available_teams.includes(teamFilter)) {
        setTeamFilter('')
      }

      if (componentFilter && response.filters?.components && !response.filters.components.includes(componentFilter)) {
        setComponentFilter('')
      }

      const hasCurrentSelection = response.data.some((epic) => epic.epic_key === selectedEpicKey)
      const nextSelectedKey = hasCurrentSelection
        ? selectedEpicKey
        : (response.data[0]?.epic_key ?? '')

      setSelectedEpicKey(nextSelectedKey)
    } catch (err: any) {
      setEpicsError(err.response?.data?.detail || 'Failed to load JIRA epic report data')
      setEpics([])
      setTotalEpics(0)
      setSelectedEpicKey('')
      setSelectedEpicDetails(null)
      setFilterOptions(emptyFilterOptions)
      setAvailableTeams([])
    } finally {
      setLoadingEpics(false)
    }
  }

  const loadEpicDetails = async (epicKey: string) => {
    setLoadingEpicDetails(true)
    setDetailsError(null)
    setSelectedEpicDetails(null)
    setIssueHistoryDialogOpen(false)
    setSelectedTransitionIssueKey('')
    setIssueTransitionsDetails(null)
    setIssueTransitionsError(null)
    setHierarchyZoomLevel(1)

    try {
      const response = await reportsApi.getJiraEpicDetails(epicKey)
      setSelectedEpicDetails(response)
      setExpandedNodes({ [response.tree.key]: true })
    } catch (err: any) {
      setDetailsError(err.response?.data?.detail || `Failed to load details for epic ${epicKey}`)
      setSelectedEpicDetails(null)
      setExpandedNodes({})
    } finally {
      setLoadingEpicDetails(false)
    }
  }

  const openInsightsDrawerForEpic = (epicKey: string) => {
    setFocusedIssueKey('')
    setPendingScrollIssueKey('')
    setIssueHistoryDialogOpen(false)
    setSelectedTransitionIssueKey('')
    setIssueTransitionsDetails(null)
    setIssueTransitionsError(null)
    setHierarchyZoomLevel(1)
    setInsightsViewMode('split')
    setInsightsDrawerOpen(true)
    setSelectedEpicKey(epicKey)
    // Auto-load the details for the epic being viewed
    loadEpicDetails(epicKey)
  }

  const toggleNode = (nodeKey: string) => {
    setExpandedNodes((prev) => ({
      ...prev,
      [nodeKey]: !prev[nodeKey]
    }))
  }

  const focusIssueInTree = useCallback((issueKey: string) => {
    if (!issueKey) {
      return
    }

    setFocusedIssueKey(issueKey)

    const nodesToExpand: Record<string, boolean> = {}
    let currentIssue: string | null = issueKey

    while (currentIssue) {
      nodesToExpand[currentIssue] = true
      currentIssue = parentByIssueKey[currentIssue] ?? null
    }

    setExpandedNodes((prev) => ({
      ...prev,
      ...nodesToExpand
    }))

    setPendingScrollIssueKey(issueKey)
  }, [parentByIssueKey])

  const loadIssueTransitions = async (issueKey: string) => {
    const selectedIssue = String(issueKey || '').trim()
    if (!selectedIssue) {
      return
    }

    setSelectedTransitionIssueKey(selectedIssue)
    setLoadingIssueTransitions(true)
    setIssueTransitionsError(null)

    try {
      const response = await reportsApi.getJiraIssueTransitions(selectedIssue)
      setIssueTransitionsDetails(response)
    } catch (err: any) {
      setIssueTransitionsDetails(null)
      setIssueTransitionsError(err.response?.data?.detail || `Failed to load transitions for ${selectedIssue}`)
    } finally {
      setLoadingIssueTransitions(false)
    }
  }

  const handleSyncPaneRowClick = (issueKey: string) => {
    focusIssueInTree(issueKey)
    loadIssueTransitions(issueKey)
    setIssueHistoryDialogOpen(true)
  }

  const handleChildDurationBarClick = (chartEntry: unknown) => {
    if (!chartEntry || typeof chartEntry !== 'object') {
      return
    }

    const payload = (chartEntry as { payload?: { key?: unknown } }).payload
    const clickedIssueKey = typeof payload?.key === 'string' ? payload.key.trim() : ''
    if (!clickedIssueKey) {
      return
    }

    handleSyncPaneRowClick(clickedIssueKey)
  }

  useEffect(() => {
    if (!insightsDrawerOpen || !hierarchyDelayGraph || !hierarchyNetworkContainerRef.current) {
      return
    }

    const { layoutProfile } = hierarchyDelayGraph

    const hierarchyNetwork = new Network(
      hierarchyNetworkContainerRef.current,
      {
        nodes: new DataSet(hierarchyDelayGraph.nodes),
        edges: new DataSet(hierarchyDelayGraph.edges)
      },
      {
        layout: {
          hierarchical: {
            enabled: true,
            direction: 'LR',
            sortMethod: 'directed',
            levelSeparation: layoutProfile.levelSeparation,
            nodeSpacing: layoutProfile.nodeSpacing,
            treeSpacing: layoutProfile.treeSpacing,
            blockShifting: true,
            edgeMinimization: true,
            parentCentralization: true
          }
        },
        interaction: {
          hover: true,
          tooltipDelay: 80,
          navigationButtons: true,
          keyboard: {
            enabled: true,
            bindToWindow: false
          },
          dragView: true,
          zoomView: true
        },
        nodes: {
          shape: 'box',
          borderWidth: 1.3,
          margin: {
            top: 10,
            right: 12,
            bottom: 10,
            left: 12
          },
          widthConstraint: {
            maximum: layoutProfile.maxNodeWidth
          },
          font: {
            face: 'Arial',
            size: layoutProfile.nodeFontSize,
            multi: 'html'
          }
        },
        edges: {
          smooth: {
            enabled: true,
            type: 'cubicBezier',
            roundness: 0.2
          },
          arrows: {
            to: {
              enabled: true,
              scaleFactor: 0.6
            }
          },
          font: {
            align: 'middle',
            size: layoutProfile.edgeFontSize,
            strokeWidth: 4,
            strokeColor: theme.palette.background.paper
          }
        },
        physics: false
      }
    )

    hierarchyNetworkRef.current = hierarchyNetwork
    hierarchyNetwork.fit({
      animation: {
        duration: 220,
        easingFunction: 'easeInOutQuad'
      }
    })

    setHierarchyZoomLevel(Number(hierarchyNetwork.getScale().toFixed(2)))

    const refitHierarchyGraph = () => {
      const graphContainer = hierarchyNetworkContainerRef.current
      if (!graphContainer) {
        return
      }

      if (graphContainer.clientWidth <= 0 || graphContainer.clientHeight <= 0) {
        return
      }

      hierarchyNetwork.redraw()
      hierarchyNetwork.fit({
        animation: false
      })
      setHierarchyZoomLevel(Number(hierarchyNetwork.getScale().toFixed(2)))
    }

    const animationFrameId = requestAnimationFrame(() => {
      refitHierarchyGraph()
    })

    const delayedRefitTimer = window.setTimeout(() => {
      refitHierarchyGraph()
    }, 280)

    hierarchyNetwork.on('click', (eventParams: any) => {
      const selectedNode = eventParams?.nodes?.[0]
      if (!selectedNode) {
        return
      }

      focusIssueInTree(String(selectedNode))
    })

    hierarchyNetwork.on('zoom', (eventParams: any) => {
      const currentScale = Number(eventParams?.scale ?? hierarchyNetwork.getScale())
      if (!Number.isNaN(currentScale)) {
        setHierarchyZoomLevel(Number(currentScale.toFixed(2)))
      }
    })

    return () => {
      cancelAnimationFrame(animationFrameId)
      window.clearTimeout(delayedRefitTimer)
      hierarchyNetwork.destroy()
      if (hierarchyNetworkRef.current === hierarchyNetwork) {
        hierarchyNetworkRef.current = null
      }
    }
  }, [insightsDrawerOpen, hierarchyDelayGraph, focusIssueInTree, theme])

  useEffect(() => {
    if (!insightsDrawerOpen || !hierarchyNetworkRef.current) {
      return
    }

    const currentPosition = hierarchyNetworkRef.current.getViewPosition()
    const currentScale = hierarchyNetworkRef.current.getScale()

    const animationFrameId = requestAnimationFrame(() => {
      if (!hierarchyNetworkRef.current) {
        return
      }

      hierarchyNetworkRef.current.redraw()
      hierarchyNetworkRef.current.moveTo({
        position: currentPosition,
        scale: currentScale,
        animation: false
      })

      setHierarchyZoomLevel(Number(currentScale.toFixed(2)))
    })

    return () => {
      cancelAnimationFrame(animationFrameId)
    }
  }, [insightsViewMode, insightsDrawerOpen])

  const applyHierarchyZoom = (targetScale: number) => {
    if (!hierarchyNetworkRef.current) {
      return
    }

    const currentViewport = hierarchyNetworkRef.current.getViewPosition()
    hierarchyNetworkRef.current.moveTo({
      position: currentViewport,
      scale: targetScale,
      animation: {
        duration: 180,
        easingFunction: 'easeInOutQuad'
      }
    })

    setHierarchyZoomLevel(Number(targetScale.toFixed(2)))
  }

  const zoomInHierarchyGraph = () => {
    const currentScale = hierarchyNetworkRef.current?.getScale() ?? hierarchyZoomLevel
    const nextScale = Math.min(2.2, Number((currentScale + 0.15).toFixed(2)))
    applyHierarchyZoom(nextScale)
  }

  const zoomOutHierarchyGraph = () => {
    const currentScale = hierarchyNetworkRef.current?.getScale() ?? hierarchyZoomLevel
    const minScale = hierarchyDelayGraph?.layoutProfile.minScale ?? 0.65
    const nextScale = Math.max(minScale, Number((currentScale - 0.15).toFixed(2)))
    applyHierarchyZoom(nextScale)
  }

  const resetHierarchyGraphZoom = () => {
    if (!hierarchyNetworkRef.current) {
      return
    }

    hierarchyNetworkRef.current.fit({
      animation: {
        duration: 220,
        easingFunction: 'easeInOutQuad'
      }
    })

    const nextScale = hierarchyNetworkRef.current.getScale()
    setHierarchyZoomLevel(Number(nextScale.toFixed(2)))
  }

  const isSplitInsightsView = insightsViewMode === 'split'
  const plannedChartHeight = isSplitInsightsView ? 360 : 480
  const hierarchyChartHeight = isSplitInsightsView ? 560 : 680

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <AccountTreeIcon sx={{ fontSize: 32, color: 'primary.main' }} />
              <Typography variant="h4">
                JIRA Epic Tree Report
              </Typography>
            </Box>
            <Typography variant="body2" color="text.secondary">
              Filter epics, then drill down into Stories, Tasks, and Sub-tasks with assignee and delay analysis.
            </Typography>
          </Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            size="small"
            onClick={loadEpics}
            disabled={loadingEpics}
          >
            Refresh
          </Button>
        </Box>

        <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
          <TextField
            select
            label="Team"
            value={teamFilter}
            onChange={(event) => {
              setEpicPage(0)
              setTeamFilter(event.target.value)
            }}
            size="small"
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="">All Teams</MenuItem>
            {availableTeams.length > 0 ? (
              availableTeams.map((team) => (
                <MenuItem key={team} value={team}>{team}</MenuItem>
              ))
            ) : (
              filterOptions.teams.map((team) => (
                <MenuItem key={team} value={team}>{team}</MenuItem>
              ))
            )}
          </TextField>

          <TextField
            select
            label="State"
            value={stateFilter}
            onChange={(event) => {
              setEpicPage(0)
              setStateFilter(event.target.value)
            }}
            size="small"
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="">All States</MenuItem>
            {filterOptions.states.map((state) => (
              <MenuItem key={state} value={state}>{state}</MenuItem>
            ))}
          </TextField>

          <TextField
            select
            label="Sprint"
            value={sprintFilter}
            onChange={(event) => {
              setEpicPage(0)
              setSprintFilter(event.target.value)
            }}
            size="small"
            sx={{ minWidth: 200 }}
          >
            <MenuItem value="">All Sprints</MenuItem>
            {filterOptions.sprints.map((sprint) => (
              <MenuItem key={sprint} value={sprint}>{sprint}</MenuItem>
            ))}
          </TextField>

          <TextField
            select
            label="Assignee"
            value={assigneeFilter}
            onChange={(event) => {
              setEpicPage(0)
              setAssigneeFilter(event.target.value)
            }}
            size="small"
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="">All Assignees</MenuItem>
            {filterOptions.assignees.map((assignee) => (
              <MenuItem key={assignee} value={assignee}>{assignee}</MenuItem>
            ))}
          </TextField>

          <TextField
            select
            label="Component"
            value={componentFilter}
            onChange={(event) => {
              setEpicPage(0)
              setComponentFilter(event.target.value)
            }}
            size="small"
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="">All Components</MenuItem>
            {filterOptions.components.map((component) => (
              <MenuItem key={component} value={component}>{component}</MenuItem>
            ))}
          </TextField>

          <TextField
            label="Search Epic"
            value={searchFilter}
            onChange={(event) => {
              setEpicPage(0)
              setSearchFilter(event.target.value)
            }}
            size="small"
            placeholder="Epic key or summary"
            sx={{ minWidth: 260 }}
          />
        </Stack>

        {epicsError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {epicsError}
          </Alert>
        )}

        {loadingEpics && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 5 }}>
            <CircularProgress />
          </Box>
        )}

        {!loadingEpics && !epicsError && (
          <>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
              <Chip label={`${epics.length} of ${totalEpics} Epics`} color="primary" variant="outlined" />
              {selectedEpicKey && <Chip label={`Selected: ${selectedEpicKey}`} color="secondary" variant="outlined" />}
            </Stack>

            {epics.length > 0 ? (
              <>
                <TableContainer sx={{ maxHeight: 320 }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 110 }}>View</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 110 }}>Epic</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 260 }}>Summary</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 140 }}>Team</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 130 }}>Status</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 180 }}>Sprint</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Open</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Delayed</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Avg Delay (d)</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {epics.map((epic) => (
                        <TableRow
                          key={epic.epic_key}
                          hover
                          selected={epic.epic_key === selectedEpicKey}
                          onClick={() => setSelectedEpicKey(epic.epic_key)}
                          sx={{ cursor: 'pointer' }}
                        >
                          <TableCell>
                            <Button
                              variant="outlined"
                              size="small"
                              startIcon={<VisibilityIcon />}
                              onClick={(event) => {
                                event.stopPropagation()
                                openInsightsDrawerForEpic(epic.epic_key)
                              }}
                            >
                              View
                            </Button>
                          </TableCell>
                          <TableCell>
                            <Chip label={epic.epic_key} size="small" variant="outlined" />
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2">{epic.summary}</Typography>
                          </TableCell>
                          <TableCell>{epic.team}</TableCell>
                          <TableCell>
                            <Chip label={epic.status} size="small" color={statusChipColor(epic.status)} />
                          </TableCell>
                          <TableCell>{epic.sprint}</TableCell>
                          <TableCell align="right">{epic.open_descendants}</TableCell>
                          <TableCell align="right">
                            <Chip
                              label={epic.overdue_descendants}
                              size="small"
                              color={epic.overdue_descendants > 0 ? 'warning' : 'success'}
                              variant="outlined"
                            />
                          </TableCell>
                          <TableCell align="right">{formatDelayInDays(epic.avg_delay_days)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                <TablePagination
                  component="div"
                  count={totalEpics}
                  page={epicPage}
                  onPageChange={(_, nextPage) => setEpicPage(nextPage)}
                  rowsPerPage={epicPageSize}
                  onRowsPerPageChange={(event) => {
                    const nextPageSize = Number.parseInt(event.target.value, 10)
                    setEpicPageSize(nextPageSize)
                    setEpicPage(0)
                  }}
                  rowsPerPageOptions={EPIC_PAGE_SIZE_OPTIONS}
                />
              </>
            ) : (
              <Box sx={{ textAlign: 'center', py: 5 }}>
                <Typography variant="body1" color="text.secondary">
                  No epics match the selected filters
                </Typography>
              </Box>
            )}
          </>
        )}
      </Paper>

      {selectedEpicKey && (
        <Paper sx={{ p: 3 }}>
          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={1.5}
            sx={{ mb: 2, justifyContent: 'space-between', alignItems: { xs: 'stretch', md: 'flex-start' } }}
          >
            <Box>
              <Typography variant="h5" sx={{ mb: 1 }}>
                Selected Epic Analysis
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Tree view for epic {selectedEpicKey}. Click Process Analysis to load the latest hierarchy and delay metrics.
              </Typography>
            </Box>
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{ ml: { md: 'auto' }, justifyContent: 'flex-end', flexWrap: 'wrap' }}
              useFlexGap
            >
              <Button
                variant="contained"
                startIcon={<RefreshIcon />}
                onClick={() => loadEpicDetails(selectedEpicKey)}
                disabled={loadingEpicDetails || !selectedEpicKey}
              >
                Process Analysis
              </Button>
              <Button
                variant="outlined"
                startIcon={<InsightsIcon />}
                onClick={() => {
                  setInsightsViewMode('split')
                  setInsightsDrawerOpen(true)

                  if (!selectedEpicDetails || selectedEpicDetails.epic.key !== selectedEpicKey) {
                    loadEpicDetails(selectedEpicKey)
                  }
                }}
                disabled={!selectedEpicKey}
              >
                Open Insights Workspace
              </Button>
            </Stack>
          </Stack>

          {detailsError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {detailsError}
            </Alert>
          )}

          {loadingEpicDetails && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 5 }}>
              <CircularProgress />
            </Box>
          )}

          {!loadingEpicDetails && !detailsError && !selectedEpicDetails && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Click Process Analysis to load data for epic {selectedEpicKey}.
            </Alert>
          )}

          {!loadingEpicDetails && selectedEpicDetails && (
            <>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 3 }}>
                <Chip label={`Total: ${selectedEpicDetails.analysis.total_related_issues}`} color="primary" variant="outlined" />
                <Chip label={`Done: ${selectedEpicDetails.analysis.done_issues}`} color="success" variant="outlined" />
                <Chip label={`Open: ${selectedEpicDetails.analysis.open_issues}`} color="info" variant="outlined" />
                <Chip
                  label={`Delayed: ${selectedEpicDetails.analysis.delayed_issues}`}
                  color={selectedEpicDetails.analysis.delayed_issues > 0 ? 'warning' : 'success'}
                  variant="outlined"
                />
                <Chip label={`Avg Delay: ${formatDelayWithUnit(selectedEpicDetails.analysis.avg_delay_days)}`} variant="outlined" />
                <Chip label={`Max Delay: ${formatDelayWithUnit(selectedEpicDetails.analysis.max_delay_days)}`} variant="outlined" />
                {focusedIssueKey && <Chip label={`Focused: ${focusedIssueKey}`} color="secondary" variant="outlined" />}
              </Stack>

              <Typography variant="h6" sx={{ mb: 1 }}>Epic Hierarchy Tree</Typography>
              <TableContainer sx={{ maxHeight: 420, mb: 3 }}>
                <Table stickyHeader size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 'bold', minWidth: 130 }}>Issue</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', minWidth: 110 }}>Type</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', minWidth: 300 }}>Summary</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', minWidth: 170 }}>Assignee</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', minWidth: 140 }}>Team</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', minWidth: 130 }}>Status</TableCell>
                      <TableCell sx={{ fontWeight: 'bold', minWidth: 160 }}>Sprint</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }} align="right">Age (d)</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }} align="right">Planning Delay (d)</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }} align="right">Delay (d)</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {treeRows.map(({ node, level }) => {
                      const hasChildren = node.children.length > 0
                      const isExpanded = expandedNodes[node.key]
                      const isFocusedIssue = node.key === focusedIssueKey

                      return (
                        <TableRow
                          key={`${node.key}-${level}`}
                          hover
                          selected={isFocusedIssue}
                          ref={(rowElement) => {
                            treeRowRefs.current[node.key] = rowElement
                          }}
                        >
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center', pl: level * 2 }}>
                              {hasChildren ? (
                                <IconButton size="small" onClick={() => toggleNode(node.key)}>
                                  {isExpanded ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                                </IconButton>
                              ) : (
                                <Box sx={{ width: 34 }} />
                              )}
                              <Typography
                                variant="body2"
                                sx={{
                                  fontWeight: level === 0 ? 700 : 400,
                                  color: isFocusedIssue ? 'primary.main' : 'text.primary'
                                }}
                              >
                                {node.key}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell>{node.issue_type}</TableCell>
                          <TableCell>
                            <Typography variant="body2">{node.summary}</Typography>
                          </TableCell>
                          <TableCell>{node.assignee}</TableCell>
                          <TableCell>{node.team}</TableCell>
                          <TableCell>
                            <Chip label={node.status} size="small" color={statusChipColor(node.status)} />
                          </TableCell>
                          <TableCell>{node.sprint}</TableCell>
                          <TableCell align="right">{node.age_days.toFixed(1)}</TableCell>
                          <TableCell align="right">{formatPlanningDelayInDays(node.slippage_days)}</TableCell>
                          <TableCell align="right">
                            <Chip
                              label={formatDelayInDays(node.delay_days)}
                              size="small"
                              color={node.delay_days >= 0 ? delayChipColor(node.delay_days) : 'default'}
                              variant={node.delay_days > 0 ? 'filled' : 'outlined'}
                            />
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </Paper>
      )}

      <Dialog
        open={insightsDrawerOpen}
        onClose={() => setInsightsDrawerOpen(false)}
        fullScreen
      >
        <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Paper square elevation={0} sx={{ px: { xs: 2, md: 3 }, py: 1.5, borderBottom: 1, borderColor: 'divider' }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
              <Box>
                <Typography variant="h6">Epic Insights Workspace</Typography>
                <Typography variant="body2" color="text.secondary">
                  Large-screen analytics view for planned vs actual, hierarchy delay, and assignee analysis.
                </Typography>
              </Box>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ ml: 'auto', justifyContent: 'flex-end' }}>
                <Button
                  size="small"
                  variant={insightsViewMode === 'full' ? 'contained' : 'outlined'}
                  onClick={() => setInsightsViewMode('full')}
                >
                  Full View
                </Button>
                <Button
                  size="small"
                  variant={insightsViewMode === 'split' ? 'contained' : 'outlined'}
                  onClick={() => setInsightsViewMode('split')}
                >
                  Split View
                </Button>
                <IconButton 
                  size="small" 
                  onClick={() => {
                    setInsightsDrawerOpen(false)
                    setSelectedEpicDetails(null)
                  }}
                >
                  <CloseIcon fontSize="small" />
                </IconButton>
              </Stack>
            </Stack>
          </Paper>

          <Box sx={{ flex: 1, overflow: 'auto', px: { xs: 2, md: 3 }, py: 2.5 }}>
            <Divider sx={{ mb: 2 }} />

            {loadingEpicDetails ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
                <CircularProgress />
              </Box>
            ) : detailsError ? (
              <Alert severity="error">{detailsError}</Alert>
            ) : !selectedEpicDetails ? (
              <Alert severity="info">Select an epic from the report table to view insights.</Alert>
            ) : (
              <>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
                  <Chip
                    label={`Timed Children: ${selectedEpicDetails.analysis.timing_summary?.timed_children ?? 0}`}
                    color="primary"
                    variant="outlined"
                  />
                  <Chip
                    label={`Overrun: ${selectedEpicDetails.analysis.timing_summary?.overrun_children ?? 0}`}
                    color={(selectedEpicDetails.analysis.timing_summary?.overrun_children ?? 0) > 0 ? 'warning' : 'success'}
                    variant="outlined"
                  />
                  <Chip
                    label={`Avg Planned: ${(selectedEpicDetails.analysis.timing_summary?.avg_planned_days ?? 0).toFixed(1)}d`}
                    variant="outlined"
                  />
                  <Chip
                    label={`Avg Actual: ${(selectedEpicDetails.analysis.timing_summary?.avg_actual_days ?? 0).toFixed(1)}d`}
                    variant="outlined"
                  />
                  <Chip
                    label={`Avg Slippage: ${(selectedEpicDetails.analysis.timing_summary?.avg_slippage_days ?? 0).toFixed(1)}d`}
                    variant="outlined"
                  />
                </Stack>

                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: isSplitInsightsView ? { xs: '1fr', lg: '1fr 1.35fr' } : '1fr',
                    gap: 2,
                    mb: 2
                  }}
                >
                  {isSplitInsightsView && (
                    <Paper variant="outlined" sx={{ p: 1.5 }}>
                      <Typography variant="subtitle1" sx={{ mb: 1 }}>Hierarchy Tree (Sync Pane)</Typography>
                      {focusedIssueKey && (
                        <Chip label={`Focused: ${focusedIssueKey}`} color="secondary" variant="outlined" size="small" sx={{ mb: 1 }} />
                      )}
                      <TableContainer sx={{ maxHeight: 980 }}>
                        <Table stickyHeader size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 'bold', minWidth: 130 }}>Issue</TableCell>
                              <TableCell sx={{ fontWeight: 'bold', minWidth: 110 }}>Type</TableCell>
                              <TableCell sx={{ fontWeight: 'bold', minWidth: 170 }}>Assignee</TableCell>
                              <TableCell sx={{ fontWeight: 'bold', minWidth: 130 }}>Status</TableCell>
                              <TableCell sx={{ fontWeight: 'bold' }} align="right">Planning Delay (d)</TableCell>
                              <TableCell sx={{ fontWeight: 'bold' }} align="right">Delay (d)</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {treeRows.map(({ node, level }) => {
                              const hasChildren = node.children.length > 0
                              const isExpanded = expandedNodes[node.key]
                              const isFocusedIssue = node.key === focusedIssueKey

                              return (
                                <TableRow
                                  key={`split-${node.key}-${level}`}
                                  hover
                                  selected={isFocusedIssue}
                                  onClick={() => handleSyncPaneRowClick(node.key)}
                                  sx={{ cursor: 'pointer' }}
                                  ref={(rowElement) => {
                                    treeRowRefs.current[node.key] = rowElement
                                  }}
                                >
                                  <TableCell>
                                    <Box sx={{ display: 'flex', alignItems: 'center', pl: level * 1.5 }}>
                                      {hasChildren ? (
                                        <IconButton
                                          size="small"
                                          onClick={(event) => {
                                            event.stopPropagation()
                                            toggleNode(node.key)
                                          }}
                                        >
                                          {isExpanded ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
                                        </IconButton>
                                      ) : (
                                        <Box sx={{ width: 34 }} />
                                      )}
                                      <Typography
                                        variant="body2"
                                        sx={{ color: isFocusedIssue ? 'primary.main' : 'text.primary' }}
                                      >
                                        {node.key}
                                      </Typography>
                                    </Box>
                                  </TableCell>
                                  <TableCell>{node.issue_type}</TableCell>
                                  <TableCell>{node.assignee}</TableCell>
                                  <TableCell>
                                    <Chip label={node.status} size="small" color={statusChipColor(node.status)} />
                                  </TableCell>
                                  <TableCell align="right">{formatPlanningDelayInDays(node.slippage_days)}</TableCell>
                                  <TableCell align="right">
                                    <Chip
                                      label={formatDelayInDays(node.delay_days)}
                                      size="small"
                                      color={node.delay_days >= 0 ? delayChipColor(node.delay_days) : 'default'}
                                      variant={node.delay_days > 0 ? 'filled' : 'outlined'}
                                    />
                                  </TableCell>
                                </TableRow>
                              )
                            })}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Paper>
                  )}

                  <Box>
                    <Typography variant="subtitle1" sx={{ mb: 1 }}>Planned vs Actual Child Duration</Typography>
                    {childTimingChartData.length > 0 ? (
                      <>
                        <Box sx={{ height: plannedChartHeight, mb: 1.5 }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                              data={childTimingChartData}
                              margin={{ top: 8, right: 16, left: 0, bottom: 88 }}
                            >
                              <CartesianGrid strokeDasharray="3 3" />
                              <XAxis
                                dataKey="key"
                                angle={-32}
                                textAnchor="end"
                                interval={0}
                                height={88}
                                tick={{ fontSize: 11 }}
                              />
                              <YAxis />
                              <Tooltip />
                              <Legend />
                              <Bar
                                dataKey="planned_days"
                                name="Planned Days"
                                fill={theme.palette.primary.main}
                                cursor="pointer"
                                onClick={handleChildDurationBarClick}
                              />
                              <Bar dataKey="actual_days" name="Actual Days" cursor="pointer" onClick={handleChildDurationBarClick}>
                                {childTimingChartData.map((timingItem) => (
                                  <Cell
                                    key={`actual-${timingItem.key}`}
                                    fill={timingItem.actual_days > timingItem.planned_days ? theme.palette.error.main : theme.palette.success.light}
                                  />
                                ))}
                              </Bar>
                              <Brush
                                dataKey="key"
                                startIndex={plannedChartRange.startIndex}
                                endIndex={plannedChartRange.endIndex}
                                onChange={(range) => {
                                  if (
                                    typeof range?.startIndex === 'number'
                                    && typeof range?.endIndex === 'number'
                                  ) {
                                    setPlannedChartRange({
                                      startIndex: range.startIndex,
                                      endIndex: range.endIndex
                                    })
                                  }
                                }}
                                height={28}
                                stroke={theme.palette.primary.main}
                                travellerWidth={10}
                              />
                            </BarChart>
                          </ResponsiveContainer>
                        </Box>

                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                          Zoom using the brush handles. Visible range: {Math.min(plannedChartRange.startIndex + 1, childTimingChartData.length)}-
                          {Math.min(plannedChartRange.endIndex + 1, childTimingChartData.length)} of {childTimingChartData.length} child issues.
                        </Typography>
                      </>
                    ) : (
                      <Alert severity="info" sx={{ mb: 2 }}>
                        No child issues with both planned and actual duration are available for this epic.
                      </Alert>
                    )}

                    {(selectedEpicDetails.analysis.timing_summary?.truncated ?? false) && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                        Showing {selectedEpicDetails.analysis.timing_summary.returned_children} timed child issues out of {selectedEpicDetails.analysis.timing_summary.timed_children}.
                      </Typography>
                    )}

                    <Stack
                      direction={{ xs: 'column', md: 'row' }}
                      spacing={1.2}
                      alignItems={{ xs: 'flex-start', md: 'center' }}
                      justifyContent="space-between"
                      sx={{ mb: 1 }}
                    >
                      <Typography variant="subtitle1">Hierarchy Delay Graph (Epic → Story → Task → Sub-task)</Typography>
                      <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                        <Chip label={`Zoom: ${Math.round(hierarchyZoomLevel * 100)}%`} size="small" variant="outlined" />
                        <Button size="small" variant="outlined" startIcon={<ZoomOutIcon />} onClick={zoomOutHierarchyGraph}>Zoom Out</Button>
                        <Button size="small" variant="outlined" startIcon={<ZoomInIcon />} onClick={zoomInHierarchyGraph}>Zoom In</Button>
                        <Button size="small" variant="outlined" startIcon={<RestartAltIcon />} onClick={resetHierarchyGraphZoom}>Reset</Button>
                      </Stack>
                    </Stack>

                    {hierarchyDelayGraph ? (
                      <Box sx={{ height: hierarchyChartHeight, mb: 1.5, border: 1, borderColor: 'divider', borderRadius: 1, overflow: 'hidden' }}>
                        <Box ref={hierarchyNetworkContainerRef} sx={{ width: '100%', height: '100%' }} />
                      </Box>
                    ) : (
                      <Alert severity="info" sx={{ mb: 2 }}>
                        Hierarchy graph is not available for this epic.
                      </Alert>
                    )}

                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                      Click a node to sync with the tree. Use zoom controls and built-in navigation buttons for dense graphs.
                    </Typography>

                    {(hierarchyDelayGraph?.truncated ?? false) && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                        Showing {hierarchyDelayGraph?.shownNodes ?? 0} of {hierarchyDelayGraph?.totalNodes ?? 0} nodes for readability.
                      </Typography>
                    )}
                  </Box>
                </Box>

                <Typography variant="subtitle1" sx={{ mb: 1 }}>Assignee Delay Analysis</Typography>
                <TableContainer sx={{ maxHeight: 520 }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold' }}>Assignee</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>Team</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Total</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Done</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">In Progress</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">To Do</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Delayed</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Avg Age (d)</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Avg Delay (d)</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Max Delay (d)</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {selectedEpicDetails.analysis.assignee_breakdown.map((assignee) => (
                        <TableRow key={`${assignee.assignee}-${assignee.team}`} hover>
                          <TableCell>{assignee.assignee}</TableCell>
                          <TableCell>{assignee.team}</TableCell>
                          <TableCell align="right">{assignee.total_issues}</TableCell>
                          <TableCell align="right">{assignee.done_issues}</TableCell>
                          <TableCell align="right">{assignee.in_progress_issues}</TableCell>
                          <TableCell align="right">{assignee.todo_issues}</TableCell>
                          <TableCell align="right">
                            <Chip
                              label={assignee.delayed_issues}
                              size="small"
                              color={assignee.delayed_issues > 0 ? 'warning' : 'success'}
                              variant="outlined"
                            />
                          </TableCell>
                          <TableCell align="right">{assignee.avg_age_days.toFixed(1)}</TableCell>
                          <TableCell align="right">{formatDelayInDays(assignee.avg_delay_days)}</TableCell>
                          <TableCell align="right">{formatDelayInDays(assignee.max_delay_days)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </>
            )}
          </Box>
        </Box>
      </Dialog>

      <Drawer
        anchor="right"
        open={issueHistoryDialogOpen}
        onClose={() => setIssueHistoryDialogOpen(false)}
        sx={{ zIndex: (muiTheme) => muiTheme.zIndex.modal + 5 }}
        PaperProps={{
          sx: {
            width: { xs: '100%', md: 720 },
            p: 2.5,
            display: 'flex',
            flexDirection: 'column'
          }
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
            <Typography variant="h6">Issue Transition History</Typography>
            <IconButton size="small" onClick={() => setIssueHistoryDialogOpen(false)}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>

          {selectedTransitionIssueKey && (
            <Chip
              label={`Issue: ${selectedTransitionIssueKey}`}
              color="secondary"
              variant="outlined"
              size="small"
              sx={{ mb: 1.5 }}
            />
          )}

          {loadingIssueTransitions ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
              <CircularProgress size={24} />
            </Box>
          ) : issueTransitionsError ? (
            <Alert severity="error" sx={{ mb: 1 }}>{issueTransitionsError}</Alert>
          ) : issueTransitionsDetails ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
                <Chip label={`Delay: ${formatDelayWithUnit(issueTransitionsDetails.delay_computation.delay_days)}`} size="small" variant="outlined" />
                <Chip label={`Basis: ${issueTransitionsDetails.delay_computation.basis}`} size="small" variant="outlined" />
              </Stack>

              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                {issueTransitionsDetails.delay_computation.formula}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
                Sprint End: {formatDateAsYyyyMmDd(issueTransitionsDetails.delay_computation.sprint_end_date)} | Delay Baseline: {formatDateAsYyyyMmDd(issueTransitionsDetails.delay_computation.delay_baseline_date || issueTransitionsDetails.delay_computation.sprint_end_date)} ({issueTransitionsDetails.delay_computation.delay_baseline_source || 'sprint_end_date'}) | Effective End: {formatDateAsYyyyMmDd(issueTransitionsDetails.delay_computation.effective_end_date)}
              </Typography>

              <Typography variant="subtitle2" sx={{ mb: 0.75 }}>Assignment Timeline</Typography>
              {issueTransitionsDetails.assignee_timeline.length > 0 ? (
                <TableContainer sx={{ maxHeight: 220, mb: 1.5 }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 140 }}>Assignee</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 120 }}>From</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 120 }}>To</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Duration (d)</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Delay Attributed (d)</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {issueTransitionsDetails.assignee_timeline.map((timelineRow, index) => (
                        <TableRow key={`${timelineRow.assignee}-${timelineRow.period_start}-${index}`} hover>
                          <TableCell>{timelineRow.assignee || 'Unassigned'}</TableCell>
                          <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateAsYyyyMmDd(timelineRow.period_start)}</TableCell>
                          <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateAsYyyyMmDd(timelineRow.period_end)}</TableCell>
                          <TableCell align="right">{formatDelayInDays(timelineRow.duration_days)}</TableCell>
                          <TableCell align="right">{formatDelayInDays(timelineRow.delay_days)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Alert severity="info" sx={{ mb: 1.5 }}>No assignee timeline available for this issue.</Alert>
              )}

              <Typography variant="subtitle2" sx={{ mb: 0.75 }}>Transition Events</Typography>

              {issueTransitionsDetails.transitions.length > 0 ? (
                <TableContainer sx={{ flex: 1, minHeight: 0 }}>
                  <Table stickyHeader size="small" sx={{ tableLayout: 'fixed' }}>
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold', width: 130, whiteSpace: 'nowrap' }}>Change Date</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', width: 120, py: 0.75 }} align="right">
                          <Box sx={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.15 }}>
                            <span>Accumulated</span>
                            <span>Delay (d)</span>
                          </Box>
                        </TableCell>
                        <TableCell sx={{ fontWeight: 'bold', width: 110 }}>Field</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>From</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>To</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {issueTransitionsDetails.transitions.map((transition, index) => (
                        <TableRow key={`${transition.change_date}-${transition.field}-${index}`} hover>
                          <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateAsYyyyMmDd(transition.change_date)}</TableCell>
                          <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{formatDelayInDays(transition.accumulated_delay_days)}</TableCell>
                          <TableCell>{transition.field || 'NA'}</TableCell>
                          <TableCell>{transition.from_value || 'NA'}</TableCell>
                          <TableCell>{transition.to_value || 'NA'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Alert severity="info">No transition history found for this issue.</Alert>
              )}
            </Box>
          ) : (
            <Alert severity="info">Click an issue row in the sync pane to view complete transition history and delay computation.</Alert>
          )}
        </Box>
      </Drawer>
    </Container>
  )
}
