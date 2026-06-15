#!/usr/bin/env python3
"""
GitHub Commits Fetcher - Python Script
Fetches commit details from multiple GitHub Enterprise repositories
Can export to CSV, Excel, or Google Sheets
"""

import requests
import json
import csv
import re
import fcntl
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
import sys
import pandas as pd
import time
from contextlib import contextmanager

# ============================================================================
# CONFIGURATION
# ============================================================================

# All configuration will be loaded from github_config.json
# Global defaults will be set after loading the config file

def _resolve_project_root() -> str:
    """Resolve TeamSight project root for config/data/output paths."""
    env_root = os.getenv('TEAMSIGHT_HOME')
    if env_root:
        return os.path.abspath(os.path.expanduser(env_root))

    source_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(source_root, 'config')):
        return source_root

    cwd_root = os.getcwd()
    if os.path.isdir(os.path.join(cwd_root, 'config')):
        return cwd_root

    return source_root


PROJECT_ROOT = _resolve_project_root()


def _resolve_path(path_value: str) -> str:
    """Resolve relative paths against TeamSight project root."""
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(PROJECT_ROOT, path_value)


def _ensure_parent_dir(file_path: str):
    """Ensure parent directory exists for a file path."""
    parent_dir = os.path.dirname(file_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)


def _derive_commit_files_output(commits_output: str) -> str:
    """Derive file-level CSV output path from commit-level CSV path."""
    name = os.path.basename(commits_output)
    directory = os.path.dirname(commits_output)

    if name.endswith('_commits.csv'):
        file_name = name.replace('_commits.csv', '_commit_files.csv')
    elif name.endswith('.csv'):
        file_name = name.replace('.csv', '_files.csv')
    else:
        file_name = f"{name}_files.csv"

    return os.path.join(directory, file_name)


@contextmanager
def acquire_fetch_lock(lock_file: Optional[str] = None):
    """Acquire shared lock to prevent concurrent SCM fetch jobs."""
    if lock_file is None:
        lock_file = FETCH_LOCK_FILE
    _ensure_parent_dir(lock_file)
    lock_handle = open(lock_file, 'w', encoding='utf-8')
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        raise RuntimeError('Another SCM fetch job is already running')

    try:
        lock_handle.write(str(os.getpid()))
        lock_handle.flush()
        yield
    finally:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
        finally:
            lock_handle.close()

# Export format (only CSV is supported)
EXPORT_FORMAT = 'csv'
OUTPUT_FILE = os.path.join(PROJECT_ROOT, 'output', 'github_commits.csv')

# Checkpoint file to track last fetched commit per repository
CHECKPOINT_FILE = os.path.join(PROJECT_ROOT, 'data', 'fetch_checkpoint.json')

# Shared lock for SCM fetchers (GitHub + GitLab)
FETCH_LOCK_FILE = os.path.join(PROJECT_ROOT, 'data', 'scm_fetch.lock')

# Rate limiting: delay in seconds between repository fetches
REPO_FETCH_DELAY = 2

# Batch size for fetching commits (GitHub API page size max is 100)
COMMIT_BATCH_SIZE = 100

# Minimum commit date filter (only fetch commits on or after this date)
# Set to None to fetch all commits, or specify a date string like '2025-04-01'
MIN_COMMIT_DATE = '2025-04-01'  # Format: 'YYYY-MM-DD' or None

# Sliding overlap window (days) applied to checkpoint-based incremental fetches
# to catch late-pushed commits whose authored/committed timestamp is older than
# the last checkpoint timestamp.
CHECKPOINT_OVERLAP_DAYS = 15

# Repository list file (JSON file with repository list)
# Set to None to use REPOSITORY_LIST from code, or specify a JSON file path
REPOSITORY_LIST_FILE = None  # Format: 'repos.json' or None

# Configuration file for per-repository settings
CONFIG_FILE = os.path.join(PROJECT_ROOT, 'config', 'github_config.json')

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_config_file(config_file: str = CONFIG_FILE) -> Dict:
    """
    Load configuration from JSON file
    
    Returns:
        Dictionary with default and per-repository settings
    """
    if not os.path.exists(config_file):
        print(f"⚠️  Warning: Config file '{config_file}' not found. Using defaults.")
        return {}
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            
            # Convert relative paths to absolute paths from project root
            if 'outputFile' in config and not os.path.isabs(config['outputFile']):
                config['outputFile'] = _resolve_path(config['outputFile'])
            if 'checkpointFile' in config and not os.path.isabs(config['checkpointFile']):
                config['checkpointFile'] = _resolve_path(config['checkpointFile'])
            
            return config
    except Exception as e:
        print(f"⚠️  Warning: Could not load config file: {e}")
        return {}


def get_repository_config(config_data: Dict, owner: str, repo: str) -> Dict:
    """
    Get configuration for a specific repository, merging with defaults
    
    Args:
        config_data: Full configuration data from file
        owner: Repository owner
        repo: Repository name
        
    Returns:
        Dictionary with merged configuration, or None if token is missing
    """
    repo_key = f"{owner}/{repo}"
    
    # Start with environment/default settings
    repo_config = {
        'githubToken': GITHUB_TOKEN,
        'githubApiBaseUrl': GITHUB_API_BASE_URL
    }
    
    # Override with config file defaults
    if 'default' in config_data:
        default_config = config_data['default']
        if 'githubToken' in default_config:
            repo_config['githubToken'] = default_config['githubToken']
        if 'githubApiBaseUrl' in default_config:
            repo_config['githubApiBaseUrl'] = default_config['githubApiBaseUrl']
    
    # Override with repository-specific settings
    if 'repositories' in config_data and repo_key in config_data['repositories']:
        repo_specific = config_data['repositories'][repo_key]
        if 'githubToken' in repo_specific:
            repo_config['githubToken'] = repo_specific['githubToken']
        if 'githubApiBaseUrl' in repo_specific:
            repo_config['githubApiBaseUrl'] = repo_specific['githubApiBaseUrl']
    
    # Validate that we have a token
    if not repo_config['githubToken']:
        return None
    
    return repo_config


def get_repository_list(config_data: Dict) -> List[Dict]:
    """
    Get repository list from configuration file
    
    Args:
        config_data: Full configuration data from file
        
    Returns:
        List of repository dictionaries with 'owner' and 'repo' keys
    """
    if not config_data or 'repositories' not in config_data:
        print("⚠️  Warning: No repositories found in config file")
        return []
    
    repo_list = []
    for repo_key in config_data['repositories'].keys():
        if '/' in repo_key:
            owner, repo = repo_key.split('/', 1)
            repo_list.append({'owner': owner, 'repo': repo})
    
    return repo_list


# Load configuration on module init
GLOBAL_CONFIG_DATA = load_config_file()
REPOSITORY_LIST = get_repository_list(GLOBAL_CONFIG_DATA)

# Load default GitHub token and API URL from config file
GITHUB_TOKEN = GLOBAL_CONFIG_DATA.get('default', {}).get('githubToken', '')
if not GITHUB_TOKEN:
    env_token = os.getenv('GITHUB_TOKEN', '')
    if env_token:
        GITHUB_TOKEN = env_token
        print("⚠️  WARNING: Using GITHUB_TOKEN from environment variable (not from config file)")
        print("   This is not the normal configuration method. Please add 'githubToken' to github_config.json")

GITHUB_API_BASE_URL = GLOBAL_CONFIG_DATA.get('default', {}).get('githubApiBaseUrl', 'https://github01.hclpnp.com/api/v3')

try:
    COMMIT_BATCH_SIZE = int(
        GLOBAL_CONFIG_DATA.get('default', {}).get('batchSize', COMMIT_BATCH_SIZE)
    )
except (TypeError, ValueError):
    COMMIT_BATCH_SIZE = 100
if COMMIT_BATCH_SIZE <= 0:
    COMMIT_BATCH_SIZE = 100

try:
    CHECKPOINT_OVERLAP_DAYS = int(
        GLOBAL_CONFIG_DATA.get('default', {}).get(
            'checkpointOverlapDays',
            GLOBAL_CONFIG_DATA.get('default', {}).get('overlapDays', CHECKPOINT_OVERLAP_DAYS),
        )
    )
except (TypeError, ValueError):
    CHECKPOINT_OVERLAP_DAYS = 15
if CHECKPOINT_OVERLAP_DAYS < 0:
    CHECKPOINT_OVERLAP_DAYS = 0

# Load valid JIRA project codes from jira_config.json
VALID_JIRA_PROJECTS = []
try:
    jira_config_path = os.path.join(PROJECT_ROOT, 'config', 'jira_config.json')
    if os.path.exists(jira_config_path):
        with open(jira_config_path, 'r') as f:
            jira_config = json.load(f)
            VALID_JIRA_PROJECTS = list(jira_config.get('projects', {}).keys())
