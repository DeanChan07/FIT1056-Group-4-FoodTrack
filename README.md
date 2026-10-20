# FIT1056 Group 04: FoodShare Tracker

A prototype for a single-site community food bank: donations, inventory with expiry
tracking, needs-aware allocation, private food swaps, a check-in pickup queue,
volunteer tasks, reports and anonymous feedback.

Built with **Streamlit** (screens) and **SQLite** (data), in Python 3.11 or newer.

```bash
cd FoodTracker
bash setup.sh                 # Windows: .\setup.ps1
./.venv/bin/python run.py     # opens http://localhost:8501
```

Demo sign-ins: `staff`, `volunteer`, `recipient`, `recipient2`, `recipient3`, `manager`, `admin`.
Every demo password is `DemoPassword123!`.

- How to run, demo walkthrough and structure: [FoodTracker/README.md](FoodTracker/README.md)
- How the Flask vs Streamlit review issues were handled: [FoodTracker/docs/REVIEW_FIXES.md](FoodTracker/docs/REVIEW_FIXES.md)

The earlier Flask version is in this repository's history (commit `e515714`).
# FIT1056-Group-4-FoodTrack
