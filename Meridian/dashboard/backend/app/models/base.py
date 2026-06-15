"""
Pydantic models for API request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

# Employee Models
class EmployeeBase(BaseModel):
    sapid: str = Field(..., description="8-digit employee ID")
    name: str
    team: str
    scrum: str
    primary_role: str
    secondary_role: Optional[str] = None
    manager: Optional[str] = None
    employment_status: Optional[str] = 'Active'

class EmployeeCreate(EmployeeBase):
    pass

class EmployeeUpdate(EmployeeBase):
    pass

class Employee(EmployeeBase):
    ref: Optional[str] = None
    reporting: Optional[float] = None
    manager_name: Optional[str] = None
    email: Optional[str] = None
    resource_sheet_name: Optional[str] = None
    resource_sheet_id: Optional[str] = None
    jira_name: Optional[str] = None
    git_email: Optional[str] = None
    udeid: Optional[str] = None
    tacid: Optional[str] = None
    url: Optional[str] = None
    github_name: Optional[str] = None
    last_modified: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# Role/KPI Models
class RoleBase(BaseModel):
    index: str = Field(..., description="KPI identifier (e.g., k3)")
    name: str
    primary_role: str
    secondary_role: Optional[str] = None
    goal_type: str = Field(..., description="Input, Output, Quality, or Hygiene")
    kpp_goals: Optional[str] = None
    measurement_criteria: Optional[str] = None
    tool: Optional[str] = None
    measure: Optional[str] = None
    weekly_target: float
    quarterly_target: float
    annual_target: float
    aggregation_type: str = Field(..., description="ANG, ANL, APG, APL, or NA")
    active: bool = True

class RoleCreate(RoleBase):
    pass

class RoleUpdate(BaseModel):
    weekly_target: Optional[float] = None
    quarterly_target: Optional[float] = None
    annual_target: Optional[float] = None

class Role(RoleBase):
    employee_count: Optional[int] = 0
    last_modified: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# Response Models
class PaginatedResponse(BaseModel):
    data: list
    total: int
    page: int
    page_size: int
    total_pages: int

class SuccessResponse(BaseModel):
    success: bool = True
    message: str
    data: Optional[dict] = None
