"""
API endpoints for scoring configuration and management
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Optional
from app.services.scoring_service import get_scoring_service
from app.dependencies import require_admin
from app.models.user import TokenData

router = APIRouter(prefix="/api", tags=["scoring"])


class ScoringWeightages(BaseModel):
    """Model for scoring weightages configuration"""
    Input: float = Field(..., ge=0, le=100, description="Weightage for Input KPIs (0-100)")
    Output: float = Field(..., ge=0, le=100, description="Weightage for Output KPIs (0-100)")
    Quality: float = Field(..., ge=0, le=100, description="Weightage for Quality KPIs (0-100)")
    Hygiene: float = Field(..., ge=0, le=100, description="Weightage for Hygiene KPIs (0-100)")
    
    @field_validator('Input', 'Output', 'Quality', 'Hygiene')
    @classmethod
    def validate_percentage(cls, v):
        if v < 0 or v > 100:
            raise ValueError('Weightage must be between 0 and 100')
        return v
    
    def validate_total(self):
        """Validate that all weightages sum to 100"""
        total = self.Input + self.Output + self.Quality + self.Hygiene
        if abs(total - 100) > 0.01:
            raise ValueError(f'Weightages must sum to 100, got {total}')


class StatusWeights(BaseModel):
    """Model for status weights configuration"""
    Green: float = Field(..., ge=0, le=1, description="Weight for Green status (0-1, default 1.0)")
    Orange: float = Field(..., ge=0, le=1, description="Weight for Orange status (0-1, default 0.75)")
    Red: float = Field(..., ge=0, le=1, description="Weight for Red status (0-1, default 0.0)")
    
    @field_validator('Green', 'Orange', 'Red')
    @classmethod
    def validate_weight(cls, v):
        if v < 0 or v > 1:
            raise ValueError('Status weight must be between 0 and 1')
        return v


class RoleWeights(BaseModel):
    """Model for individual role-based KPI weights"""
    Primary: float = Field(..., ge=0, le=20, description="Weight for KPIs applicable via Primary role (0-20)")
    Secondary: float = Field(..., ge=0, le=20, description="Weight for KPIs applicable via Secondary role (0-20)")
    All: float = Field(..., ge=0, le=20, description="Weight for KPIs marked as All (0-20)")
    Common: float = Field(..., ge=0, le=20, description="Weight for KPIs marked as Common (0-20)")
    Other: float = Field(..., ge=0, le=20, description="Weight for KPIs in Other/Metric category (0-20)")


class AggregationRoleWeights(BaseModel):
    """Model for team/scrum aggregation role weights"""
    specific: float = Field(..., ge=0, le=20, description="Weight for role-specific KPIs in team/scrum aggregation (0-20)")
    non_specific: float = Field(..., ge=0, le=20, description="Weight for Non-Specific KPIs (All, Common, Other) in team/scrum aggregation (0-20)")


class ROGThresholds(BaseModel):
    """Model for ROG threshold configuration (for individual KPI status)"""
    green_threshold: float = Field(..., ge=0, le=100, description="Threshold for Green status in % (default 100.0)")
    orange_threshold: float = Field(..., ge=0, le=100, description="Threshold for Orange status in % (default 70.0)")
    
    @field_validator('green_threshold', 'orange_threshold')
    @classmethod
    def validate_threshold(cls, v):
        if v < 0 or v > 200:
            raise ValueError('Threshold must be between 0 and 200')
        return v
    
    def validate_ordering(self):
        """Validate that orange_threshold <= green_threshold"""
        if self.orange_threshold > self.green_threshold:
            raise ValueError(f'orange_threshold ({self.orange_threshold}) must be <= green_threshold ({self.green_threshold})')


class ScoreDisplayThresholds(BaseModel):
    """Model for score display threshold configuration (for gauge coloring)"""
    green_min: float = Field(..., ge=0, le=100, description="Minimum score for Green color (default 70.0)")
    orange_min: float = Field(..., ge=0, le=100, description="Minimum score for Orange color (default 36.0)")
    red_max: float = Field(..., ge=0, le=100, description="Maximum score for Red color (default 35.0)")
    
    @field_validator('green_min', 'orange_min', 'red_max')
    @classmethod
    def validate_threshold(cls, v):
        if v < 0 or v > 100:
            raise ValueError('Display threshold must be between 0 and 100')
        return v
    
    def validate_ordering(self):
        """Validate that red_max < orange_min < green_min"""
        if not (self.red_max < self.orange_min < self.green_min):
            raise ValueError(f'Must satisfy: red_max ({self.red_max}) < orange_min ({self.orange_min}) < green_min ({self.green_min})')


class ScoringConfig(BaseModel):
    """Complete scoring configuration"""
    weightages: ScoringWeightages
    status_weights: Optional[StatusWeights] = None
    role_weights: Optional[RoleWeights] = None
    aggregation_role_weights: Optional[AggregationRoleWeights] = None
    rog_thresholds: Optional[ROGThresholds] = None
    score_display_thresholds: Optional[ScoreDisplayThresholds] = None


class ScoringConfigResponse(BaseModel):
    """Response model for scoring configuration"""
    weightages: Dict[str, float]
    status_weights: Dict[str, float]
    role_weights: Dict[str, float]
    aggregation_role_weights: Dict[str, float]
    rog_thresholds: Dict[str, float]
    score_display_thresholds: Dict[str, float]
    total: float
    description: str = "Scoring configuration for category weights, status weights, role weights, ROG thresholds, and display thresholds"


@router.get("/score-config", response_model=ScoringConfigResponse)
def get_scoring_config():
    """
    Get current scoring configuration.
    
    Returns:
        - weightages: Weightages for each KPI category (Input, Output, Quality, Hygiene)
        - status_weights: Weights for each status level (Green, Orange, Red)
        - role_weights: Weights by individual KPI applicability (Primary, Secondary, All, Common, Other)
        - aggregation_role_weights: Weights for team/scrum aggregation (specific, non_specific)
        - rog_thresholds: Performance percentage thresholds for individual KPI status determination
        - score_display_thresholds: Color thresholds for gauge display (0-35 Red, 36-69 Orange, 70-100 Green)
    """
    try:
        scoring_service = get_scoring_service()
        config = scoring_service.get_config()
        
        weightages = config.get('weightages', {})
        status_weights = config.get('status_weights', {})
        role_weights = config.get('role_weights', {})
        aggregation_role_weights = config.get('aggregation_role_weights', {})
        rog_thresholds = config.get('rog_thresholds', {})
        score_display_thresholds = config.get('score_display_thresholds', {})
        total = sum(weightages.values())
        
        return ScoringConfigResponse(
            weightages=weightages,
            status_weights=status_weights,
            role_weights=role_weights,
            aggregation_role_weights=aggregation_role_weights,
            rog_thresholds=rog_thresholds,
            score_display_thresholds=score_display_thresholds,
            total=total,
            description="Current scoring configuration"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching scoring config: {str(e)}")


@router.put("/score-config", response_model=ScoringConfigResponse)
def update_scoring_config(config: ScoringConfig, current_user: TokenData = Depends(require_admin)):
    """
    Update scoring configuration.
    
    Updates the configuration for scoring calculation and display:
    - Category weightages must total 100%
    - Status weights must be between 0 and 1
    - Role weights must be between 0 and 20
    - Aggregation role weights must be between 0 and 20
    - ROG thresholds: orange_threshold <= green_threshold, both between 0-100% (for individual KPIs)
    - Score display thresholds: red_max < orange_min < green_min, all between 0-100 (for gauge coloring)
    
    Args:
        config: New configuration payload
        
    Returns:
        Updated scoring configuration
    """
    try:
        # Validate total equals 100
        config.weightages.validate_total()
        
        # Convert weightages to dict
        weightages_dict = {
            'Input': config.weightages.Input,
            'Output': config.weightages.Output,
            'Quality': config.weightages.Quality,
            'Hygiene': config.weightages.Hygiene
        }
        
        # Convert status weights to dict if provided
        status_weights_dict = None
        if config.status_weights:
            status_weights_dict = {
                'Green': config.status_weights.Green,
                'Orange': config.status_weights.Orange,
                'Red': config.status_weights.Red
            }

        # Convert individual role weights to dict if provided
        role_weights_dict = None
        if config.role_weights:
            role_weights_dict = {
                'Primary': config.role_weights.Primary,
                'Secondary': config.role_weights.Secondary,
                'All': config.role_weights.All,
                'Common': config.role_weights.Common,
                'Other': config.role_weights.Other
            }

        # Convert aggregation role weights to dict if provided
        aggregation_role_weights_dict = None
        if config.aggregation_role_weights:
            aggregation_role_weights_dict = {
                'specific': config.aggregation_role_weights.specific,
                'non_specific': config.aggregation_role_weights.non_specific
            }
        
        # Convert ROG thresholds to dict if provided
        rog_thresholds_dict = None
        if config.rog_thresholds:
            config.rog_thresholds.validate_ordering()
            rog_thresholds_dict = {
                'green_threshold': config.rog_thresholds.green_threshold,
                'orange_threshold': config.rog_thresholds.orange_threshold
            }
        
        # Convert score display thresholds to dict if provided
        score_display_thresholds_dict = None
        if config.score_display_thresholds:
            config.score_display_thresholds.validate_ordering()
            score_display_thresholds_dict = {
                'green_min': config.score_display_thresholds.green_min,
                'orange_min': config.score_display_thresholds.orange_min,
                'red_max': config.score_display_thresholds.red_max
            }
        
        # Save configuration
        scoring_service = get_scoring_service()
        success = scoring_service.save_config(
            weightages_dict,
            status_weights_dict,
            rog_thresholds_dict,
            score_display_thresholds_dict,
            role_weights_dict,
            aggregation_role_weights_dict
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save scoring configuration")
        
        # Get updated config
        updated_config = scoring_service.get_config()
        total = sum(updated_config['weightages'].values())
        
        return ScoringConfigResponse(
            weightages=updated_config['weightages'],
            status_weights=updated_config['status_weights'],
            role_weights=updated_config['role_weights'],
            aggregation_role_weights=updated_config['aggregation_role_weights'],
            rog_thresholds=updated_config['rog_thresholds'],
            score_display_thresholds=updated_config['score_display_thresholds'],
            total=total,
            description="Scoring configuration updated successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating scoring config: {str(e)}")
