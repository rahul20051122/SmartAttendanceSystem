# SmartAttendanceSystem

Minimal instructions to run this Flask-based attendance app locally.

Prerequisites
- Python 3.8+ (virtualenv recommended)

Setup
```powershell
cd SmartAttendanceSystem
python -m venv venv
.\venv\Scripts\Activate.ps1  # PowerShell
pip install -r requirements.txt
```

Run
```powershell
python app.py
```

The app will run at `http://127.0.0.1:5000` by default.

Notes
- The app creates/uses the local database on startup.
- If `cv2` import fails, ensure `opencv-python` is installed (`pip install opencv-python`).
