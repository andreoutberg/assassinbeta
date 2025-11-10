# Screenshots Directory

This directory contains screenshots for the Andre Assassin Trading System documentation.

## Required Screenshots

### Dashboard Screenshots
- **dashboard.png** - Main trading dashboard overview showing real-time metrics
- **mobile.png** - Mobile responsive view of the dashboard

### Monitoring Screenshots
- **optuna.png** - Optuna optimization dashboard showing live trials
- **grafana.png** - Grafana monitoring dashboard with system metrics

## How to Add Screenshots

1. Take screenshots in production or demo environment
2. Optimize images (recommended max 1920x1080, < 500KB)
3. Use descriptive filenames
4. Place in this directory
5. Update README.md references if needed

## Screenshot Guidelines

- Use consistent window sizes
- Hide sensitive information (API keys, real trading data)
- Show meaningful data (not empty dashboards)
- Include dark mode variants where applicable
- Capture during actual operation for authenticity

## Tools for Screenshots

### Recommended Tools
- **Linux**: Flameshot, GNOME Screenshot
- **macOS**: CleanShot X, Shottr
- **Windows**: ShareX, Greenshot
- **Browser**: Full Page Screen Capture extensions

### Image Optimization
```bash
# Optimize PNG files
optipng -o5 *.png

# Convert to WebP for smaller sizes
for f in *.png; do cwebp -q 80 "$f" -o "${f%.png}.webp"; done
```

## Placeholder Images

Until real screenshots are available, the system will gracefully handle missing images in documentation.