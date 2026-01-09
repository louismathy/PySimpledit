# Simpledit

Simpledit is a lightweight, timeline-based video editor written in Python.
It focuses on a clean rendering core, deterministic playback, and explicit
audio/video synchronization rather than UI complexity.

The project was built to explore real-world media processing problems such as
timeline scheduling, preview vs. render separation, and audio/video sync.


## Architecture Highlights
- Timeline-based deterministic playback model
- Separate preview and render pipelines
- Custom audio engine with block-based block mixing
- Declarative, serializable effect chains
- O(log n) clip lookup during playback

## Design Decisions
- MoviePy + FFmpeg for stability and reproducibility
- Preview rendering is throttled and decoupled from final export
- Effects are defined declaratively to support serialization and future backends
- Parallel rendering was intentionally avoided to reduce I/O contention

## Requirements
- Python 3.10+
- FFmpeg available in PATH (required by MoviePy)

## Install and Run (Windows)


1. Open a terminal in the project folder.
2. Run the launcher:

```
start.bat
```

This will create a virtual environment, install dependencies, and start the app.

## Install and Run (Linux/macOS)

1. Open a terminal in the project folder.
2. Make the script executable (first run only):

```
chmod +x start.sh
```

3. Run the launcher:

```
./start.sh
```

This will create a virtual environment, install dependencies, and start the app.

## Manual Setup (All Platforms)

If you prefer to run it manually:

```
python -m venv venv
```

Activate the environment:

- Windows:
```
venv\Scripts\activate
```

- Linux/macOS:
```
source venv/bin/activate
```

Install dependencies:

```
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run:

```
python src/main.py
```

## ffmpeg

ffmpeg must be installed and available in PATH. Download from:

- https://ffmpeg.org/download.html

## Project Structure

- `src/` Application source code
- `start.bat` Windows launcher
- `start.sh` Linux/macOS launcher
- `requirements.txt` Python dependencies
