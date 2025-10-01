# audio_decode.py
from pydub import AudioSegment
import numpy as np
import threading

class AudioSource:
    """
    Lazy-Decoding mit pydub/ffmpeg, gecacht pro Datei.
    Liefert float32 Samples in gewünschter Samplerate/Channels.
    """
    _cache_lock = threading.Lock()
    _cache = {}  # path -> AudioSegment (standardisiert auf sr/ch)

    def __init__(self, path: str, target_sr=48000, channels=2):
        self.path = path
        self.sr = int(target_sr)
        self.ch = int(channels)

    def _load(self) -> AudioSegment:
        key = (self.path, self.sr, self.ch)
        with AudioSource._cache_lock:
            seg = AudioSource._cache.get(key)
            if seg is None:
                seg = AudioSegment.from_file(self.path)
                # normalisieren auf Ziel-SR/Channels (pydub ist intern int)
                seg = seg.set_frame_rate(self.sr).set_channels(self.ch)
                AudioSource._cache[key] = seg
        return seg

    def duration(self) -> float:
        seg = self._load()
        return seg.duration_seconds

    def read_window(self, start_sec: float, nframes: int) -> np.ndarray:
        """
        Gibt float32-Array (nframes, ch) im Bereich [start_sec, start_sec + nframes/sr) zurück.
        Außerhalb -> Nullen.
        """
        seg = self._load()
        sr = self.sr
        ch = self.ch
        # pydub arbeitet in ms
        start_ms = max(0.0, start_sec * 1000.0)
        end_ms = start_ms + (nframes / sr) * 1000.0

        # slice
        win = seg[start_ms:end_ms] if end_ms > start_ms else AudioSegment.silent(duration=0, frame_rate=sr)

        # Falls am Ende weniger Samples -> später mit Nullen auffüllen
        raw = np.array(win.get_array_of_samples(), dtype=np.float32)
        if ch > 1:
            raw = raw.reshape(-1, ch)
        else:
            raw = raw.reshape(-1, 1)

        # pydub skaliert int basierend auf sample_width; hier auf [-1..1]
        peak = float(1 << (8 * win.sample_width - 1))
        if peak > 0:
            raw /= peak

        # pad/trim auf exakt nframes
        nf = raw.shape[0]
        if nf < nframes:
            pad = np.zeros((nframes - nf, ch), dtype=np.float32)
            raw = np.concatenate([raw, pad], axis=0)
        elif nf > nframes:
            raw = raw[:nframes]

        return raw
