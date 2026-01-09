# Simpledit

Simpledit is a lightweight timeline editor built with PySide6 and MoviePy.
## Architecture Highlights
- Timeline-based deterministic playback
- Separate preview and render pipelines
- Custom audio engine with block-based mixing
- Declarative effect chains (serializable)
- O(log n) clip lookup during playback


## Requirements

- Python 3.10+ (recommended)
- ffmpeg in PATH (required for media decoding via moviepy/pydub)

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
