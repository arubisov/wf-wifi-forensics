# wf/analysis/config.py

from dataclasses import dataclass

@dataclass
class ClassifierConfig:
    """
    Configuration for the co-traveller vs. static-AP classifier pipeline.

    Attributes
    ----------
    t_max_gap
        Maximum silence (s) before closing a visibility window.
    min_window_len
        Minimum observations per window.
    r_stationary
        Maximum diameter (m) to call a window “stationary.”
    mobile_decim_d
        Distance (m) threshold for mobile-track decimation.
    mobile_decim_t
        Time (s) threshold for mobile-track decimation.
    max_speed_ms
        Maximum allowed speed (m/s) to guard against spurious jumps.
    """
    t_max_gap:        int     = 120
    min_window_len:   int     = 1
    r_stationary:     float   = 350.0
    mobile_decim_d:   float   = 100.0
    mobile_decim_t:   int     = 30
    max_speed_ms:     float   = 200e3 / 3600
    
    @classmethod
    def driving(cls):
        """Preset for vehicle mode (default thresholds)."""
        return cls()

    @classmethod
    def walking(cls):
        """Preset for pedestrian mode (tighter thresholds)."""
        return cls(
            t_max_gap=60,
            min_window_len=1,
            r_stationary=50.0,
            mobile_decim_d=10.0,
            mobile_decim_t=5,
            max_speed_ms=8_000 / 3600,  # ~8 km/h in m/s
        )