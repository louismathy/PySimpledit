from dataclasses import dataclass
from typing import Optional

APP_NAME = "Simpledit"


@dataclass
class ClipItem:
    """
    Repräsentiert ein Video-Clipsegment auf der Timeline.
    - path: Dateipfad
    - duration: volle Mediendauer in Sekunden
    - trim_in/trim_out: lokaler In/Out-Punkt relativ zum Medienanfang
    - start_time: Startzeit auf der Timeline (Sekunden)
    """
    path: str
    duration: float
    trim_in: float = 0.0
    trim_out: Optional[float] = None
    start_time: float = 0.0

    def safe_out(self) -> float:
        """Out-Punkt (falls None → volle Dauer)."""
        return self.trim_out if self.trim_out is not None else self.duration

    def trimmed_length(self) -> float:
        """Aktuelle Segmentlänge = trim_out - trim_in (min. 0)."""
        return max(0.0, self.safe_out() - self.trim_in)


@dataclass
class AudioItem:
    """
    Repräsentiert ein Audio-Segment auf der Timeline.
    - path: Dateipfad
    - duration: volle Mediendauer in Sekunden
    - trim_in/trim_out: lokaler In/Out-Punkt relativ zum Medienanfang
    - start_time: Startzeit auf der Timeline (Sekunden)
    - gain_db: Pegeländerung in dB (−60 … +24 dB typischer Bereich)
    """
    path: str
    duration: float
    trim_in: float = 0.0
    trim_out: Optional[float] = None
    start_time: float = 0.0
    gain_db: float = 0.0

    def safe_out(self) -> float:
        """Out-Punkt (falls None → volle Dauer)."""
        return self.trim_out if self.trim_out is not None else self.duration

    def trimmed_length(self) -> float:
        """Aktuelle Segmentlänge = trim_out - trim_in (min. 0)."""
        return max(0.0, self.safe_out() - self.trim_in)
