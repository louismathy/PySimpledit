                 
import sounddevice as sd
import numpy as np
from utils import debug_log

class AudioEngine:
    def __init__(self, sample_rate=48000, channels=2, blocksize=1024, latency='low'):
        self.sr = int(sample_rate)
        self.ch = int(channels)
        self.blocksize = int(blocksize)
        self.latency = latency
        self._timeline_cb = None
        self._playing = False
        self._time = 0.0                                      

        self._stream = sd.OutputStream(
            samplerate=self.sr,
            channels=self.ch,
            blocksize=self.blocksize,
            dtype='float32',
            latency=self.latency,
            callback=self._callback,
        )

    def set_timeline_callback(self, fn):
                                                                                         
        self._timeline_cb = fn

    def play(self, start_time: float):
        self._time = float(start_time)
        debug_log(f"audio.play start_time={self._time:.3f}")
        if not self._stream.active:
            self._stream.start()
        self._playing = True

    def pause(self):
        debug_log("audio.pause")
        self._playing = False

    def stop(self):
        debug_log("audio.stop")
        self._playing = False
        try:
            if self._stream.active:
                self._stream.stop()
        except Exception:
            pass

    def seek(self, t: float):
        self._time = float(t)
        debug_log(f"audio.seek t={self._time:.3f}")

    def time(self) -> float:
        return float(self._time)

                                
    def _callback(self, outdata, frames, time_info, status):
        if status:
            debug_log(f"audio.callback status={status}")
            pass
        if not self._playing or self._timeline_cb is None:
            outdata[:] = 0
            return
        try:
            buf = self._timeline_cb(self._time, int(frames))
            if not isinstance(buf, np.ndarray):
                outdata[:] = 0
            else:
                             
                if buf.ndim == 1:
                    buf = np.stack([buf] * self.ch, axis=-1)
                if buf.shape[1] != self.ch:
                                                             
                    if buf.shape[1] > self.ch:
                        buf = buf[:, :self.ch]
                    else:
                                                    
                        rep = self.ch - buf.shape[1]
                        buf = np.concatenate([buf] + [buf[:, :1]] * rep, axis=1)
                if buf.dtype != np.float32:
                    buf = buf.astype(np.float32, copy=False)
                if buf.shape[0] != frames:
                                 
                    if buf.shape[0] < frames:
                        pad = np.zeros((frames - buf.shape[0], self.ch), dtype=np.float32)
                        buf = np.concatenate([buf, pad], axis=0)
                    else:
                        buf = buf[:frames]
                outdata[:] = buf
        except Exception:
            debug_log("audio.callback exception")
            outdata[:] = 0
        finally:
            self._time += frames / self.sr