except Exception:
    pass  # Silently fail if JIRA config not available

def load_checkpoint() -> Dict[str, str]:
    """
    Load checkpoint data from file
    
    Returns:
        Dictionary with repository keys and their last fetched commit dates
    """
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Warning: Could not load checkpoint file: {e}")
    return {}


def save_checkpoint(checkpoint_data: Dict[str, str]):
    """
    Save checkpoint data to file
    
    Args:
        checkpoint_data: Dictionary with repository keys and their last fetched commit dates
    """
    try:
        _ensure_parent_dir(CHECKPOINT_FILE)
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
        print(f"💾 Checkpoint saved to {CHECKPOINT_FILE}")
    except Exception as e:
        print(f"⚠️  Warning: Could not save checkpoint: {e}")


def load_repository_list_from_file(file_path: str) -> List[Dict]:
    """
    Load repository list from a JSON file
    
    Args:
        file_path: Path to JSON file containing repository list
        
    Returns:
        List of repository dictionaries with 'owner' and 'repo' keys
        
    Expected JSON format:
    [
        {"owner": "org1", "repo": "repo1"},
        {"owner": "org2", "repo": "repo2"}
    ]
    """
    try:
        with open(file_path, 'r') as f:
            repos = json.load(f)
        
        if not isinstance(repos, list):
            raise ValueError("Repository list file must contain a JSON array")
        
        # Validate format
        for repo in repos:
            if not isinstance(repo, dict) or 'owner' not in repo or 'repo' not in repo:
                raise ValueError("Each repository must be an object with 'owner' and 'repo' keys")
        
        return repos
    except FileNotFoundError:
        print(f"❌ Repository list file not found: {file_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in repository list file: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"❌ Invalid repository list format: {e}")
        sys.exit(1)


def categorize_file(filename: str, filepath: str) -> Dict:
    """
    Categorize a file based on extension, path, and naming patterns.
    
    Args:
        filename: Base filename (e.g., 'LoginScreen.jsx')
        filepath: Full file path (e.g., 'src/screens/LoginScreen.jsx')
    
    Returns:
        Dictionary with category, subcategory, is_screen, confidence
    """
    import os
    
    # Normalize path separators
    filepath_lower = filepath.lower().replace('\\', '/')
    filename_lower = filename.lower()
    
    # Extract extension
    _, ext = os.path.splitext(filename_lower)
    
    # Enhanced test file detection
    # Path-based patterns (folder names) - both with trailing slash and at path start
    test_path_patterns = [
        '/test/', '/tests/', '/__tests__/', '/__test__/', 
        'test/', 'tests/', '__tests__/',  # At beginning of path
        '/unittest/', '/unittests/', '/unit_test/', '/unit_tests/',
        'unittest/', 'unittests/', 'unit_test/', 'unit_tests/',  # At beginning
        '/integrationtest/', '/integration_test/', '/integration_tests/',
        'integrationtest/', 'integration_test/', 'integration_tests/',  # At beginning
        '/e2etest/', '/e2e_test/', '/e2e/', '/e2e-tests/',
        'e2etest/', 'e2e_test/', 'e2e/', 'e2e-tests/', 'e2etests/',  # At beginning
        '/__mocks__/', '/mock/', '/mocks/',
        '__mocks__/', 'mock/', 'mocks/',  # At beginning
        '/spec/', '/specs/',
        'spec/', 'specs/',  # At beginning
        '/testing/', '/testdata/', '/test_data/',
        'testing/', 'testdata/', 'test_data/',  # At beginning
        '/fixtures/', '/fixture/',
        'fixtures/', 'fixture/'  # At beginning
    ]
    
    # Filename patterns (naming conventions)
    test_filename_patterns = [
        'test_',           # Python: test_login.py
        '_test.',          # Go: login_test.go
        '.test.',          # JS/TS: login.test.js, login.test.tsx
        '.spec.',          # Angular/Vue: login.spec.ts
        'test.js',         # Direct test files
        'test.ts', 
        'test.jsx',
        'test.tsx',
        'spec.js',
        'spec.ts',
        'spec.jsx',
        'spec.tsx'
    ]
    
    # Check path patterns FIRST (higher priority)
    is_test_path = any(pattern in filepath_lower for pattern in test_path_patterns)
    
    # Check filename patterns
    is_test_filename = any(pattern in filename_lower for pattern in test_filename_patterns)
    
    # Additional check: files ending with "Tests.java", "Tests.kt", "Test.java", "Test.kt"
    is_java_test = (ext in ['.java', '.kt']) and (
        filename_lower.endswith('test.java') or 
        filename_lower.endswith('test.kt') or
        filename_lower.endswith('tests.java') or 
        filename_lower.endswith('tests.kt')
    )
    
    # Check for common test framework imports/annotations in path context
    # (e.g., files in folders containing 'junit', 'pytest', 'jest', 'mocha')
    test_framework_patterns = ['/junit/', '/pytest/', '/jest/', '/mocha/', '/jasmine/', '/karma/']
    is_test_framework = any(pattern in filepath_lower for pattern in test_framework_patterns)
    
    # Determine subcategory based on extension
    test_subcategory_map = {
        '.py': 'python_test',
        '.js': 'javascript_test',
        '.jsx': 'react_test',
        '.ts': 'typescript_test',
        '.tsx': 'react_typescript_test',
        '.java': 'java_test',
        '.kt': 'kotlin_test',
        '.go': 'go_test',
        '.rb': 'ruby_test',
        '.php': 'php_test',
        '.cs': 'csharp_test',
        '.swift': 'swift_test',
        '.dart': 'dart_test'
    }
    
    if is_test_path or is_test_filename or is_java_test or is_test_framework:
        subcategory = test_subcategory_map.get(ext, 'test')
        confidence = 'high' if (is_test_path or is_java_test) else 'medium'
        
        return {
            'category': 'test',
            'subcategory': subcategory,
            'is_screen': False,
            'confidence': confidence
        }
    
    # DATA SCIENCE / ML DETECTION
    # Jupyter notebooks
    if ext == '.ipynb':
        return {
            'category': 'data_science',
            'subcategory': 'notebook',
            'is_screen': False,
            'confidence': 'high'
        }
    
    # R scripts and markdown
    if ext in ['.r', '.rmd', '.rmarkdown']:
        return {
            'category': 'data_science',
            'subcategory': 'r_script',
            'is_screen': False,
            'confidence': 'high'
        }
    
    # Data files
    data_extensions = ['.csv', '.parquet', '.feather', '.arrow', '.pkl', '.pickle', 
                      '.h5', '.hdf5', '.hdf', '.mat', '.sav', '.dta', '.rds', '.rdata']
    if ext in data_extensions:
        return {
            'category': 'data_science',
            'subcategory': 'data_file',
            'is_screen': False,
            'confidence': 'high'
        }
    
    # ML/LLM model files and weights
    ml_model_extensions = ['.joblib', '.pb', '.pth', '.pt', '.onnx', '.tflite', 
                          '.caffemodel', '.h5', '.keras', '.ckpt', '.weights',
                          '.safetensors', '.bin', '.msgpack', '.index']
    
    # LLM-specific files (transformers, embeddings, tokenizers)
    llm_file_patterns = ['tokenizer', 'vocab', 'merges', 'config.json', 'pytorch_model',
                        'tf_model', 'model.safetensors', 'adapter_', 'lora_']
    has_llm_pattern = any(pattern in filename_lower for pattern in llm_file_patterns)
    
    if ext in ml_model_extensions or 'model' in filename_lower or has_llm_pattern:
        # Check if in ML/LLM paths for higher confidence
        ml_paths = ['/models/', '/ml/', '/machine_learning/', '/data_science/', 
                   '/notebooks/', '/analysis/', '/training/', '/inference/',
                   '/llm/', '/transformers/', '/embeddings/', '/fine-tuning/',
                   '/fine_tuning/', '/checkpoints/', '/weights/', '/pretrained/']
        in_ml_path = any(path in filepath_lower for path in ml_paths)
        
        # Determine if it's specifically LLM-related
        llm_paths = ['/llm/', '/gpt/', '/bert/', '/transformers/', '/langchain/',
                    '/llamaindex/', '/embeddings/', '/prompts/', '/agents/']
        in_llm_path = any(path in filepath_lower for path in llm_paths)
        
        subcategory = 'llm_model' if (in_llm_path or has_llm_pattern) else 'ml_model'
        
        return {
            'category': 'data_science',
            'subcategory': subcategory,
            'is_screen': False,
            'confidence': 'high' if in_ml_path else 'medium'
        }
    
    # SQL files - context-aware categorization
    if ext == '.sql':
        # Data science SQL (analysis, reporting, ETL)
        ds_sql_paths = ['/analysis/', '/queries/', '/reports/', '/etl/', '/data_science/',
                       '/notebooks/', '/analytics/', '/bi/', '/warehouse/']
        in_ds_sql_path = any(path in filepath_lower for path in ds_sql_paths)
        
        # Application SQL (migrations, schema, backend)
        app_sql_paths = ['/migrations/', '/schema/', '/db/', '/database/', '/sql/',
                        '/backend/', '/api/', '/models/']
        in_app_sql_path = any(path in filepath_lower for path in app_sql_paths)
        
        # Check filename patterns for data science
        ds_sql_keywords = ['analysis', 'report', 'analytics', 'query', 'explore', 'aggregate']
        has_ds_keyword = any(keyword in filename_lower for keyword in ds_sql_keywords)
        
        if in_ds_sql_path or (has_ds_keyword and not in_app_sql_path):
            return {
                'category': 'data_science',
                'subcategory': 'query',
                'is_screen': False,
                'confidence': 'high' if in_ds_sql_path else 'medium'
            }
        # Otherwise, treat as backend/config (will be handled later)
        # Don't categorize here, let it fall through to backend/config detection
    
    # Python ML/LLM/data science scripts (check path and content context)
    if ext == '.py':
        # ML/LLM paths
        ml_paths = ['/notebooks/', '/analysis/', '/data_science/', '/ml/', '/machine_learning/',
                   '/models/', '/training/', '/preprocessing/', '/features/', '/pipeline/',
                   '/llm/', '/transformers/', '/embeddings/', '/fine-tuning/', '/fine_tuning/',
                   '/inference/', '/agents/', '/prompts/', '/langchain/', '/llamaindex/']
        in_ml_path = any(path in filepath_lower for path in ml_paths)
        
        # ML/DS keywords in filename
        ml_ds_keywords = ['train', 'model', 'predict', 'feature', 'preprocess', 'pipeline',
                         'analysis', 'visualization', 'viz', 'explore', 'eda', 'clean',
                         'inference', 'evaluate', 'metrics', 'dataset']
        has_ml_keyword = any(keyword in filename_lower for keyword in ml_ds_keywords)
        
        # LLM-specific keywords
        llm_keywords = ['llm', 'gpt', 'bert', 'transformer', 'tokenize', 'embedding',
                       'fine_tune', 'finetune', 'prompt', 'agent', 'langchain',
                       'llamaindex', 'rag', 'retrieval', 'generation', 'chat']
        has_llm_keyword = any(keyword in filename_lower for keyword in llm_keywords)
        
        # LLM paths
        llm_paths = ['/llm/', '/gpt/', '/bert/', '/transformers/', '/langchain/',
                    '/llamaindex/', '/embeddings/', '/prompts/', '/agents/', '/rag/']
        in_llm_path = any(path in filepath_lower for path in llm_paths)
        
        if in_ml_path or has_ml_keyword or has_llm_keyword or in_llm_path:
            # Determine subcategory
            if in_llm_path or has_llm_keyword:
                subcategory = 'python_llm'
            elif 'train' in filename_lower or 'training' in filepath_lower:
                subcategory = 'python_ml_training'
            elif 'inference' in filename_lower or 'predict' in filename_lower:
                subcategory = 'python_ml_inference'
            else:
                subcategory = 'python_ds'
            
            return {
                'category': 'data_science',
                'subcategory': subcategory,
                'is_screen': False,
                'confidence': 'high' if (in_ml_path or in_llm_path) else 'medium'
            }
    
    # LLM prompt and configuration files
    # Text files in prompts directories or with prompt-related names
    if ext in ['.txt', '.md']:
        llm_paths = ['/prompts/', '/prompt_templates/', '/system_prompts/', '/agents/',
                    '/llm/', '/langchain/', '/instructions/']
        in_llm_path = any(path in filepath_lower for path in llm_paths)
        
        llm_keywords = ['prompt', 'instruction', 'system_message', 'agent', 'template']
        has_llm_keyword = any(keyword in filename_lower for keyword in llm_keywords)
        
        if in_llm_path or has_llm_keyword:
            return {
                'category': 'data_science',
                'subcategory': 'llm_prompt',
                'is_screen': False,
                'confidence': 'high' if in_llm_path else 'medium'
            }
    
    # YAML/JSON config files for ML/LLM (in ML contexts)
    if ext in ['.yaml', '.yml', '.json']:
        ml_config_paths = ['/models/', '/ml/', '/llm/', '/transformers/', '/config/',
                          '/fine-tuning/', '/training/', '/inference/']
        in_ml_config_path = any(path in filepath_lower for path in ml_config_paths)
        
        ml_config_keywords = ['model_config', 'training_config', 'inference_config',
                             'hyperparameters', 'config', 'tokenizer']
        has_ml_config_keyword = any(keyword in filename_lower for keyword in ml_config_keywords)
        
        if in_ml_config_path and has_ml_config_keyword:
            return {
                'category': 'data_science',
                'subcategory': 'ml_config',
                'is_screen': False,
                'confidence': 'high'
            }
    
    # Exclude build/dist folders
    exclude_patterns = ['/node_modules/', '/dist/', '/build/', '/.next/', '/coverage/', '/vendor/']
    if any(pattern in filepath_lower for pattern in exclude_patterns):
        return {
            'category': 'excluded',
            'subcategory': 'build_artifact',
            'is_screen': False,
            'confidence': 'high'
        }
    
    # BACKEND DETECTION - Check for backend paths BEFORE screen detection
    # Exclude API/controller/service paths from being categorized as screens
    backend_paths = ['/api/', '/controllers/', '/api-gateway/', '/services/', '/backend/', 
                    '/server/', '/routes/', '/middleware/', '/models/', '/repositories/']
    is_backend_path = any(path in filepath_lower for path in backend_paths)
    
    # HIGH CONFIDENCE SCREENS - Path-based
    screen_paths = ['/screens/', '/pages/', '/views/', '/activities/', '/fragments/', '/viewcontrollers/']
    in_screen_path = any(path in filepath_lower for path in screen_paths)
    
    # Screen naming patterns (only for frontend files, not backend)
    screen_suffixes = ['screen.jsx', 'screen.tsx', 'page.tsx', 'page.jsx', 'page.vue', 
                       'view.swift', 'viewcontroller.swift', 'activity.java', 'activity.kt',
                       'fragment.java', 'fragment.kt']
    # Exclude controller.js/controller.ts from screen suffixes as they're often backend
    has_screen_suffix = any(filename_lower.endswith(suffix) for suffix in screen_suffixes)
    
    screen_prefixes = ['screen', 'page']
    has_screen_prefix = any(filename_lower.startswith(prefix) for prefix in screen_prefixes) and ext in ['.dart', '.vue', '.jsx', '.tsx']
    
    # Frontend extensions
    frontend_extensions = ['.jsx', '.tsx', '.vue', '.svelte', '.dart']
    is_frontend = ext in frontend_extensions
    
    # Android layout
    is_android_layout = '/res/layout/' in filepath_lower and ext == '.xml'
    
    # iOS storyboard/xib
    is_ios_ui = ext in ['.storyboard', '.xib']
    
    # Web templates
    template_extensions = ['.html', '.ejs', '.pug', '.hbs', '.cshtml', '.razor', '.jsp', '.aspx']
    is_web_template = ext in template_extensions
    
    # Stylesheets
    style_extensions = ['.css', '.scss', '.sass', '.less', '.styl']
    is_stylesheet = ext in style_extensions
    
    # HIGH CONFIDENCE SCREEN
    # Exclude backend paths even if they have screen-like patterns
    if is_backend_path:
        # Backend files should never be categorized as screens
        pass  # Will be handled in backend section below
    elif (in_screen_path and is_frontend) or has_screen_suffix or is_android_layout or is_ios_ui:
        subcategory = 'react' if ext in ['.jsx', '.tsx'] else \
                     'vue' if ext == '.vue' else \
                     'flutter' if ext == '.dart' else \
                     'android' if is_android_layout or ext in ['.java', '.kt'] else \
                     'ios' if is_ios_ui or ext == '.swift' else \
                     'web' if is_web_template else 'frontend'
        
        return {
            'category': 'ui_screen',
            'subcategory': subcategory,
            'is_screen': True,
            'confidence': 'high'
        }
    
    # MEDIUM CONFIDENCE SCREEN
    # Frontend files in root or top-level with screen-like names
    if is_frontend and (has_screen_prefix or 'page' in filename_lower or 'view' in filename_lower or 'screen' in filename_lower):
        component_paths = ['/components/', '/widgets/', '/ui/', '/common/', '/shared/']
        in_component_path = any(path in filepath_lower for path in component_paths)
        
        # If in component folder, likely not a screen unless explicitly named
        if in_component_path and not (has_screen_suffix or has_screen_prefix):
            return {
                'category': 'ui_component',
                'subcategory': 'react' if ext in ['.jsx', '.tsx'] else 'vue' if ext == '.vue' else 'frontend',
                'is_screen': False,
                'confidence': 'high'
            }
        
        return {
            'category': 'ui_screen',
            'subcategory': 'react' if ext in ['.jsx', '.tsx'] else 'vue' if ext == '.vue' else 'frontend',
            'is_screen': True,
            'confidence': 'medium'
        }
    
    # UI COMPONENT (not screen)
    if is_frontend:
        return {
            'category': 'ui_component',
            'subcategory': 'react' if ext in ['.jsx', '.tsx'] else 'vue' if ext == '.vue' else 'flutter' if ext == '.dart' else 'frontend',
            'is_screen': False,
            'confidence': 'high'
        }
    
    # STYLESHEET
    if is_stylesheet:
        # Count as UI work if in screens/pages/components folders
        ui_paths = ['/screens/', '/pages/', '/views/', '/components/', '/ui/']
        in_ui_path = any(path in filepath_lower for path in ui_paths)
        
        return {
            'category': 'ui_style',
            'subcategory': 'stylesheet',
            'is_screen': False,
            'confidence': 'high' if in_ui_path else 'medium'
        }
    
    # BACKEND
    backend_extensions = ['.py', '.java', '.go', '.rb', '.php', '.cs', '.rs', '.js', '.ts', '.sql']
    # is_backend_path already defined earlier, but also check extensions
    if is_backend_path or ext in backend_extensions:
        return {
            'category': 'backend',
            'subcategory': ext[1:] if ext else 'unknown',
            'is_screen': False,
            'confidence': 'high'
        }
    
    # CONFIG/DOC
    config_extensions = ['.json', '.yaml', '.yml', '.xml', '.toml', '.ini', '.env']
    doc_extensions = ['.md', '.txt', '.doc', '.pdf']
    if ext in config_extensions:
        return {'category': 'config', 'subcategory': 'config', 'is_screen': False, 'confidence': 'high'}
    if ext in doc_extensions:
        return {'category': 'documentation', 'subcategory': 'doc', 'is_screen': False, 'confidence': 'high'}
    
    # OTHER
    return {
        'category': 'other',
        'subcategory': ext[1:] if ext else 'unknown',
        'is_screen': False,
        'confidence': 'low'
    }


def extract_jira_ids(text: str) -> str:
    """
    Extract JIRA issue IDs from text (commit message, PR title, etc.)
    
    Args:
        text: Text to search for JIRA IDs
        
    Returns:
        Comma-separated list of unique JIRA IDs found, or empty string if none
        
    Examples:
        "DES-123: Fix bug" -> "DES-123"
        "Fixed HR-456 and PCS-789" -> "HR-456,PCS-789"
        "Merge pull request #123 from feature/IT-999" -> "IT-999"
    """
    if not text or not VALID_JIRA_PROJECTS:
        return ''
    
    # Use valid JIRA project codes loaded from jira_config.json
    # Only match these specific project codes to avoid false positives (e.g., OCT-25 dates)
    
    # Build pattern to match only valid project codes
    projects_pattern = '|'.join(VALID_JIRA_PROJECTS)
    pattern = rf'\b({projects_pattern})-(\d{{1,6}})\b'
    
    matches = re.findall(pattern, text)
    
    # Remove duplicates while preserving order
    unique_ids = []
    seen = set()
    for match in matches:
        # match is a tuple (project, number), reconstruct as "PROJECT-NUMBER"
        jira_id = f"{match[0]}-{match[1]}"
        if jira_id not in seen:
            unique_ids.append(jira_id)
            seen.add(jira_id)
    
    return ','.join(unique_ids)


def get_headers(token: Optional[str] = None):
    """
    Get headers for GitHub API requests
    
    Args:
        token: GitHub token (uses GITHUB_TOKEN global if not provided)
        
    Returns:
        Dictionary of request headers
    """
    auth_token = token if token else GITHUB_TOKEN
    return {
        'Authorization': f'Bearer {auth_token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Python-GitHub-Fetcher'
    }


def make_request(url: str, params: Optional[Dict] = None, token: Optional[str] = None) -> Dict:
    """
    Make a request to GitHub API with error handling
    
    Args:
        url: API endpoint URL
        params: Query parameters
        token: GitHub token (uses GITHUB_TOKEN global if not provided)
        
    Returns:
        JSON response as dictionary
        
    Raises:
        Exception: If request fails
    """
    try:
        response = requests.get(url, headers=get_headers(token), params=params, timeout=30)
        
        if response.status_code != 200:
            error_msg = f"GitHub API returned status {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f": {error_detail.get('message', response.text)}"
            except:
                error_msg += f": {response.text}"
            raise Exception(error_msg)
        
        return response.json()
    
    except requests.exceptions.RequestException as e:
        raise Exception(f"Request failed: {str(e)}")


# ============================================================================
# GITHUB API FUNCTIONS
# ============================================================================

def get_pr_review_info(owner: str, repo: str, commit_sha: str, repo_config: Optional[Dict] = None) -> tuple:
    """
    Get pull request review information for a commit
    
    Args:
        owner: Repository owner
        repo: Repository name
        commit_sha: Commit SHA
        repo_config: Repository-specific configuration (token, API URL)
        
    Returns:
        Tuple of (pr_number, approver, review_comments_formatted)
        pr_number: PR number (or empty string if not part of a PR)
        approver: Name of the person who approved the PR (or empty string)
        review_comments_formatted: Formatted string of comments (commenter1:count;commenter2:count;...)
    """
    if repo_config is None:
        repo_config = get_repository_config(GLOBAL_CONFIG_DATA, owner, repo)
    
    api_base = repo_config['githubApiBaseUrl']
    token = repo_config['githubToken']
    
    try:
        # Get PRs associated with this commit
        print(f"      🔍 Checking PR for commit {commit_sha[:7]}...", end='', flush=True)
        prs_url = f"{api_base}/repos/{owner}/{repo}/commits/{commit_sha}/pulls"
        prs = make_request(prs_url, token=token)
        
        if not prs:
            print(" No PR")
            return ('', '', '')
        
        # Use the first PR (usually commits are only in one PR)
        pr = prs[0]
        pr_number = pr['number']
        print(f" PR #{pr_number}", end='', flush=True)
        
        # Get PR reviews
        reviews_url = f"{api_base}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        reviews = make_request(reviews_url, token=token)
        
        # Get PR review comments
        comments_url = f"{api_base}/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        comments = make_request(comments_url, token=token)
        
        # Find approver (last person who approved)
        approver = ''
        for review in reversed(reviews):
            if review.get('state') == 'APPROVED':
                approver = review['user']['login']
                break
        
        # Count comments per commenter
        commenter_counts = {}
        
        # Count review-level comments
        for review in reviews:
            if review.get('body') and review['body'].strip():
                commenter = review['user']['login']
                commenter_counts[commenter] = commenter_counts.get(commenter, 0) + 1
        
        # Count inline review comments
        for comment in comments:
            if comment.get('body') and comment['body'].strip():
                commenter = comment['user']['login']
                commenter_counts[commenter] = commenter_counts.get(commenter, 0) + 1
        
        # Format as commenter1:count1;commenter2:count2;...
        review_comments_formatted = ';'.join([f"{commenter}:{count}" for commenter, count in sorted(commenter_counts.items())]) if commenter_counts else ''
        
        # Print summary with actual data being saved
        total_comment_count = sum(commenter_counts.values())
        unique_commenters = len(commenter_counts)
        
        if total_comment_count > 0:
            print(f" → {total_comment_count} comments from {unique_commenters} reviewers", end='')
        else:
            print(" → No comments", end='')
            
        if approver:
            print(f", approved by {approver}")
        else:
            print()
        
        return (str(pr_number), approver, review_comments_formatted)
        
    except Exception as e:
        # Silently handle errors (commit may not be part of a PR)
        print(f" Error: {str(e)[:50]}")
        return ('', '', '')


def get_repository_commits_batch(owner: str, repo: str, since: Optional[datetime] = None, 
                                  until: Optional[datetime] = None,
                                  batch_callback=None, max_commits: int = None,
                                  repo_config: Optional[Dict] = None) -> List[Dict]:
    """
    Fetch commits from a repository in batches with callback support
    
    Args:
        owner: Repository owner
        repo: Repository name
        since: Only fetch commits after this date (exclusive)
        until: Only fetch commits before this date (exclusive)
        batch_callback: Function to call with each batch of commits
        max_commits: Maximum number of commits to fetch (None for all)
        repo_config: Repository-specific configuration (token, API URL)
        
    Returns:
        List of commit dictionaries with metrics
    """
    if repo_config is None:
        repo_config = get_repository_config(GLOBAL_CONFIG_DATA, owner, repo)
    
    api_base = repo_config['githubApiBaseUrl']
    token = repo_config['githubToken']
    
    url = f"{api_base}/repos/{owner}/{repo}/commits"
    all_commits = []
    page = 1
    per_page = min(100, COMMIT_BATCH_SIZE)  # GitHub API max is 100
    min_commit_date = datetime.strptime(MIN_COMMIT_DATE, '%Y-%m-%d') if MIN_COMMIT_DATE else None
    api_since = since
    if api_since is None and min_commit_date is not None:
        if CHECKPOINT_OVERLAP_DAYS > 0:
            api_since = min_commit_date - timedelta(days=CHECKPOINT_OVERLAP_DAYS)
        else:
            api_since = min_commit_date
    # Guard against the same SHA appearing on multiple pages (pagination overlap)
    seen_shas: set = set()
    
    while True:
        params = {'per_page': per_page, 'page': page}
        if api_since:
            params['since'] = api_since.isoformat() + 'Z'
        if until:
            params['until'] = until.isoformat() + 'Z'
        
        try:
            commits_data = make_request(url, params, token=token)
        except Exception as e:
            print(f"   ⚠️  Error fetching page {page}: {e}")
            break
        
        if not commits_data:
            break
        
        batch_commits = []
        stop_fetching = False
        
        for commit in commits_data:
            # Skip if we've already seen this SHA (pagination overlap guard)
            if commit['sha'] in seen_shas:
                continue
            seen_shas.add(commit['sha'])
            # Get detailed commit info to fetch stats
            commit_url = f"{api_base}/repos/{owner}/{repo}/commits/{commit['sha']}"
            try:
                commit_detail = make_request(commit_url, token=token)
                commit_date = datetime.strptime(commit['commit']['author']['date'], '%Y-%m-%dT%H:%M:%SZ')
                
                # Check if commit is outside the date range - STOP if too old
                if since and commit_date < since:
                    # Reached the checkpoint date - stop fetching
                    stop_fetching = True
                    break
                if until and commit_date >= until:
                    continue
                
                # Check MIN_COMMIT_DATE - STOP if too old
                if min_commit_date is not None:
                    if commit_date < min_commit_date:
                        # Reached the minimum date limit - stop fetching
                        stop_fetching = True
                        break
                
                stats = commit_detail.get('stats', {})
                commit_message = commit['commit']['message'].split('\n')[0]
                full_commit_message = commit['commit']['message']
                
                # Extract JIRA IDs from full commit message
                jira_ids = extract_jira_ids(full_commit_message)
                
                # Only fetch PR review information for merge commits to optimize performance
                is_merge_commit = commit_message.startswith('Merge pull request')
                
                if is_merge_commit:
                    # Get PR review information only for merge commits
                    pr_number, approver, review_comments = get_pr_review_info(owner, repo, commit['sha'], repo_config)
                    count_review_flag = 'true' if pr_number else 'false'
                else:
                    # Skip PR fetch for non-merge commits
                    pr_number = ''
                    approver = ''
                    review_comments = ''
                    count_review_flag = 'false'
                
                # Extract file details for separate tracking
                commit_files = []
                for file_info in commit_detail.get('files', []):
                    filename = file_info.get('filename', '')
                    file_category = categorize_file(filename.split('/')[-1], filename)
                    
                    commit_files.append({
                        'commit_sha': commit['sha'],
                        'date': commit_date,
                        'author': commit['commit']['author']['name'],
                        'author_email': commit['commit']['author']['email'],
                        'repository': f"{owner}/{repo}",
                        'jira_id': jira_ids,
                        'filename': filename.split('/')[-1],
                        'filepath': filename,
                        'file_extension': os.path.splitext(filename)[1],
                        'status': file_info.get('status', 'modified'),
                        'lines_added': file_info.get('additions', 0),
                        'lines_deleted': file_info.get('deletions', 0),
                        'lines_changed': file_info.get('changes', 0),
                        'category': file_category['category'],
                        'subcategory': file_category['subcategory'],
                        'is_screen': file_category['is_screen'],
                        'confidence': file_category['confidence']
                    })
                
                batch_commits.append({
                    'commit_sha': commit['sha'],
                    'date': commit_date,
                    'author': commit['commit']['author']['name'],
                    'author_email': commit['commit']['author']['email'],
                    'repository': f"{owner}/{repo}",
                    'message': commit_message,
                    'jira_id': jira_ids,
                    'files_changed': len(commit_detail.get('files', [])),
                    'lines_added': stats.get('additions', 0),
                    'lines_deleted': stats.get('deletions', 0),
                    'lines_changed': stats.get('total', 0),
                    'pr_number': pr_number,
                    'approver': approver,
                    'review_comments': review_comments,
                    'count_review_flag': count_review_flag,
                    'commit_files': commit_files  # Store file details for later export
                })
            except Exception as e:
                print(f"   ⚠️  Error fetching commit details: {e}")
                continue
        
        all_commits.extend(batch_commits)
        
        # Call batch callback if provided
        if batch_callback and batch_commits:
            batch_callback(batch_commits)
        
        print(f"   📊 Fetched batch {page}: {len(batch_commits)} commits (total: {len(all_commits)})")
        
        # Stop if we've hit a date boundary
        if stop_fetching:
            print(f"   ⏹️  Reached date limit - stopping fetch")
            break
        
        # Check if we've reached the max commits or end of data
        if max_commits and len(all_commits) >= max_commits:
            break
        if len(commits_data) < per_page:
            break
        
        page += 1
        time.sleep(0.5)  # Small delay between pages
    
    return all_commits


def get_commits_by_date_range(owner: str, repo: str, 
                              since: Optional[datetime] = None,
                              until: Optional[datetime] = None,
                              batch_callback=None,
                              repo_config: Optional[Dict] = None) -> List[Dict]:
    """
    Fetch commits within a date range (wrapper for batch function)
    
    Args:
        owner: Repository owner
        repo: Repository name
        since: Only commits after this date
        until: Only commits before this date
        batch_callback: Function to call with each batch of commits
        repo_config: Repository-specific configuration (token, API URL)
        
    Returns:
        List of commit dictionaries
    """
    # Use the batch function
    return get_repository_commits_batch(owner, repo, since=since, until=until, 
                                       batch_callback=batch_callback, repo_config=repo_config)


def list_all_accessible_repositories(per_page: int = 100) -> List[Dict]:
    """
    List all repositories accessible to the authenticated user
    
    Args:
        per_page: Number of repositories per page (max 100)
        
    Returns:
        List of repository dictionaries
    """
    all_repos = []
    page = 1
    
    while True:
        url = f"{GITHUB_API_BASE_URL}/user/repos"
        params = {
            'per_page': per_page,
            'page': page,
            'sort': 'updated',
            'affiliation': 'owner,collaborator,organization_member'
        }
        
        repos_data = make_request(url, params)
        
        if not repos_data:
            break
        
        for repo in repos_data:
            all_repos.append({
                'owner': repo['owner']['login'],
                'repo': repo['name'],
                'full_name': repo['full_name'],
                'description': repo.get('description', ''),
                'private': repo['private'],
                'url': repo['html_url'],
                'language': repo.get('language', 'N/A'),
                'stars': repo['stargazers_count'],
                'forks': repo['forks_count'],
                'updated_at': datetime.strptime(repo['updated_at'], '%Y-%m-%dT%H:%M:%SZ'),
                'default_branch': repo['default_branch']
            })
        
        if len(repos_data) < per_page:
            break
        
        page += 1
    
    return all_repos


def list_user_organizations() -> List[Dict]:
    """
    List all organizations the authenticated user belongs to
    
    Returns:
        List of organization dictionaries
    """
    url = f"{GITHUB_API_BASE_URL}/user/orgs"
    orgs_data = make_request(url)
    
    orgs = []
    for org in orgs_data:
        orgs.append({
            'login': org['login'],
            'name': org.get('name', org['login']),
            'description': org.get('description', ''),
            'url': org['html_url']
        })
    
    return orgs


# ============================================================================
# EXPORT FUNCTIONS
# ============================================================================

def export_to_csv(commits: List[Dict], filename: str = 'github_commits.csv', append: bool = False):
    """Export commits to CSV file
    
    Args:
        commits: List of commit dictionaries
        filename: Output filename
        append: If True, append to existing file; if False, overwrite
    """
    if not commits:
        return
    
    # Remove commit_files from commits before export (it's exported separately)
    commits_for_export = []
    for commit in commits:
        commit_copy = commit.copy()
        commit_copy.pop('commit_files', None)
        commits_for_export.append(commit_copy)
    
    fieldnames = list(commits_for_export[0].keys())
    file_exists = os.path.exists(filename) and append

    # Dedup: when appending, filter out commits already present.
    # Prefer commit_sha as the dedup key; fall back to
    # (date, author_email, message, lines_added, lines_deleted, lines_changed).
    if file_exists:
        try:
            read_cols = ['date', 'author_email', 'message', 'lines_added', 'lines_deleted', 'lines_changed']
            existing_df_cols = list(pd.read_csv(filename, nrows=0).columns)
            has_sha_col = 'commit_sha' in existing_df_cols
            if has_sha_col:
                read_cols.append('commit_sha')
            read_cols = [c for c in read_cols if c in existing_df_cols]
            existing_df = pd.read_csv(filename, usecols=read_cols)
            existing_shas: set = set()
            existing_fallback_keys: set = set()
            if has_sha_col:
                existing_shas = set(existing_df['commit_sha'].dropna().astype(str))
            existing_fallback_keys = set(
                zip(existing_df['date'].astype(str),
                    existing_df['author_email'].astype(str),
                    existing_df['message'].astype(str),
                    existing_df.get('lines_added', pd.Series(dtype=str)).fillna('').astype(str),
                    existing_df.get('lines_deleted', pd.Series(dtype=str)).fillna('').astype(str),
                    existing_df.get('lines_changed', pd.Series(dtype=str)).fillna('').astype(str))
            )
            before = len(commits_for_export)
            filtered = []
            for c in commits_for_export:
                sha = str(c.get('commit_sha', ''))
                if sha and has_sha_col:
                    if sha not in existing_shas:
                        filtered.append(c)
                else:
                    key = (
                        str(c.get('date', '')),
                        str(c.get('author_email', '')),
                        str(c.get('message', '')),
                        str(c.get('lines_added', '')),
                        str(c.get('lines_deleted', '')),
                        str(c.get('lines_changed', '')),
                    )
                    if key not in existing_fallback_keys:
                        filtered.append(c)
            commits_for_export = filtered
            skipped = before - len(commits_for_export)
            if skipped:
                print(f"   ⚠ Skipped {skipped} duplicate commits (already in {filename})")
        except Exception:
            pass  # If read fails, proceed and append anyway

    if not commits_for_export:
        print(f"   ✓ No new commits to append (all duplicates)")
        return

    mode = 'a' if file_exists else 'w'
    _ensure_parent_dir(filename)

    # Schema-upgrade guard: if the existing file has fewer columns than the new
    # commits (e.g. commit_sha was added), rewrite the file with the union schema.
    if file_exists:
        existing_cols = list(pd.read_csv(filename, nrows=0).columns)
        new_cols = [c for c in fieldnames if c not in existing_cols]
        if new_cols:
            existing_df = pd.read_csv(filename)
            for col in new_cols:
                insert_pos = 0 if col == 'commit_sha' else len(existing_df.columns)
                existing_df.insert(insert_pos, col, '')
            fieldnames = list(existing_df.columns)
            existing_df.to_csv(filename, index=False)
            print(f"   Schema upgraded: added columns {new_cols} to {filename}")

    with open(filename, mode, newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerows(commits_for_export)

    action = "Appended" if file_exists else "Exported"
    print(f"   💾 {action} {len(commits_for_export)} commits to {filename}")


def export_files_to_csv(commits: List[Dict], filename: str = 'github_commit_files.csv', append: bool = False):
    """Export file details to separate CSV file
    
    Args:
        commits: List of commit dictionaries (with commit_files field)
        filename: Output filename
        append: If True, append to existing file; if False, overwrite
    """
    all_files = []
    for commit in commits:
        commit_files = commit.get('commit_files', [])
        all_files.extend(commit_files)
    
    if not all_files:
        return
    
    fieldnames = [
        'commit_sha', 'date', 'author', 'author_email', 'repository', 'jira_id',
        'filename', 'filepath', 'file_extension', 'status',
        'lines_added', 'lines_deleted', 'lines_changed',
        'category', 'subcategory', 'is_screen', 'confidence'
    ]
    file_exists = os.path.exists(filename) and append
    
    mode = 'a' if file_exists else 'w'
    _ensure_parent_dir(filename)
    with open(filename, mode, newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(all_files)
    
    action = "Appended" if file_exists else "Exported"
    print(f"   💾 {action} {len(all_files)} file changes to {filename}")





# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

def fetch_all_commits(use_checkpoint: bool = True):
    """Fetch commits from all configured repositories with incremental saving
    
    Args:
        use_checkpoint: If True, only fetch commits after the last checkpoint
    """
    print(f"\n{'='*60}")
    print("Fetching commits from all repositories...")
    if use_checkpoint:
        print("Using checkpoint for incremental fetch")
    else:
        print("Full fetch - checkpoint ignored")
    print(f"Mode: Incremental save after each repository")
    print(f"{'='*60}\n")
    
    # Load checkpoint data
    checkpoint = load_checkpoint() if use_checkpoint else {}
    
    # If full fetch, reset the output file
    if not use_checkpoint and EXPORT_FORMAT == 'csv' and os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        print(f"🗑️  Removed existing {OUTPUT_FILE} for full fetch\n")
    
    total_commits = 0
    total_repos = len(REPOSITORY_LIST)
    file_exists = os.path.exists(OUTPUT_FILE) if EXPORT_FORMAT == 'csv' else False
    
    for idx, repo_info in enumerate(REPOSITORY_LIST, 1):
        owner = repo_info['owner']
        repo = repo_info['repo']
        repo_key = f"{owner}/{repo}"
        
        print(f"📦 [{idx}/{total_repos}] Processing {repo_key}...")
        
        try:
            # Load checkpoint info for this repository
            repo_checkpoint = checkpoint.get(repo_key, {}) if use_checkpoint else {}
            
            # Handle old checkpoint format (string) - convert to new format
            if isinstance(repo_checkpoint, str):
                repo_checkpoint = {'newest': repo_checkpoint}
            
            since_date = None
            until_date = None
            fetch_mode = None
            
            if 'newest' in repo_checkpoint and 'oldest' not in repo_checkpoint:
                # Incremental fetch: repository was fully fetched before
                since_date = datetime.fromisoformat(repo_checkpoint['newest'])
                fetch_mode = 'incremental'
                if CHECKPOINT_OVERLAP_DAYS > 0:
                    fetch_since = since_date - timedelta(days=CHECKPOINT_OVERLAP_DAYS)
                    print(
                        f"   ℹ️  Incremental fetch - commits after {fetch_since.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"(checkpoint overlap: {CHECKPOINT_OVERLAP_DAYS} days; checkpoint={since_date.strftime('%Y-%m-%d %H:%M:%S')})"
                    )
                    since_date = fetch_since
                else:
                    print(f"   ℹ️  Incremental fetch - commits after {since_date.strftime('%Y-%m-%d %H:%M:%S')}")
            elif 'oldest' in repo_checkpoint:
                # Resuming incomplete first-time fetch
                until_date = datetime.fromisoformat(repo_checkpoint['oldest'])
                fetch_mode = 'resume'
                print(f"   ℹ️  Resuming fetch - commits before {until_date.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                # First-time fetch
                fetch_mode = 'first-time'
                if MIN_COMMIT_DATE and CHECKPOINT_OVERLAP_DAYS > 0:
                    min_fetch_date = datetime.strptime(MIN_COMMIT_DATE, '%Y-%m-%d') - timedelta(days=CHECKPOINT_OVERLAP_DAYS)
                    print(
                        f"   ℹ️  First-time fetch - commits after {min_fetch_date.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"(MIN_COMMIT_DATE={MIN_COMMIT_DATE}; overlap={CHECKPOINT_OVERLAP_DAYS} days)"
                    )
                elif MIN_COMMIT_DATE:
                    print(f"   ℹ️  First-time fetch - commits after {MIN_COMMIT_DATE}")
                else:
                    print(f"   ℹ️  First-time fetch - all commits")
            
            # Track newest and oldest dates
            repo_newest_date = None
            repo_oldest_date = None
            first_batch_processed = False
            
            # If resuming, start with the existing newest date from checkpoint
            if fetch_mode in ['first-time', 'resume'] and 'newest' in repo_checkpoint:
                repo_newest_date = datetime.fromisoformat(repo_checkpoint['newest'])
            
            # Define callback to save batches
            def batch_callback(batch_commits):
                nonlocal file_exists, total_commits, repo_newest_date, repo_oldest_date, checkpoint, first_batch_processed
                # Cross-repo session guard: drop SHAs already written in this run
                if not hasattr(fetch_all_commits, '_global_seen_shas'):
                    fetch_all_commits._global_seen_shas = set()
                deduped = []
                for c in batch_commits:
                    sha = str(c.get('commit_sha', ''))
                    if sha and sha in fetch_all_commits._global_seen_shas:
                        continue
                    if sha:
                        fetch_all_commits._global_seen_shas.add(sha)
                    deduped.append(c)
                skipped = len(batch_commits) - len(deduped)
                if skipped:
                    print(f"   ⚠ Skipped {skipped} cross-repo duplicate commit(s)")
                batch_commits = deduped
                if not batch_commits:
                    return
                if EXPORT_FORMAT == 'csv':
                    export_to_csv(batch_commits, OUTPUT_FILE, append=file_exists)
                    
                    # Also export file details to separate CSV
                    files_output = _derive_commit_files_output(OUTPUT_FILE)
                    export_files_to_csv(batch_commits, files_output, append=file_exists)
                    
                    file_exists = True
                total_commits += len(batch_commits)
                
                # Track newest and oldest dates in this batch
                if batch_commits:
                    batch_newest = max(c['date'] for c in batch_commits)
                    batch_oldest = min(c['date'] for c in batch_commits)
                    
                    # For first-time/resume: capture newest ONLY from first batch (commits are newest-first)
                    # For incremental: update newest with each batch (going forward in time)
                    if fetch_mode == 'incremental':
                        # Incremental mode: update newest as we find newer commits
                        if repo_newest_date is None or batch_newest > repo_newest_date:
                            repo_newest_date = batch_newest
                    else:
                        # First-time/resume: capture newest only from first batch
                        if not first_batch_processed:
                            repo_newest_date = batch_newest
                            first_batch_processed = True
                    
                    # Always update oldest as we paginate backwards
                    if repo_oldest_date is None or batch_oldest < repo_oldest_date:
                        repo_oldest_date = batch_oldest
                    
                    # Update checkpoint after each batch
                    if use_checkpoint:
                        if fetch_mode == 'incremental':
                            # Only update newest for incremental fetches
                            checkpoint[repo_key] = {'newest': repo_newest_date.isoformat()}
                        else:
                            # For first-time/resume, track oldest and the true newest (from first batch)
                            checkpoint[repo_key] = {'oldest': repo_oldest_date.isoformat()}
                            if repo_newest_date:
                                checkpoint[repo_key]['newest'] = repo_newest_date.isoformat()
                        save_checkpoint(checkpoint)
            
            # Fetch commits with batch processing
            repo_config = get_repository_config(GLOBAL_CONFIG_DATA, owner, repo)
            if repo_config is None:
                print(f"   ❌ Error: No GitHub token configured for {repo_key}")
                print(f"      Please add 'githubToken' to the default section or repository-specific section in github_config.json")
                continue
            
            commits = get_repository_commits_batch(owner, repo, since=since_date, until=until_date,
                                                  batch_callback=batch_callback, repo_config=repo_config)
            
            print(f"   ✅ Completed: {len(commits)} commits")
            
            # Mark fetch as complete by setting newest only (remove oldest)
            if use_checkpoint and repo_newest_date:
                if fetch_mode in ['first-time', 'resume']:
                    # First fetch complete - keep only newest, remove oldest to mark as complete
                    checkpoint[repo_key] = {'newest': repo_newest_date.isoformat()}
                    save_checkpoint(checkpoint)
                    print(f"   💾 Fetch complete. Checkpoint: {repo_newest_date.strftime('%Y-%m-%d %H:%M:%S')}")
                elif fetch_mode == 'incremental' and commits:
                    print(f"   💾 Incremental complete. Latest: {repo_newest_date.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Rate limiting: sleep between repository fetches
            if idx < total_repos:
                time.sleep(REPO_FETCH_DELAY)
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            continue
    
    print(f"\n{'='*60}")
    print(f"Total commits fetched: {total_commits}")
    print(f"Data saved to: {OUTPUT_FILE}")
    print(f"{'='*60}\n")
    
    return total_commits


def fetch_recent_commits(days: int = 7):
    """Fetch commits from the last N days with rate limiting"""
    print(f"\n{'='*60}")
    print(f"Fetching commits from last {days} days...")
    print(f"{'='*60}\n")
    
    since = datetime.utcnow() - timedelta(days=days)
    all_commits = []
    total_repos = len(REPOSITORY_LIST)
    
    for idx, repo_info in enumerate(REPOSITORY_LIST, 1):
        owner = repo_info['owner']
        repo = repo_info['repo']
        
        print(f"📦 [{idx}/{total_repos}] Fetching recent commits from {owner}/{repo}...")
        
        try:
            repo_config = get_repository_config(GLOBAL_CONFIG_DATA, owner, repo)
            if repo_config is None:
                print(f"   ❌ Error: No GitHub token configured for {owner}/{repo}")
                print(f"      Skipping repository - please add 'githubToken' to github_config.json")
                continue
            
            commits = get_commits_by_date_range(owner, repo, since=since, repo_config=repo_config)
            all_commits.extend(commits)
            print(f"   ✅ Fetched {len(commits)} commits")
            
            # Rate limiting: sleep between repository fetches
            if idx < total_repos:
                time.sleep(REPO_FETCH_DELAY)
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            continue
    
    print(f"\n{'='*60}")
    print(f"Total recent commits fetched: {len(all_commits)}")
    print(f"{'='*60}\n")
    
    return all_commits


def list_repositories():
    """List all accessible repositories"""
    print(f"\n{'='*60}")
    print("Fetching accessible repositories...")
    print(f"{'='*60}\n")
    
    try:
        repos = list_all_accessible_repositories()
        
        print(f"Found {len(repos)} accessible repositories:\n")
        
        for repo in sorted(repos, key=lambda x: x['updated_at'], reverse=True)[:20]:
            description = (repo['description'] or '')[:50]
            language = repo['language'] or 'N/A'
            print(f"  • {repo['full_name']:<40} ({language:<15}) - {description}")
        
        if len(repos) > 20:
            print(f"\n  ... and {len(repos) - 20} more")
        
        # Save files to output directory
        output_dir = os.path.join(PROJECT_ROOT, 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        # Save to JSON file
        json_path = os.path.join(output_dir, 'accessible_repositories.json')
        with open(json_path, 'w') as f:
            json.dump(repos, f, indent=2, default=str)
        
        # Save to Python-formatted file for REPOSITORY_LIST
        py_path = os.path.join(output_dir, 'repository_list.py')
        with open(py_path, 'w') as f:
            f.write("REPOSITORY_LIST = [\n")
            for repo in repos:
                f.write(f"    {{'owner': '{repo['owner']}', 'repo': '{repo['repo']}'}},\n")
            f.write("]\n")
        
        # Save to CSV file
        csv_path = os.path.join(output_dir, 'accessible_repositories.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['owner', 'repo', 'full_name', 'description', 'private', 'language', 'stars', 'forks', 'url']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for repo in repos:
                writer.writerow({
                    'owner': repo['owner'],
                    'repo': repo['repo'],
                    'full_name': repo['full_name'],
                    'description': repo['description'],
                    'private': repo['private'],
                    'language': repo['language'],
                    'stars': repo['stars'],
                    'forks': repo['forks'],
                    'url': repo['url']
                })
        
        print(f"\n✅ Full list saved to output/:")
        print(f"   - accessible_repositories.json (complete data)")
        print(f"   - accessible_repositories.csv (table format)")
        print(f"   - repository_list.py (Python REPOSITORY_LIST format)")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")


def reset_checkpoint():
    """Reset the checkpoint file and output data file"""
    files_removed = []
    
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        files_removed.append(CHECKPOINT_FILE)
    
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        files_removed.append(OUTPUT_FILE)
    
    if files_removed:
        print(f"✅ Reset complete. Removed: {', '.join(files_removed)}")
        print("   Next fetch will be a full fetch from the beginning.")
    else:
        print(f"ℹ️  No checkpoint or output files found")


def show_checkpoint():
    """Display the current checkpoint status"""
    checkpoint = load_checkpoint()
    
    if not checkpoint:
        print("ℹ️  No checkpoint data found")
        return
    
    print(f"\n{'='*60}")
    print("Checkpoint Status")
    print(f"{'='*60}\n")
    
    for repo_key, checkpoint_entry in sorted(checkpoint.items()):
        last_date = None

        if isinstance(checkpoint_entry, str):
            last_date = checkpoint_entry
        elif isinstance(checkpoint_entry, dict):
            last_date = checkpoint_entry.get('newest') or checkpoint_entry.get('oldest')

        if not last_date:
            display_date = 'N/A'
        else:
            try:
                display_date = datetime.fromisoformat(last_date).strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                display_date = str(last_date)

        print(f"  • {repo_key:<50} {display_date}")
    
    print(f"\n{'='*60}")
    print(f"Total repositories tracked: {len(checkpoint)}")
    print(f"{'='*60}\n")


def test_connection():
    """Test GitHub API connection"""
    print(f"\n{'='*60}")
    print("Testing GitHub connection...")
    print(f"{'='*60}\n")
    
    try:
        if not REPOSITORY_LIST:
            print("❌ No repositories configured in REPOSITORY_LIST")
            return
        
        test_repo = REPOSITORY_LIST[0]
        print(f"Testing with repository: {test_repo['owner']}/{test_repo['repo']}\n")
        
        repo_config = get_repository_config(GLOBAL_CONFIG_DATA, test_repo['owner'], test_repo['repo'])
        if repo_config is None:
            print("❌ No GitHub token configured")
            print("   Please add 'githubToken' to the default section in github_config.json")
            return
        
        commits = get_repository_commits_batch(test_repo['owner'], test_repo['repo'], until=None, max_commits=1, repo_config=repo_config)
        
        if commits:
            print("✅ Connection successful!")
            print(f"\nSample commit:")
            print(f"  Author: {commits[0]['author']}")
            print(f"  Date: {commits[0]['date']}")
            print(f"  Message: {commits[0]['message']}")
        else:
            print("⚠️  Connected but no commits found")
            
    except Exception as e:
        print(f"❌ Connection failed: {str(e)}")


# ============================================================================
# CLI INTERFACE
# ============================================================================

def parse_config_args(args: List[str]) -> Dict[str, str]:
    """Parse command-line arguments in key=value format
    
    Args:
        args: List of command-line arguments
        
    Returns:
        Dictionary of configuration overrides
    """
    config_overrides = {}
    for arg in args:
        if '=' in arg and not arg.startswith('--'):
            key, value = arg.split('=', 1)
            config_overrides[key.lower()] = value
    return config_overrides


def apply_config_overrides(config_overrides: Dict[str, str]):
    """Apply configuration overrides from command-line arguments
    
    Args:
        config_overrides: Dictionary of configuration key-value pairs
    """
    global GITHUB_API_BASE_URL, OUTPUT_FILE, CHECKPOINT_FILE
    global REPO_FETCH_DELAY, COMMIT_BATCH_SIZE, MIN_COMMIT_DATE, CHECKPOINT_OVERLAP_DAYS
    global REPOSITORY_LIST, REPOSITORY_LIST_FILE
    global GITHUB_TOKEN
    
    if 'token' in config_overrides:
        GITHUB_TOKEN = config_overrides['token']
        print(f"   🔧 GitHub token: {GITHUB_TOKEN[:8]}...{GITHUB_TOKEN[-4:]}")
    
    if 'api_url' in config_overrides:
        GITHUB_API_BASE_URL = config_overrides['api_url']
        print(f"   🔧 API URL: {GITHUB_API_BASE_URL}")
    
    if 'output_file' in config_overrides:
        OUTPUT_FILE = _resolve_path(config_overrides['output_file'])
        print(f"   🔧 Output file: {OUTPUT_FILE}")
    
    if 'checkpoint_file' in config_overrides:
        CHECKPOINT_FILE = _resolve_path(config_overrides['checkpoint_file'])
        print(f"   🔧 Checkpoint file: {CHECKPOINT_FILE}")
    
    if 'repo_delay' in config_overrides:
        REPO_FETCH_DELAY = float(config_overrides['repo_delay'])
        print(f"   🔧 Repository fetch delay: {REPO_FETCH_DELAY}s")
    
    if 'batch_size' in config_overrides:
        COMMIT_BATCH_SIZE = int(config_overrides['batch_size'])
        print(f"   🔧 Commit batch size: {COMMIT_BATCH_SIZE}")
    
    if 'min_date' in config_overrides:
        MIN_COMMIT_DATE = config_overrides['min_date'] if config_overrides['min_date'].lower() != 'none' else None
        print(f"   🔧 Minimum commit date: {MIN_COMMIT_DATE or 'None (all commits)'}")

    if 'overlap_days' in config_overrides:
        CHECKPOINT_OVERLAP_DAYS = max(0, int(config_overrides['overlap_days']))
        print(f"   🔧 Checkpoint overlap days: {CHECKPOINT_OVERLAP_DAYS}")
    
    if 'repo_list_file' in config_overrides:
        REPOSITORY_LIST_FILE = _resolve_path(config_overrides['repo_list_file'])
        REPOSITORY_LIST = load_repository_list_from_file(REPOSITORY_LIST_FILE)
        print(f"   🔧 Repository list file: {REPOSITORY_LIST_FILE} ({len(REPOSITORY_LIST)} repositories)")


def main():
    """Main CLI interface"""
    if len(sys.argv) < 2:
        print("""
GitHub Commits Fetcher - Python Script

Usage:
    python github_fetch.py <command> [config_options] [flags]

Commands:
    test                Test GitHub API connection
    list                List all accessible repositories
    fetch [--full]      Fetch commits (incremental by default, --full for complete fetch)
    recent [days]       Fetch commits from last N days (default: 7)
    checkpoint          Show checkpoint status
    reset-checkpoint    Reset checkpoint (next fetch will be complete)

Configuration Options (key=value format):
    token=<token>           GitHub personal access token (overrides GITHUB_TOKEN env var)
    api_url=<url>           GitHub API base URL (default: https://github01.hclpnp.com/api/v3)
    output_file=<file>      Output filename (default: github_commits.csv)
    checkpoint_file=<file>  Checkpoint filename (default: fetch_checkpoint.json)
    repo_delay=<seconds>    Delay between repository fetches (default: 2)
    batch_size=<number>     Commit batch size (default: 5)
    min_date=<YYYY-MM-DD>   Minimum commit date filter (default: 2025-04-01, use 'none' for all)
    overlap_days=<number>   Checkpoint overlap window in days (default: 15)
    repo_list_file=<file>   JSON file with repository list (overrides REPOSITORY_LIST in code)
    
Examples:
    python github_fetch.py test
    python github_fetch.py list
    python github_fetch.py fetch token=ghp_xxxxxxxxxxxx
    python github_fetch.py fetch
    python github_fetch.py fetch --full
    python github_fetch.py fetch output_file=my_commits.csv min_date=2025-01-01
    python github_fetch.py fetch min_date=none batch_size=10
    python github_fetch.py fetch overlap_days=15
    python github_fetch.py fetch repo_list_file=my_repos.json
    python github_fetch.py recent 14 output_file=recent.csv
    python github_fetch.py checkpoint
    python github_fetch.py reset-checkpoint

Repository List File Format (JSON):
    [
        {"owner": "org1", "repo": "repo1"},
        {"owner": "org2", "repo": "repo2"}
    ]

Configuration (defaults can be overridden via command line):
    - GITHUB_TOKEN: Set via environment variable
    - GITHUB_API_BASE_URL: {GITHUB_API_BASE_URL}
    - OUTPUT_FILE: {OUTPUT_FILE}
    - MIN_COMMIT_DATE: {MIN_COMMIT_DATE}
    - CHECKPOINT_OVERLAP_DAYS: {CHECKPOINT_OVERLAP_DAYS}
    - COMMIT_BATCH_SIZE: {COMMIT_BATCH_SIZE}
    - REPO_FETCH_DELAY: {REPO_FETCH_DELAY}s

Checkpoint Feature:
    The script automatically saves the last fetch date for each repository.
    Subsequent fetches only retrieve new commits, making it efficient for scheduled runs.
        """)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    # Parse configuration overrides
    config_overrides = parse_config_args(sys.argv[2:])
    if config_overrides:
        print(f"\n📝 Applying configuration overrides:")
        apply_config_overrides(config_overrides)
        print()
    
    if command == 'test':
        test_connection()
    
    elif command == 'list':
        list_repositories()
    
    elif command == 'fetch':
        # Check for --full flag
        use_checkpoint = '--full' not in sys.argv
        try:
            with acquire_fetch_lock():
                fetch_all_commits(use_checkpoint=use_checkpoint)
        except RuntimeError as e:
            print(f"⚠️  {e}. Skipping this run.")
    
    elif command == 'recent':
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        try:
            with acquire_fetch_lock():
                commits = fetch_recent_commits(days)
                if commits:
                    filename = f'recent_commits_{days}days.csv'
                    export_to_csv(commits, filename)
                    
                    # Also export file details
                    files_filename = filename.replace('.csv', '_files.csv')
                    export_files_to_csv(commits, files_filename)
        except RuntimeError as e:
            print(f"⚠️  {e}. Skipping this run.")
    
    elif command == 'checkpoint':
        show_checkpoint()
    
    elif command == 'reset-checkpoint':
        reset_checkpoint()
    
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
