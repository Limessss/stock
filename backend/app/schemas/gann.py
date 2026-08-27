"""江恩角度线 schemas。"""
from __future__ import annotations

from pydantic import BaseModel


class GannPoint(BaseModel):
    time: str
    value: float


class GannAnchor(BaseModel):
    date: str
    price: float
    kind: str
    reason: str


class GannLine(BaseModel):
    label: str
    color: str
    direction: str
    points: list[GannPoint]


class GannAnchors(BaseModel):
    up: GannAnchor | None = None
    down: GannAnchor | None = None


class GannCalibration(BaseModel):
    up_ref: GannAnchor | None = None
    down_ref: GannAnchor | None = None


class GannResponse(BaseModel):
    code: str
    name: str = ""
    window_bars: int
    price_scale: float
    note: str = ""
    anchors: GannAnchors
    calibration: GannCalibration
    lines: list[GannLine]
