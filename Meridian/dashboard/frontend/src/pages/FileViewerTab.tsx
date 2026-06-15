import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Alert,
  Tabs,
  Tab,
  IconButton,
  Tooltip,
  Divider,
  Chip,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  OpenInNew as OpenInNewIcon,
  FolderOpen as FolderIcon,
  TableChart as TableChartIcon,
  BugReport as ScanIcon,
  Description as LogIcon,
  PictureAsPdf as PdfIcon,
  Code as HtmlIcon,
  SwapHoriz as EquivalentIcon,
} from '@mui/icons-material';
import axios from 'axios';

const API_BASE = '';

// ─── Types ─────────────────────────────────────────────────────────────────

interface KpiDataResult {
  columns: string[];
  rows: (string | number | null)[][];
  total_rows: number;
  offset: number;
  limit: number;
}

interface ScanFile {
  name: string;
  type: 'html' | 'pdf';
}

interface LogResult {
  lines: string[];
  total_lines: number;
  offset: number;
  returned: number;
}

interface SnapshotFoldersResult {
  active_snapshot: string | null;
  folders: string[];
}

interface SnapshotFileResult {
  snapshot_id: string;
  file: string;
  bytes: number;
  truncated: boolean;
  content: string;
}

interface SnapshotFormattedResult {
  snapshot_id: string;
  file: string;
  truncated: boolean;
  content: string;
}

interface SnapshotSummaryRow {
  key: string;
  entity: string;
  display_name: string;
  member_or_kpi_count: number | null;
  status: string;
  overall_score?: number | null;
  red_kpis?: number;
}

interface SnapshotSummaryStats {
  avg: number | null;
  min: number | null;
  max: number | null;
}

interface SnapshotStatusCounts {
  ok: number;
  inactive: number;
  failed: number;
  n_a: number;
}

interface SnapshotTopRedEntity {
  key: string;
  entity: string;
  display_name: string;
  red_kpis: number;
  total_kpis: number | null;
  overall_score: number | null;
}

interface SnapshotManifestSummary {
  generated_at: string | null;
  source: string | null;
  periods: string[];
  team_count: number | null;
  scrum_count: number | null;
  employee_count: number | null;
}

interface SnapshotSummaryResult {
  snapshot_id: string;
  file: string;
  scope: string;
  as_of_date: string | null;
  period: string | null;
  top_level_keys: string[];
  entry_count: number;
  status_counts: SnapshotStatusCounts;
  score_stats: SnapshotSummaryStats;
  kpi_count_stats: SnapshotSummaryStats;
  member_count_stats: SnapshotSummaryStats;
  red_kpi_stats: SnapshotSummaryStats;
  category_status_counts: Record<string, { green: number; orange: number; red: number; n_a: number }>;
  top_red_entities: SnapshotTopRedEntity[];
  manifest?: SnapshotManifestSummary;
  sample_rows: SnapshotSummaryRow[];
}

// ─── KPI Section ────────────────────────────────────────────────────────────

// A "KPI entry" in the dropdown: either a real file or an equivalent alias
interface KpiEntry {
  file: string;       // display name / file used for selection key
  baseFile: string;   // actual file to load (may differ for equivalents)
  isEquivalent: boolean;
  baseKpi: string;    // e.g. "k4"
  aliasKpi: string;   // e.g. "k8" (same as display KPI id for equivalents)
}

function kpiIdFromFile(file: string): string {
  // "k8-data.csv" → "k8"
  return file.replace('-data.csv', '');
}

