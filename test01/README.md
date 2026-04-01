# Structure-from-Motion Presentation

A Python project that generates a PowerPoint presentation explaining
Structure-from-Motion (SfM) and why scale ambiguity remains in the solution.

## Contents

- **`Structure_from_Motion.pptx`** — 10-slide presentation (pre-built)
- **`build_pptx.py`** — Python script to regenerate the presentation

## Slides

1. Title
2. What is Structure-from-Motion?
3. The SfM Pipeline
4. Mathematical Foundation: Epipolar Geometry
5. Why Does Scale Ambiguity Exist?
6. Mathematical Proof of Scale Ambiguity
7. Degrees of Freedom & the Gauge Ambiguity
8. Scale Ambiguity: Same Images, Different Worlds
9. How to Resolve Scale Ambiguity
10. Summary

## Setup

```bash
pip install -r requirements.txt
```

## Regenerate

```bash
python build_pptx.py
```
