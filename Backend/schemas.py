from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class Filter(BaseModel):
    column: str
    operator: Literal["=", "!=", ">", "<", ">=", "<=", "ilike", "in"]
    value: Union[str, float, List[str]]


class SpatialCondition(BaseModel):
    operation: Literal["within_distance", "intersects"]
    reference_layer: str
    distance_m: Optional[float] = Field(None, description="Distance in METERS (within_distance only)")
    reference_filters: List[Filter] = Field(default_factory=list)
    negate: bool = Field(False, description="True for 'not near', 'far from', 'without'")


class GISQuery(BaseModel):
    target_layer: Optional[str] = None
    filters: List[Filter] = Field(default_factory=list)
    spatial: List[SpatialCondition] = Field(default_factory=list)
    limit: Optional[int] = None
    requires_clarification: bool = False
    clarification_message: Optional[str] = None
    

class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class AskRequest(BaseModel):
    text: str
    location: Optional[Location] = None