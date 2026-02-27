from pydantic import BaseModel


class LabMetricsData(BaseModel):
    builds: int
    boots: int
    tests: int
    origin: str


class BuildIncidentsByOrigin(BaseModel):
    total: int
    new_regressions: int


class MetricsReportData(BaseModel):
    # Current interval
    n_trees: int
    n_checkouts: int
    n_builds: int
    n_tests: int
    n_issues: int
    n_incidents: int
    build_incidents_by_origin: dict[str, BuildIncidentsByOrigin]
    lab_maps: dict[str, LabMetricsData]
    # Previous interval (for comparison)
    prev_n_trees: int
    prev_n_checkouts: int
    prev_n_builds: int
    prev_n_tests: int
    prev_lab_maps: dict[str, LabMetricsData]
