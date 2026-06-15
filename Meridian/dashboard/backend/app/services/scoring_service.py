"""
Scoring Service for KPI Performance Evaluation

Calculates overall scores for individuals, teams, and scrums based on:
- Green KPI percentage per category (Input, Output, Quality, Hygiene)
- Configurable weightages for each category
- Configurable status weights (Green, Orange, Red)
- Max score of 100
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class ScoringService:
    """Service to calculate performance scores based on KPI categories"""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize scoring service with configuration"""
        if config_path is None:
            # Path: dashboard/backend/app/services/scoring_service.py -> ../../../../config/scoring_config.json
            config_path = Path(__file__).parent.parent.parent.parent.parent / "config" / "scoring_config.json"
        
        self.config_path = Path(config_path)
        self.weightages, self.status_weights, self.role_weights, self.aggregation_role_weights, self.rog_thresholds, self.score_display_thresholds = self._load_config()
    
    def _load_config(self) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float]]:
        """Load scoring configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)

            weightages = config.get('weightages', {
                'Input': 10,
                'Output': 50,
                'Quality': 30,
                'Hygiene': 10
            })
            status_weights = config.get('status_weights', {
                'Green': 1.0,
                'Orange': 0.75,
                'Red': 0.0
            })
            role_weights = config.get('role_weights', {
                'Primary': 20,
                'Secondary': 10,
                'All': 5,
                'Common': 3,
                'Other': 1
            })
            aggregation_role_weights = config.get('aggregation_role_weights', {
                'specific': 10,
                'non_specific': 5
            })
            rog_thresholds = config.get('rog_thresholds', {
                'green_threshold': 100.0,
                'orange_threshold': 70.0
            })
            score_display_thresholds = config.get('score_display_thresholds', {
                'green_min': 70.0,
                'orange_min': 36.0,
                'red_max': 35.0
            })
            return weightages, status_weights, role_weights, aggregation_role_weights, rog_thresholds, score_display_thresholds
        except (FileNotFoundError, json.JSONDecodeError):
            # Return defaults if config is unavailable
            return {
                'Input': 10,
                'Output': 50,
                'Quality': 30,
                'Hygiene': 10
            }, {
                'Green': 1.0,
                'Orange': 0.75,
                'Red': 0.0
            }, {
                'Primary': 20,
                'Secondary': 10,
                'All': 5,
                'Common': 3,
                'Other': 1
            }, {
                'specific': 10,
                'common': 5
            }, {
                'green_threshold': 100.0,
                'orange_threshold': 70.0
            }, {
                'green_min': 70.0,
                'orange_min': 36.0,
                'red_max': 35.0
            }
    
    def save_config(
        self,
        weightages: Dict[str, float],
        status_weights: Optional[Dict[str, float]] = None,
        rog_thresholds: Optional[Dict[str, float]] = None,
        score_display_thresholds: Optional[Dict[str, float]] = None,
        role_weights: Optional[Dict[str, float]] = None,
        aggregation_role_weights: Optional[Dict[str, float]] = None
    ) -> bool:
        """Save updated scoring configuration to file."""
        try:
            # Validate that weightages sum to 100
            total = sum(weightages.values())
            if abs(total - 100) > 0.01:  # Allow small floating point differences
                raise ValueError(f"Weightages must sum to 100, got {total}")
            
            # Ensure all required categories are present
            required_categories = {'Input', 'Output', 'Quality', 'Hygiene'}
            if set(weightages.keys()) != required_categories:
                raise ValueError(f"Weightages must contain exactly: {required_categories}")
            
            # If status_weights provided, validate them
            if status_weights is not None:
                required_statuses = {'Green', 'Orange', 'Red'}
                if set(status_weights.keys()) != required_statuses:
                    raise ValueError(f"Status weights must contain exactly: {required_statuses}")
                
                # Validate that weights are between 0 and 1
                for status, weight in status_weights.items():
                    if not (0 <= weight <= 1):
                        raise ValueError(f"Status weight for {status} must be between 0 and 1, got {weight}")
            else:
                # Use existing status weights if not provided
                status_weights = self.status_weights

            # If role_weights provided, validate them
            if role_weights is not None:
                required_role_weights = {'Primary', 'Secondary', 'All', 'Common', 'Other'}
                if set(role_weights.keys()) != required_role_weights:
                    raise ValueError(f"Role weights must contain exactly: {required_role_weights}")

                for role_name, weight in role_weights.items():
                    if not (0 <= weight <= 20):
                        raise ValueError(f"Role weight for {role_name} must be between 0 and 20, got {weight}")
            else:
                role_weights = self.role_weights

            # If aggregation_role_weights provided, validate them
            if aggregation_role_weights is not None:
                required_agg_weights = {'specific', 'non_specific'}
                if set(aggregation_role_weights.keys()) != required_agg_weights:
                    raise ValueError(f"Aggregation role weights must contain exactly: {required_agg_weights}")

                for role_name, weight in aggregation_role_weights.items():
                    if not (0 <= weight <= 20):
                        raise ValueError(f"Aggregation role weight for {role_name} must be between 0 and 20, got {weight}")
            else:
                aggregation_role_weights = self.aggregation_role_weights
            
            # If ROG thresholds provided, validate them
            if rog_thresholds is not None:
                required_thresholds = {'green_threshold', 'orange_threshold'}
                if not all(key in rog_thresholds for key in required_thresholds):
                    raise ValueError(f"ROG thresholds must contain: {required_thresholds}")
                
                # Validate threshold values and ordering
                green = rog_thresholds.get('green_threshold', 100.0)
                orange = rog_thresholds.get('orange_threshold', 80.0)
                
                if not (0 <= orange <= green <= 200):
                    raise ValueError(f"Thresholds must satisfy: 0 <= orange_threshold ({orange}) <= green_threshold ({green}) <= 200")
            else:
                # Use existing thresholds if not provided
                rog_thresholds = self.rog_thresholds
            
            # If score display thresholds provided, validate them
            if score_display_thresholds is not None:
                required_display = {'green_min', 'orange_min', 'red_max'}
                if not all(key in score_display_thresholds for key in required_display):
                    raise ValueError(f"Score display thresholds must contain: {required_display}")
                
                green_min = score_display_thresholds['green_min']
                orange_min = score_display_thresholds['orange_min']
                red_max = score_display_thresholds['red_max']
                
                if not (0 <= red_max < orange_min < green_min <= 100):
                    raise ValueError(f"Display thresholds must satisfy: 0 <= red_max ({red_max}) < orange_min ({orange_min}) < green_min ({green_min}) <= 100")
            else:
                # Use existing display thresholds if not provided
                score_display_thresholds = self.score_display_thresholds
            
            # Load existing config and update
            config = {}
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
            
            config['weightages'] = weightages
            config['status_weights'] = status_weights
            config['role_weights'] = role_weights
            config['aggregation_role_weights'] = aggregation_role_weights
            config['rog_thresholds'] = {
                'green_threshold': rog_thresholds['green_threshold'],
                'orange_threshold': rog_thresholds['orange_threshold']
            }
            config['score_display_thresholds'] = {
                'green_min': score_display_thresholds['green_min'],
                'orange_min': score_display_thresholds['orange_min'],
                'red_max': score_display_thresholds['red_max']
            }
            config['version'] = '2.2'
            config['calculation_method'] = 'role_weighted_status'
            config['formula'] = (
                f"Individual: category_score = sum(role_weight x status_credit) / sum(role_weight) x weightage "
                f"using status credits Green={status_weights['Green']}, Orange={status_weights['Orange']}, Red={status_weights['Red']} "
                f"and role weights Primary={role_weights['Primary']}, Secondary={role_weights['Secondary']}, "
                f"All={role_weights['All']}, Common={role_weights['Common']}, Other={role_weights['Other']}. "
                f"Team/Scrum use role weights specific={aggregation_role_weights['specific']} and non_specific={aggregation_role_weights['non_specific']}. "
                f"Overall = sum of category scores (max 100)."
            )
            
            # Save updated config
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            self.weightages = weightages
            self.status_weights = status_weights
            self.role_weights = role_weights
            self.aggregation_role_weights = aggregation_role_weights
            self.rog_thresholds = rog_thresholds
            self.score_display_thresholds = score_display_thresholds
            return True
        except Exception as e:
            print(f"Error saving scoring config: {e}")
            return False
    
    def get_config(self) -> Dict:
        """Get current configuration including weightages, status weights, ROG thresholds, and score display thresholds"""
        return {
            'weightages': self.weightages.copy(),
            'status_weights': self.status_weights.copy(),
            'role_weights': self.role_weights.copy(),
            'aggregation_role_weights': self.aggregation_role_weights.copy(),
            'rog_thresholds': self.rog_thresholds.copy(),
            'score_display_thresholds': self.score_display_thresholds.copy()
        }
    
    def calculate_score(self, kpi_data: List[Dict]) -> Dict:
        """
        Calculate overall score based on KPI performance with role-based weighting.

        Individual score formula (uses role_type per KPI):
            category_score = sum(role_weight × status_credit) / sum(role_weight) × category_weightage
            role_weight: Primary=20, Secondary=10, All=5, Common=3, Other=1

        Team/Scrum aggregation formula (uses role_specificity per KPI):
            role_weight: specific=10, common=5

        Args:
            kpi_data: List of KPI dicts with 'goal_type_category', 'Status', and
                      either 'role_type' (individual) or 'role_specificity' (team/scrum) fields.

        Returns:
            Dictionary with overall score and per-category breakdown.
        """
        # Initialize per-category accumulators
        category_stats = {
            cat: {'weighted_actual': 0.0, 'weighted_max': 0.0,
                  'total': 0, 'green': 0, 'orange': 0, 'red': 0}
            for cat in ('Input', 'Output', 'Quality', 'Hygiene')
        }

        for kpi in kpi_data:
            if kpi.get('excluded_from_score', False):
                continue

            goal_type = kpi.get('goal_type_category', '').strip()
            status = kpi.get('Status', '').strip()

            if status.lower() in ('notconfigured', 'not_configured'):
                continue

            if goal_type not in category_stats:
                continue

            # Determine role weight
            # Individual dashboards supply role_type; team/scrum dashboards supply role_specificity
            role_type = kpi.get('role_type', '')
            role_specificity = kpi.get('role_specificity', '')
            if role_type:
                role_weight = self.role_weights.get(role_type, self.role_weights.get('Other', 1))
            elif role_specificity:
                role_weight = self.aggregation_role_weights.get(
                    role_specificity, self.aggregation_role_weights.get('non_specific', 5))
            else:
                role_weight = 1  # fallback for entries missing both fields

            status_credit = self.status_weights.get(status, 0.0)

            stats = category_stats[goal_type]
            stats['weighted_actual'] += role_weight * status_credit
            stats['weighted_max'] += role_weight
            stats['total'] += 1
            if status == 'Green':
                stats['green'] += 1
            elif status == 'Orange':
                stats['orange'] += 1
            elif status == 'Red':
                stats['red'] += 1

        # Calculate per-category scores
        category_scores = {}
        for category, stats in category_stats.items():
            if stats['weighted_max'] > 0:
                score_percentage = (stats['weighted_actual'] / stats['weighted_max']) * 100
                category_score = (score_percentage / 100) * self.weightages.get(category, 0)
            else:
                score_percentage = 0.0
                category_score = 0.0

            category_scores[category] = {
                'total_kpis': stats['total'],
                'green_kpis': stats['green'],
                'orange_kpis': stats['orange'],
                'red_kpis': stats['red'],
                'weighted_max': round(stats['weighted_max'], 2),
                'weighted_actual': round(stats['weighted_actual'], 2),
                'score_percentage': round(score_percentage, 2),
                'weightage': self.weightages.get(category, 0),
                'score': round(category_score, 2)
            }

        overall_score = sum(cat['score'] for cat in category_scores.values())

        return {
            'overall_score': round(overall_score, 2),
            'max_score': 100,
            'categories': category_scores,
            'weightages': self.weightages.copy(),
            'status_weights': self.status_weights.copy(),
            'role_weights': self.role_weights.copy(),
            'aggregation_role_weights': self.aggregation_role_weights.copy(),
            'rog_thresholds': self.rog_thresholds.copy(),
            'score_display_thresholds': self.score_display_thresholds.copy()
        }
    
    def calculate_aggregate_score(self, member_scores: List[Dict]) -> Dict:
        """
        Calculate aggregated score for a team or scrum.
        
        Formula: Category Score = [(Green × wG) + (Orange × wO) + (Red × wR)] / Total × Weightage
        
        Args:
            member_scores: List of individual score dictionaries
            
        Returns:
            Aggregated score dictionary with averages
        """
        if not member_scores:
            return {
                'overall_score': 0,
                'max_score': 100,
                'member_count': 0,
                'categories': {
                    category: {
                        'total_kpis': 0,
                        'green_kpis': 0,
                        'orange_kpis': 0,
                        'red_kpis': 0,
                        'score_percentage': 0,
                        'weightage': weightage,
                        'score': 0
                    }
                    for category, weightage in self.weightages.items()
                },
                'weightages': self.weightages.copy(),
                'status_weights': self.status_weights.copy(),
                'rog_thresholds': self.rog_thresholds.copy()
            }
        
        # Aggregate category stats
        agg_categories = defaultdict(lambda: {'total': 0, 'green': 0, 'orange': 0, 'red': 0})
        
        for member_score in member_scores:
            categories = member_score.get('categories', {})
            for category, stats in categories.items():
                agg_categories[category]['total'] += stats.get('total_kpis', 0)
                agg_categories[category]['green'] += stats.get('green_kpis', 0)
                agg_categories[category]['orange'] += stats.get('orange_kpis', 0)
                agg_categories[category]['red'] += stats.get('red_kpis', 0)
        
        # Calculate aggregated scores
        category_scores = {}
        for category in ['Input', 'Output', 'Quality', 'Hygiene']:
            stats = agg_categories[category]
            if stats['total'] > 0:
                # Weighted score using configurable status weights
                weighted_score = (
                    (stats['green'] * self.status_weights.get('Green', 1.0)) +
                    (stats['orange'] * self.status_weights.get('Orange', 0.75)) +
                    (stats['red'] * self.status_weights.get('Red', 0.0))
                )
                score_percentage = (weighted_score / stats['total']) * 100
                category_score = (score_percentage / 100) * self.weightages.get(category, 0)
            else:
                score_percentage = 0
                category_score = 0
            
            category_scores[category] = {
                'total_kpis': stats['total'],
                'green_kpis': stats['green'],
                'orange_kpis': stats['orange'],
                'red_kpis': stats['red'],
                'score_percentage': round(score_percentage, 2),
                'weightage': self.weightages.get(category, 0),
                'score': round(category_score, 2)
            }
        
        overall_score = sum(cat['score'] for cat in category_scores.values())
        
        return {
            'overall_score': round(overall_score, 2),
            'max_score': 100,
            'member_count': len(member_scores),
            'categories': category_scores,
            'weightages': self.weightages.copy(),
            'status_weights': self.status_weights.copy(),
            'rog_thresholds': self.rog_thresholds.copy(),
            'score_display_thresholds': self.score_display_thresholds.copy()
        }


# Singleton instance
_scoring_service = None

def get_scoring_service() -> ScoringService:
    """Get or create singleton scoring service instance"""
    global _scoring_service
    if _scoring_service is None:
        _scoring_service = ScoringService()
    return _scoring_service
