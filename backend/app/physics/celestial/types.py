"""Typed specifications for N-body simulations (unit-tagged)."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MASS_UNITS = {"kg": 1.0, "msun": 1.98847e30, "mjup": 1.89813e27, "mearth": 5.9722e24}
DISTANCE_UNITS = {"m": 1.0, "au": 1.495978707e11, "rsun": 6.957e8}
TIME_UNITS = {"s": 1.0, "day": 86400.0, "yr": 3.15576e7}


class BodySpec(BaseModel):
    """A celestial body: either Cartesian state or Keplerian elements."""

    name: str
    mass_value: float = Field(gt=0, description="Mass magnitude")
    mass_unit: Literal["kg", "msun", "mjup", "mearth"] = "msun"
    # Keplerian elements (relative to primary). If x..vz provided they win.
    a: float | None = Field(default=None, gt=0, description="Semi-major axis")
    e: float | None = Field(default=None, ge=0, lt=1, description="Eccentricity")
    inc: float | None = Field(default=None, ge=0, description="Inclination [rad]")
    Omega: float | None = Field(default=None, description="Longitude of ascending node [rad]")
    omega: float | None = Field(default=None, description="Argument of periapsis [rad]")
    theta: float | None = Field(default=None, description="True anomaly [rad]")
    # Cartesian state (SI, in the sim's unit system) fallback
    x: float | None = None
    y: float | None = None
    z: float | None = None
    vx: float | None = None
    vy: float | None = None
    vz: float | None = None

    distance_unit: Literal["m", "au"] = "au"
    velocity_unit: Literal["m/s"] = "m/s"

    def mass_kg(self) -> float:
        return self.mass_value * MASS_UNITS[self.mass_unit]

    def distance_m(self) -> float | None:
        if self.a is None:
            return None
        return self.a * DISTANCE_UNITS[self.distance_unit]


class SimConfig(BaseModel):
    """Configuration for a REBOUND N-body integration."""

    integrator: Literal["whfast", "ias15", "mercurius", "euler", "rk4"] = "ias15"
    dt: float = Field(default=0.01, gt=0, description="Timestep in simulation time units")
    t_end: float = Field(default=10.0, gt=0, description="Integration end time [yr]")
    output_every: int = Field(default=100, ge=1, description="Snapshot cadence (steps)")
    distance_unit: Literal["au"] = "au"
    mass_unit: Literal["msun"] = "msun"
    time_unit: Literal["yr"] = "yr"
    softening: float = Field(default=0.0, ge=0)
    exit_unstable: bool = Field(
        default=True, description="Stop early if any body is unbound/ejected"
    )


class SimulationRequest(BaseModel):
    bodies: list[BodySpec] = Field(min_length=2, max_length=64)
    config: SimConfig = SimConfig()

    @model_validator(mode="after")
    def _check_names(self) -> "SimulationRequest":
        names = [b.name for b in self.bodies]
        if len(set(names)) != len(names):
            raise ValueError("Body names must be unique")
        return self
