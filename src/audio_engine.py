# audio_engine.py
import sounddevice as sd
import numpy as np

class AudioEngine:
    def __init__(self, sample_rate=48000, channels=2, blocksize=1024, latency='low'):
        self.sr = int(sample_rate)
        self.ch = int(channels)
        self.blocksize = int(blocksize)
        self.latency = latency
        self._timeline_cb = None
        self._playing = False
        self._time = 0.0  # aktuelle Timeline-Zeit in Sekunden

        self._stream = sd.OutputStream(
            samplerate=self.sr,
            channels=self.ch,
            blocksize=self.blocksize,
            dtype='float32',
            latency=self.latency,
            callback=self._callback,
        )

    def set_timeline_callback(self, fn):
        """fn(t0: float, nframes: int) -> np.ndarray shape (nframes, channels) float32"""
        self._timeline_cb = fn

    def play(self, start_time: float):
        self._time = float(start_time)
        if not self._stream.active:
            self._stream.start()
        self._playing = True

    def pause(self):
        self._playing = False

    def stop(self):
        self._playing = False
        try:
            if self._stream.active:
                self._stream.stop()
        except Exception:
            pass

    def seek(self, t: float):
        self._time = float(t)

    def time(self) -> float:
        return float(self._time)

    # --- PortAudio callback ---
    def _callback(self, outdata, frames, time_info, status):
        if status:
            # optional: print(status)
            pass
        if not self._playing or self._timeline_cb is None:
            outdata[:] = 0
            return
        try:
            buf = self._timeline_cb(self._time, int(frames))
            if not isinstance(buf, np.ndarray):
                outdata[:] = 0
            else:
                # shape guard
                if buf.ndim == 1:
                    buf = np.stack([buf] * self.ch, axis=-1)
                if buf.shape[1] != self.ch:
                    # channels mismatch -> simple trim/expand
                    if buf.shape[1] > self.ch:
                        buf = buf[:, :self.ch]
                    else:
                        # expand mono to stereo etc.
                        rep = self.ch - buf.shape[1]
                        buf = np.concatenate([buf] + [buf[:, :1]] * rep, axis=1)
                if buf.shape[0] != frames:
                    # pad or trim
                    if buf.shape[0] < frames:
                        pad = np.zeros((frames - buf.shape[0], self.ch), dtype=np.float32)
                        buf = np.concatenate([buf, pad], axis=0)
                    else:
                        buf = buf[:frames]
                outdata[:] = buf
        except Exception:
            outdata[:] = 0
        finally:
            self._time += frames / self.sr
