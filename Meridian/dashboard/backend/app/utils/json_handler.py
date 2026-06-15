"""
JSON file utilities with atomic operations for safe concurrent access.
"""
import json
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def ensure_dir(filepath: str) -> None:
    """Ensure parent directory exists"""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)


def load_json_safe(filepath: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Load JSON file safely with fallback to default.
    
    Args:
        filepath: Path to JSON file
        default: Default value if file doesn't exist
    
    Returns:
        Parsed JSON dict or default
    """
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"JSON file not found: {filepath}, using default")
        return default or {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return default or {}


def save_json_atomic(filepath: str, data: Dict[str, Any]) -> None:
    """
    Write JSON file atomically using temp file + rename.
    
    This ensures data safety in case of concurrent access or process crashes.
    
    Args:
        filepath: Path to JSON file
        data: Data to write
    """
    filepath = Path(filepath)
    ensure_dir(str(filepath))
    
    try:
        # Write to temp file first
        with tempfile.NamedTemporaryFile(
            mode='w',
            dir=filepath.parent,
            delete=False,
            suffix='.tmp',
            encoding='utf-8'
        ) as tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp_path = tmp.name
        
        # Atomic rename (OS-level guarantee)
        Path(tmp_path).replace(filepath)
        logger.info(f"Saved JSON file: {filepath}")
    except Exception as e:
        logger.error(f"Failed to save JSON file {filepath}: {e}")
        raise


def get_next_id(items_list: list) -> int:
    """
    Get next available ID from a list of items.
    
    Args:
        items_list: List of items with 'id' field
    
    Returns:
        Next ID (max_id + 1)
    """
    if not items_list:
        return 1
    return max(item.get('id', 0) for item in items_list) + 1