const KpiSection: React.FC = () => {
  const [kpiEntries, setKpiEntries] = useState<KpiEntry[]>([]);
  const [selectedFile, setSelectedFile] = useState('');
  // equivalenceInfo holds info for the currently selected equivalent KPI
  const [equivalenceInfo, setEquivalenceInfo] = useState<{ alias: string; base: string } | null>(null);
  const [data, setData] = useState<KpiDataResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(0); // 0-based page index

  useEffect(() => {
    // Fetch both real files and equivalences in parallel
    Promise.all([
      axios.get<string[]>(`${API_BASE}/api/file-viewer/kpi-files`),
      axios.get<Record<string, string>>(`${API_BASE}/api/file-viewer/kpi-equivalents`).catch(() => ({ data: {} })),
    ]).then(([filesRes, equivRes]) => {
      const realFiles: string[] = filesRes.data;
      const equivMap: Record<string, string> = equivRes.data;

      const realFileSet = new Set(realFiles);

      // Build entries for real files
      const entries: KpiEntry[] = realFiles.map(f => ({
        file: f,
        baseFile: f,
        isEquivalent: false,
        baseKpi: kpiIdFromFile(f),
        aliasKpi: kpiIdFromFile(f),
      }));

      // Add entries for equivalent KPIs that DON'T have their own file
      Object.entries(equivMap).forEach(([alias, base]) => {
        const aliasFile = `${alias}-data.csv`;
        const baseFile = `${base}-data.csv`;
        if (!realFileSet.has(aliasFile) && realFileSet.has(baseFile)) {
          entries.push({
            file: aliasFile,
            baseFile,
            isEquivalent: true,
            baseKpi: base,
            aliasKpi: alias,
          });
        }
      });

      // Sort numerically by KPI number
      entries.sort((a, b) => {
        const numA = parseInt(a.aliasKpi.replace('k', ''), 10);
        const numB = parseInt(b.aliasKpi.replace('k', ''), 10);
        return numA - numB;
      });

      setKpiEntries(entries);
    }).catch(() => {});
  }, []);

  const doLoad = useCallback(async (entry: KpiEntry, limit: number, pageIndex: number, totalRows?: number) => {
    if (!entry.baseFile) return;
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, number | string> = { file: entry.baseFile, limit };
      if (pageIndex > 0 && totalRows !== undefined) {
        const rowOffset = Math.max(0, totalRows - limit * (pageIndex + 1));
        params.offset = rowOffset;
      }
      const r = await axios.get(`${API_BASE}/api/file-viewer/kpi-data`, { params });
      setData(r.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to load KPI data');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSelect = (file: string) => {
    const entry = kpiEntries.find(e => e.file === file);
    if (!entry) return;
    setSelectedFile(file);
    setPage(0);
    setEquivalenceInfo(entry.isEquivalent ? { alias: entry.aliasKpi.toUpperCase(), base: entry.baseKpi.toUpperCase() } : null);
    doLoad(entry, pageSize, 0);
  };

  const handlePageSize = (newSize: number) => {
    setPageSize(newSize);
    setPage(0);
    const entry = kpiEntries.find(e => e.file === selectedFile);
    if (entry) doLoad(entry, newSize, 0);
  };

  const totalPages = data ? Math.ceil(data.total_rows / pageSize) : 1;
  const canNewer = page > 0;
  const canOlder = data ? page < totalPages - 1 : false;

  const goNewer = () => {
    const next = page - 1;
    setPage(next);
    const entry = kpiEntries.find(e => e.file === selectedFile);
    if (entry) doLoad(entry, pageSize, next, data?.total_rows);
  };

  const goOlder = () => {
    const next = page + 1;
    setPage(next);
    const entry = kpiEntries.find(e => e.file === selectedFile);
    if (entry) doLoad(entry, pageSize, next, data?.total_rows);
  };

  const displayPage = data ? totalPages - page : 1;
  const selectedEntry = kpiEntries.find(e => e.file === selectedFile);

  return (
    <Box>
      <Box display="flex" gap={2} alignItems="center" flexWrap="wrap" mb={2}>
        <FormControl size="small" sx={{ minWidth: 280 }}>
          <InputLabel>Select KPI File</InputLabel>
          <Select
            value={selectedFile}
            label="Select KPI File"
            onChange={e => handleSelect(e.target.value)}
          >
            {kpiEntries.map(entry => (
              <MenuItem key={entry.file} value={entry.file}>
                <Box display="flex" alignItems="center" gap={1} width="100%">
                  {entry.isEquivalent
                    ? <EquivalentIcon fontSize="small" color="warning" />
                    : <TableChartIcon fontSize="small" color="action" />}
                  <span style={{ flex: 1 }}>{entry.file}</span>
                  {entry.isEquivalent && (
                    <Chip
                      label={`≡ ${entry.baseFile}`}
                      size="small"
                      color="warning"
                      variant="outlined"
                      sx={{ fontSize: '0.65rem', height: 18 }}
                    />
                  )}
                </Box>
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 110 }}>
          <InputLabel>Rows</InputLabel>
          <Select
            value={pageSize}
            label="Rows"
            onChange={e => handlePageSize(Number(e.target.value))}
          >
            {[25, 50, 100, 200, 500].map(n => (
              <MenuItem key={n} value={n}>{n} rows</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Tooltip title="Refresh (latest)">
          <span>
            <IconButton
              size="small"
              onClick={() => {
                setPage(0);
                const entry = kpiEntries.find(e => e.file === selectedFile);
                if (entry) doLoad(entry, pageSize, 0);
              }}
              disabled={!selectedFile || loading}
            >
              <RefreshIcon />
            </IconButton>
          </span>
        </Tooltip>
        {loading && <CircularProgress size={20} />}
      </Box>

      {/* Equivalence info banner */}
      {equivalenceInfo && (
        <Alert
          severity="info"
          icon={<EquivalentIcon />}
          sx={{ mb: 2 }}
        >
          <strong>{equivalenceInfo.alias}</strong> is an equivalent KPI of{' '}
          <strong>{equivalenceInfo.base}</strong> — it shares the same computation and data file.
          Displaying data from <strong>{selectedEntry?.baseFile}</strong>.
        </Alert>
      )}

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {data ? (
        <Box>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={1} flexWrap="wrap" gap={1}>
            <Typography variant="caption" color="text.secondary">
              Showing rows{' '}
              <strong>{(data.offset + 1).toLocaleString()}</strong>–
              <strong>{Math.min(data.offset + data.rows.length, data.total_rows).toLocaleString()}</strong>
              {' '}of{' '}
              <strong>{data.total_rows.toLocaleString()}</strong>{' '}in{' '}
              <em>{selectedEntry?.baseFile ?? selectedFile}</em>
              {equivalenceInfo && (
                <span style={{ color: '#ed6c02' }}>{' '}(source for {equivalenceInfo.alias})</span>
              )}
            </Typography>
            <Box display="flex" alignItems="center" gap={1}>
              <Tooltip title="Older rows">
                <span>
                  <IconButton size="small" onClick={goOlder} disabled={!canOlder || loading}>◀</IconButton>
                </span>
              </Tooltip>
              <Typography variant="caption" color="text.secondary">
                Page {displayPage} / {totalPages}
              </Typography>
              <Tooltip title="Newer rows">
                <span>
                  <IconButton size="small" onClick={goNewer} disabled={!canNewer || loading}>▶</IconButton>
                </span>
              </Tooltip>
            </Box>
          </Box>

          <TableContainer
            component={Paper}
            variant="outlined"
            sx={{ maxHeight: 460, overflow: 'auto' }}
          >
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  {data.columns.map(col => (
                    <TableCell
                      key={col}
                      sx={{ fontWeight: 700, whiteSpace: 'nowrap', bgcolor: 'background.paper' }}
                    >
                      {col}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {data.rows.map((row, i) => (
                  <TableRow key={i} hover>
                    {row.map((cell, j) => (
                      <TableCell key={j} sx={{ whiteSpace: 'nowrap', fontSize: '0.75rem' }}>
                        {cell === null ? '—' : String(cell)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      ) : (
        !loading && !error && (
          <Typography color="text.secondary" align="center" py={5}>
            Select a KPI file above to browse its rows.
          </Typography>
        )
      )}
    </Box>
  );
};

// ─── Scan Reports Section ────────────────────────────────────────────────────

const ScanSection: React.FC = () => {
  const [scanTypes, setScanTypes] = useState<string[]>([]);
  const [activeScanType, setActiveScanType] = useState('');
  const [files, setFiles] = useState<ScanFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    axios.get(`${API_BASE}/api/file-viewer/scan-types`)
      .then(r => {
        const types: string[] = r.data;
        setScanTypes(types);
        if (types.length > 0) setActiveScanType(types[0]);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeScanType) return;
    setLoading(true);
    setError(null);
    axios.get(`${API_BASE}/api/file-viewer/scan-files`, { params: { scan_type: activeScanType } })
      .then(r => setFiles(r.data))
      .catch(e => setError(e?.response?.data?.detail ?? 'Failed to load scan files'))
      .finally(() => setLoading(false));
  }, [activeScanType]);

  const [openingFile, setOpeningFile] = useState<string | null>(null);

  const openFile = async (type: string, file: string) => {
    setOpeningFile(file);
    try {
      const r = await axios.get(`${API_BASE}/api/file-viewer/scan-file`, {
        params: { scan_type: type, file },
        responseType: 'blob',
      });
      const blob = new Blob([r.data], { type: String(r.headers['content-type'] ?? 'application/octet-stream') });
      const blobUrl = URL.createObjectURL(blob);
      const win = window.open(blobUrl, '_blank', 'noopener,noreferrer');
      // Revoke after a short delay to allow the tab to load
      setTimeout(() => URL.revokeObjectURL(blobUrl), 30000);
      if (!win) {
        setError('Popup was blocked. Please allow popups for this site.');
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to open file');
    } finally {
      setOpeningFile(null);
    }
  };

  if (scanTypes.length === 0) {
    return <Typography color="text.secondary">No scan folders found.</Typography>;
  }

  const scanTypeLabel: Record<string, string> = {
    sast: 'SAST',
    dast: 'DAST',
    sca: 'SCA',
    mend: 'Mend / SCA',
  };

  return (
    <Box>
      <Tabs
        value={activeScanType}
        onChange={(_, v) => setActiveScanType(v)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
      >
        {scanTypes.map(t => (
          <Tab
            key={t}
            label={scanTypeLabel[t] ?? t.toUpperCase()}
            value={t}
            icon={<ScanIcon fontSize="small" />}
            iconPosition="start"
          />
        ))}
      </Tabs>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress size={24} />
        </Box>
      ) : files.length === 0 ? (
        <Typography color="text.secondary" py={2}>No files in this scan type.</Typography>
      ) : (
        <Box>
          <Typography variant="body2" color="text.secondary" mb={2}>
            {files.length} file{files.length !== 1 ? 's' : ''} — click to open in a new browser tab
          </Typography>
          <Box display="flex" flexWrap="wrap" gap={1.5}>
            {files.map(f => (
              <Button
                key={f.name}
                variant="outlined"
                size="small"
                startIcon={openingFile === f.name ? <CircularProgress size={14} /> : f.type === 'pdf' ? <PdfIcon /> : <HtmlIcon />}
                endIcon={openingFile !== f.name ? <OpenInNewIcon fontSize="small" /> : undefined}
                onClick={() => openFile(activeScanType, f.name)}
                color={f.type === 'pdf' ? 'secondary' : 'primary'}
                disabled={openingFile === f.name}
                sx={{ textTransform: 'none' }}
              >
                {f.name}
              </Button>
            ))}
          </Box>
        </Box>
      )}
    </Box>
  );
};

// ─── Log Viewer Section ──────────────────────────────────────────────────────

const LOG_COLORS: { test: RegExp; color: string }[] = [
  { test: /\b(ERROR|CRITICAL|FATAL)\b/, color: '#f87171' },
  { test: /\bWARNING\b/, color: '#fbbf24' },
  { test: /\bINFO\b/, color: '#86efac' },
  { test: /\bDEBUG\b/, color: '#93c5fd' },
];

function lineColor(line: string): string {
  for (const { test, color } of LOG_COLORS) {
    if (test.test(line)) return color;
  }
  return '#d4d4d4';
}

const LogSection: React.FC = () => {
  const [logFiles, setLogFiles] = useState<string[]>([]);
  const [selectedLog, setSelectedLog] = useState('');
  const [logLines, setLogLines] = useState(100);
  const [data, setData] = useState<LogResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logBoxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    axios.get(`${API_BASE}/api/file-viewer/logs`)
      .then(r => {
        const files: string[] = r.data;
        setLogFiles(files);
        if (files.length > 0) {
          setSelectedLog(files[0]);
          fetchLog(files[0], 100, 0);
        }
      })
      .catch(() => {});
  }, []);

  // Auto-scroll to bottom whenever new log data arrives (offset=0 = latest)
  useEffect(() => {
    if (data && data.offset === 0 && logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [data]);

  const fetchLog = async (file: string, lines: number, offset: number) => {
    setLoading(true);
    setError(null);
    try {
      const r = await axios.get(`${API_BASE}/api/file-viewer/log`, {
        params: { file, lines, offset },
      });
      setData(r.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to load log');
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (file: string) => {
    setSelectedLog(file);
    setData(null);
    fetchLog(file, logLines, 0);
  };

  const handleLinesChange = (lines: number) => {
    setLogLines(lines);
    if (selectedLog) fetchLog(selectedLog, lines, 0);
  };

  const loadOlder = () => {
    if (!data || !selectedLog) return;
    const newOffset = data.offset + data.returned;
    fetchLog(selectedLog, logLines, newOffset);
  };

  const canLoadOlder = data
    ? data.offset + data.returned < data.total_lines
    : false;

  return (
    <Box>
      <Box display="flex" gap={2} alignItems="center" flexWrap="wrap" mb={2}>
        <FormControl size="small" sx={{ minWidth: 210 }}>
          <InputLabel>Log File</InputLabel>
          <Select
            value={selectedLog}
            label="Log File"
            onChange={e => handleFileChange(e.target.value)}
          >
            {logFiles.map(f => (
              <MenuItem key={f} value={f}>
                <Box display="flex" alignItems="center" gap={1}>
                  <LogIcon fontSize="small" color="action" />
                  {f}
                </Box>
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Lines</InputLabel>
          <Select
            value={logLines}
            label="Lines"
            onChange={e => handleLinesChange(Number(e.target.value))}
          >
            {[50, 100, 200, 500].map(n => (
              <MenuItem key={n} value={n}>{n} lines</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Tooltip title="Refresh (latest)">
          <span>
            <IconButton
              size="small"
              onClick={() => selectedLog && fetchLog(selectedLog, logLines, 0)}
              disabled={loading || !selectedLog}
            >
              <RefreshIcon />
            </IconButton>
          </span>
        </Tooltip>

        {loading && <CircularProgress size={20} />}

        {data && (
          <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
            Showing {data.returned} lines &nbsp;|&nbsp; total: {data.total_lines.toLocaleString()}
          </Typography>
        )}
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {canLoadOlder && (
        <Box display="flex" justifyContent="center" mb={1}>
          <Button size="small" variant="text" onClick={loadOlder} disabled={loading}>
            ↑ Load older lines
          </Button>
        </Box>
      )}

      {data && (
        <Paper
          ref={logBoxRef}
          variant="outlined"
          sx={{
            bgcolor: '#1a1a2e',
            p: 1.5,
            maxHeight: 460,
            overflow: 'auto',
          }}
        >
          {data.lines.map((line, i) => (
            <Box
              key={i}
              component="pre"
              sx={{
                m: 0,
                fontFamily: '"Fira Code", "Courier New", monospace',
                fontSize: '0.72rem',
                lineHeight: 1.55,
                color: lineColor(line),
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
              }}
            >
              {line || '\u200B'}
            </Box>
          ))}
        </Paper>
      )}

      {!data && !loading && !error && (
        <Typography color="text.secondary" align="center" py={5}>
          Select a log file above to view its latest entries.
        </Typography>
      )}
    </Box>
  );
};

// ─── Dashboard Snapshot Files Section ────────────────────────────────────────

const SnapshotSection: React.FC = () => {
  const [folders, setFolders] = useState<string[]>([]);
  const [activeSnapshot, setActiveSnapshot] = useState<string | null>(null);
  const [selectedFolder, setSelectedFolder] = useState('');
  const [files, setFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState('');
  const [data, setData] = useState<SnapshotFileResult | null>(null);
  const [loadingFolders, setLoadingFolders] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [loadingContent, setLoadingContent] = useState(false);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [loadingFormatted, setLoadingFormatted] = useState(false);
  const [downloadingRaw, setDownloadingRaw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<SnapshotSummaryResult | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [formattedData, setFormattedData] = useState<SnapshotFormattedResult | null>(null);
  const [formattedError, setFormattedError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'summary' | 'formatted' | 'raw'>('summary');

  const loadFolders = useCallback(async () => {
    setLoadingFolders(true);
    setError(null);
    try {
      const r = await axios.get<SnapshotFoldersResult>(`${API_BASE}/api/file-viewer/snapshot-folders`);
      const nextFolders = r.data.folders || [];
      setFolders(nextFolders);
      setActiveSnapshot(r.data.active_snapshot || null);

      if (nextFolders.length === 0) {
        setSelectedFolder('');
        setFiles([]);
        setSelectedFile('');
        setData(null);
        return;
      }

      setSelectedFolder((prev) => {
        if (prev && nextFolders.includes(prev)) return prev;
        if (r.data.active_snapshot && nextFolders.includes(r.data.active_snapshot)) return r.data.active_snapshot;
        return nextFolders[0];
      });
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to load snapshot folders');
    } finally {
      setLoadingFolders(false);
    }
  }, []);

  useEffect(() => {
    loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    if (!selectedFolder) return;
    setLoadingFiles(true);
    setError(null);
    axios.get<string[]>(`${API_BASE}/api/file-viewer/snapshot-files`, {
      params: { snapshot_id: selectedFolder },
    })
      .then((r) => {
        const nextFiles = r.data || [];
        setFiles(nextFiles);
        setSelectedFile((prev) => (prev && nextFiles.includes(prev) ? prev : (nextFiles[0] || '')));
      })
      .catch((e) => {
        setError(e?.response?.data?.detail ?? 'Failed to load snapshot files');
        setFiles([]);
        setSelectedFile('');
      })
      .finally(() => setLoadingFiles(false));
  }, [selectedFolder]);

  useEffect(() => {
    if (!selectedFolder || !selectedFile) {
      setData(null);
      setSummary(null);
      return;
    }

    setLoadingSummary(true);
    setSummaryError(null);
    axios.get<SnapshotSummaryResult>(`${API_BASE}/api/file-viewer/snapshot-summary`, {
      params: { snapshot_id: selectedFolder, file: selectedFile },
    })
      .then((r) => setSummary(r.data))
      .catch((e) => {
        setSummaryError(e?.response?.data?.detail ?? 'Failed to load snapshot summary');
        setSummary(null);
      })
      .finally(() => setLoadingSummary(false));

    setLoadingFormatted(true);
    setFormattedError(null);
    axios.get<SnapshotFormattedResult>(`${API_BASE}/api/file-viewer/snapshot-file-formatted`, {
      params: { snapshot_id: selectedFolder, file: selectedFile },
    })
      .then((r) => setFormattedData(r.data))
      .catch((e) => {
        setFormattedError(e?.response?.data?.detail ?? 'Failed to load formatted snapshot content');
        setFormattedData(null);
      })
      .finally(() => setLoadingFormatted(false));

    setLoadingContent(true);
    setError(null);
    axios.get<SnapshotFileResult>(`${API_BASE}/api/file-viewer/snapshot-file`, {
      params: { snapshot_id: selectedFolder, file: selectedFile },
    })
      .then((r) => setData(r.data))
      .catch((e) => {
        setError(e?.response?.data?.detail ?? 'Failed to load snapshot file content');
        setData(null);
      })
      .finally(() => setLoadingContent(false));
  }, [selectedFolder, selectedFile]);

  const handleRawDownload = useCallback(async () => {
    if (!selectedFolder || !selectedFile) return;

    setDownloadingRaw(true);
    setError(null);

    try {
      const response = await axios.get(`${API_BASE}/api/file-viewer/snapshot-file-download`, {
        params: {
          snapshot_id: selectedFolder,
          file: selectedFile,
        },
        responseType: 'blob',
      });

      const contentType = String(response.headers['content-type'] ?? 'application/json');
      const blob = new Blob([response.data], { type: contentType });
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = selectedFile;
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(blobUrl);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to download raw snapshot file');
    } finally {
      setDownloadingRaw(false);
    }
  }, [selectedFolder, selectedFile]);

  return (
    <Box>
      <Box display="flex" gap={2} alignItems="center" flexWrap="wrap" mb={2}>
        <FormControl size="small" sx={{ minWidth: 260 }}>
          <InputLabel>Snapshot Folder</InputLabel>
          <Select
            value={selectedFolder}
            label="Snapshot Folder"
            onChange={(e) => setSelectedFolder(e.target.value)}
            disabled={loadingFolders || folders.length === 0}
          >
            {folders.map((folder) => (
              <MenuItem key={folder} value={folder}>
                <Box display="flex" alignItems="center" gap={1}>
                  {folder}
                  {activeSnapshot === folder && (
                    <Chip label="ACTIVE" size="small" color="success" variant="outlined" />
                  )}
                </Box>
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 260 }}>
          <InputLabel>Snapshot File</InputLabel>
          <Select
            value={selectedFile}
            label="Snapshot File"
            onChange={(e) => setSelectedFile(e.target.value)}
            disabled={loadingFiles || files.length === 0 || !selectedFolder}
          >
            {files.map((file) => (
              <MenuItem key={file} value={file}>{file}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <Tooltip title="Refresh folders/files">
          <span>
            <IconButton size="small" onClick={loadFolders} disabled={loadingFolders || loadingFiles || loadingContent || loadingSummary || loadingFormatted}>
              <RefreshIcon />
            </IconButton>
          </span>
        </Tooltip>

        {(loadingFolders || loadingFiles || loadingContent || loadingSummary || loadingFormatted) && <CircularProgress size={20} />}
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {summaryError && <Alert severity="warning" sx={{ mb: 2 }}>{summaryError}</Alert>}
      {formattedError && <Alert severity="warning" sx={{ mb: 2 }}>{formattedError}</Alert>}

      {!loadingFolders && folders.length === 0 && (
        <Typography color="text.secondary" py={2}>No dashboard snapshots found in output/dashboard_snapshots.</Typography>
      )}

      {data && (
        <Box>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={1} flexWrap="wrap" gap={1}>
            <Typography variant="caption" color="text.secondary">
              <strong>{data.file}</strong> from <strong>{data.snapshot_id}</strong> · {data.bytes.toLocaleString()} bytes
            </Typography>
            <Box display="flex" gap={1} alignItems="center">
              {data.truncated && (
                <Chip
                  label="Preview truncated"
                  size="small"
                  color="warning"
                  variant="outlined"
                />
              )}
            </Box>
          </Box>

          <Tabs
            value={viewMode}
            onChange={(_, v) => setViewMode(v)}
            sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
          >
            <Tab value="summary" label="Summary" />
            <Tab value="formatted" label="Formatted JSON" />
            <Tab value="raw" label="Raw" />
          </Tabs>

          {viewMode === 'summary' && (
            <Box>
              {summary ? (
                <>
                  <Box display="flex" gap={1} flexWrap="wrap" mb={1.5}>
                    <Chip label={`Scope: ${summary.scope || 'unknown'}`} size="small" variant="outlined" />
                    <Chip label={`As of: ${summary.as_of_date ?? 'n/a'}`} size="small" variant="outlined" />
                    <Chip label={`Period: ${summary.period ?? 'n/a'}`} size="small" variant="outlined" />
                    <Chip label={`Entries: ${summary.entry_count ?? 0}`} size="small" variant="outlined" />
                  </Box>

                  {summary.scope === 'manifest' && summary.manifest && (
                    <Box display="flex" gap={1} flexWrap="wrap" mb={1.5}>
                      <Chip label={`Generated: ${summary.manifest.generated_at ?? 'n/a'}`} size="small" color="info" variant="outlined" />
                      <Chip label={`Source: ${summary.manifest.source ?? 'n/a'}`} size="small" color="info" variant="outlined" />
                      <Chip label={`Teams: ${summary.manifest.team_count ?? 0}`} size="small" color="primary" variant="outlined" />
                      <Chip label={`Scrums: ${summary.manifest.scrum_count ?? 0}`} size="small" color="primary" variant="outlined" />
                      <Chip label={`Employees: ${summary.manifest.employee_count ?? 0}`} size="small" color="primary" variant="outlined" />
                    </Box>
                  )}

                  {summary.scope !== 'manifest' && (
                    <>
                      <Box display="flex" gap={1} flexWrap="wrap" mb={1.5}>
                        <Chip label={`OK: ${summary.status_counts?.ok ?? 0}`} size="small" color="success" variant="outlined" />
                        <Chip label={`Inactive: ${summary.status_counts?.inactive ?? 0}`} size="small" color="warning" variant="outlined" />
                        <Chip label={`Failed: ${summary.status_counts?.failed ?? 0}`} size="small" color="error" variant="outlined" />
                        <Chip label={`N/A: ${summary.status_counts?.n_a ?? 0}`} size="small" variant="outlined" />
                      </Box>

                      <Box display="flex" gap={1} flexWrap="wrap" mb={1.5}>
                        <Chip label={`Score avg/min/max: ${summary.score_stats?.avg ?? 'n/a'} / ${summary.score_stats?.min ?? 'n/a'} / ${summary.score_stats?.max ?? 'n/a'}`} size="small" variant="outlined" />
                        <Chip label={`KPIs avg/min/max: ${summary.kpi_count_stats?.avg ?? 'n/a'} / ${summary.kpi_count_stats?.min ?? 'n/a'} / ${summary.kpi_count_stats?.max ?? 'n/a'}`} size="small" variant="outlined" />
                        <Chip label={`Red KPIs avg/min/max: ${summary.red_kpi_stats?.avg ?? 'n/a'} / ${summary.red_kpi_stats?.min ?? 'n/a'} / ${summary.red_kpi_stats?.max ?? 'n/a'}`} size="small" variant="outlined" />
                        <Chip label={`Members avg/min/max: ${summary.member_count_stats?.avg ?? 'n/a'} / ${summary.member_count_stats?.min ?? 'n/a'} / ${summary.member_count_stats?.max ?? 'n/a'}`} size="small" variant="outlined" />
                      </Box>

                      <Typography variant="subtitle2" sx={{ mb: 1 }}>Category Status Distribution</Typography>
                      <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 220, mb: 2 }}>
                        <Table size="small" stickyHeader>
                          <TableHead>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 700 }}>Category</TableCell>
                              <TableCell sx={{ fontWeight: 700 }}>Green</TableCell>
                              <TableCell sx={{ fontWeight: 700 }}>Orange</TableCell>
                              <TableCell sx={{ fontWeight: 700 }}>Red</TableCell>
                              <TableCell sx={{ fontWeight: 700 }}>N/A</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {Object.entries(summary.category_status_counts ?? {}).map(([category, counts]) => (
                              <TableRow key={category} hover>
                                <TableCell>{category}</TableCell>
                                <TableCell>{counts.green}</TableCell>
                                <TableCell>{counts.orange}</TableCell>
                                <TableCell>{counts.red}</TableCell>
                                <TableCell>{counts.n_a}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>

                      <Typography variant="subtitle2" sx={{ mb: 1 }}>Top Red KPI Entities</Typography>
                      <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 220, mb: 2 }}>
                        <Table size="small" stickyHeader>
                          <TableHead>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 700 }}>Entity</TableCell>
                              <TableCell sx={{ fontWeight: 700 }}>Name</TableCell>
                              <TableCell sx={{ fontWeight: 700 }}>Red KPIs</TableCell>
                              <TableCell sx={{ fontWeight: 700 }}>Total KPIs</TableCell>
                              <TableCell sx={{ fontWeight: 700 }}>Overall Score</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {(summary.top_red_entities ?? []).map((entity) => (
                              <TableRow key={entity.key} hover>
                                <TableCell sx={{ textTransform: 'capitalize' }}>{entity.entity || summary.scope || 'unknown'}</TableCell>
                                <TableCell>{entity.display_name || entity.key || 'unknown'}</TableCell>
                                <TableCell>{entity.red_kpis}</TableCell>
                                <TableCell>{entity.total_kpis ?? '—'}</TableCell>
                                <TableCell>{entity.overall_score ?? '—'}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </>
                  )}

                  <Typography variant="caption" color="text.secondary" display="block" mb={1}>
                    Top-level keys: {(summary.top_level_keys ?? []).join(', ')}
                  </Typography>

                  <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 420 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 700 }}>Entity</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Name</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Member/KPI Count</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Red KPIs</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Overall Score</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {(summary.sample_rows ?? []).map((row) => (
                          <TableRow key={row.key} hover>
                            <TableCell sx={{ textTransform: 'capitalize' }}>{row.entity || summary.scope || 'unknown'}</TableCell>
                            <TableCell>{row.display_name || row.key || 'unknown'}</TableCell>
                            <TableCell>{row.member_or_kpi_count ?? '—'}</TableCell>
                            <TableCell>{row.status}</TableCell>
                            <TableCell>{row.red_kpis ?? 0}</TableCell>
                            <TableCell>{row.overall_score ?? '—'}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </>
              ) : (
                <Alert severity="info">Loading summary… If this persists, use Raw tab.</Alert>
              )}
            </Box>
          )}

          {viewMode === 'formatted' && (
            <Paper
              variant="outlined"
              sx={{
                bgcolor: '#1a1a2e',
                p: 1.5,
                maxHeight: 460,
                overflow: 'auto',
              }}
            >
              <Box
                component="pre"
                sx={{
                  m: 0,
                  fontFamily: '"Fira Code", "Courier New", monospace',
                  fontSize: '0.72rem',
                  lineHeight: 1.55,
                  color: '#d4d4d4',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {formattedData?.content || (data.content || '\u200B')}
              </Box>
            </Paper>
          )}

          {viewMode === 'raw' && (
            <Box>
              <Alert severity="info" sx={{ mb: 2 }}>
                Raw files are download-only to avoid heavy browser rendering for large snapshots.
              </Alert>
              <Button
                variant="contained"
                startIcon={downloadingRaw ? <CircularProgress size={16} color="inherit" /> : <OpenInNewIcon />}
                onClick={handleRawDownload}
                disabled={downloadingRaw || !selectedFolder || !selectedFile}
              >
                {downloadingRaw ? 'Downloading…' : 'Download Raw JSON'}
              </Button>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
};

// ─── Main Tab Component ──────────────────────────────────────────────────────

const FileViewerTab: React.FC = () => {
  const [section, setSection] = useState(0);

  const sectionTabs = [
    { label: 'KPI Data Files', icon: <TableChartIcon /> },
    { label: 'Scan Reports', icon: <ScanIcon /> },
    { label: 'Application Logs', icon: <LogIcon /> },
    { label: 'Dashboard Snapshots', icon: <FolderIcon /> },
  ];

  return (
    <Box>
      <Card>
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={2}>
            <FolderIcon color="action" />
            <Typography variant="h6">File Viewer</Typography>
          </Box>

          <Tabs
            value={section}
            onChange={(_, v) => setSection(v)}
            sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
          >
            {sectionTabs.map((t, i) => (
              <Tab
                key={i}
                icon={t.icon}
                iconPosition="start"
                label={t.label}
              />
            ))}
          </Tabs>

          <Divider sx={{ mb: 3 }} />

          {section === 0 && <KpiSection />}
          {section === 1 && <ScanSection />}
          {section === 2 && <LogSection />}
          {section === 3 && <SnapshotSection />}
        </CardContent>
      </Card>
    </Box>
  );
};

export default FileViewerTab;
