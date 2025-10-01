# timeline_mixer.py
import numpy as np
from audio_decode import AudioSource

class _TrackBinding:
    def __init__(self, path: str, trim_in: float, trim_out: float, start_time: float, gain_db: float, sr: int, ch: int):
        self.path = path
        self.trim_in = float(trim_in)
        self.trim_out = float(trim_out)
        self.start_time = float(start_time)
        self.gain_db = float(gain_db)
        self.src = AudioSource(path, target_sr=sr, channels=ch)

    def contains(self, t: float) -> bool:
        # t in Timeline-Koordinaten
        local = (t - self.start_time) + self.trim_in
        return (local >= 0.0) and (self.trim_in <= local < self.trim_out + 1e-9)

    def read(self, t0: float, nframes: int, sr: int) -> np.ndarray:
        # mappe Timeline-Zeit -> lokale Quellzeit
        local_start = (t0 - self.start_time) + self.trim_in
        if local_start < 0:
            # teilweise vor TrimIn -> vorne Nullen, ab 0 starten
            # negative offset: verschiebe Start und kürze nframes
            miss_sec = -local_start
            miss_frames = int(min(nframes, round(miss_sec * sr)))
            head = np.zeros((miss_frames, 2), dtype=np.float32)
            tail = self.src.read_window(0.0, nframes - miss_frames)
            return np.concatenate([head, tail], axis=0)

        # Clamp auf trim_out
        max_end = self.trim_out
        remain_sec = max(0.0, max_end - local_start)
        if remain_sec <= 0:
            return np.zeros((nframes, 2), dtype=np.float32)

        want = nframes
        max_frames = int(round(remain_sec * sr))
        if max_frames < want:
            buf = self.src.read_window(local_start, max_frames)
            tail = np.zeros((want - max_frames, buf.shape[1]), dtype=np.float32)
            out = np.concatenate([buf, tail], axis=0)
        else:
            out = self.src.read_window(local_start, want)

        if abs(self.gain_db) > 1e-6:
            out *= 10 ** (self.gain_db / 20.0)
        return out


class TimelineMixer:
    """
    Kennt Clips (Video mit möglichem Audio) und getrennte Audiospuren.
    Liefert pro Block den Summenmix (float32).
    """
    def __init__(self, clips_ref, audios_ref, sample_rate=48000, channels=2):
        """
        clips_ref/audios_ref: callable ohne Args, die aktuelle Listen liefern
                              (damit keine Kopien gepflegt werden müssen)
        """
        self._clips_ref = clips_ref
        self._audios_ref = audios_ref
        self.sr = int(sample_rate)
        self.ch = int(channels)

    def _active_bindings(self, t0: float, nframes: int):
        t1 = t0 + nframes / self.sr
        binds = []

        # Video-Clip-Audios (falls du deren Audio mitmischen willst)
        for c in self._clips_ref():
            # hat Clip-Audio? MoviePy-Preview nutzt Bild, hier gehen wir über Datei
            # Wir behandeln einfach jedes Video so, als hätte es Audio – falls nicht, kommt Stille zurück.
            if (t0 < c.start_time + c.trimmed_length()) and (t1 > c.start_time):
                binds.append(_TrackBinding(
                    path=c.path, trim_in=c.trim_in, trim_out=c.safe_out(), start_time=c.start_time,
                    gain_db=0.0, sr=self.sr, ch=self.ch
                ))

        # Separate Audio-Tracks
        for a in self._audios_ref():
            if (t0 < a.start_time + a.trimmed_length()) and (t1 > a.start_time):
                binds.append(_TrackBinding(
                    path=a.path, trim_in=a.trim_in, trim_out=a.safe_out(), start_time=a.start_time,
                    gain_db=getattr(a, "gain_db", 0.0), sr=self.sr, ch=self.ch
                ))
        return binds

    def render_block(self, t0: float, nframes: int):
        mix = np.zeros((nframes, self.ch), dtype=np.float32)
        for b in self._active_bindings(t0, nframes):
            buf = b.read(t0, nframes, self.sr)
            # channel guard
            if buf.shape[1] != self.ch:
                if buf.shape[1] > self.ch:
                    buf = buf[:, :self.ch]
                else:
                    rep = self.ch - buf.shape[1]
                    buf = np.concatenate([buf] + [buf[:, :1]] * rep, axis=1)
            mix[:buf.shape[0]] += buf
        # Soft-clip
        np.clip(mix, -1.0, 1.0, out=mix)
        return mix
