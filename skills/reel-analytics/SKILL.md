---
name: reel-analytics
description: Analyze Instagram Reels performance metrics (reach, plays, saves, shares, engagement rate) for CurioMotion and generate algorithmic growth insights.
---

# CurioMotion Reel Analytics Skill

This skill analyzes published Instagram Reels, tracks virality metrics, and produces strategic insights to optimize hooks, retention, and topic selection.

## When to Use
- Whenever a new Reel is published to Instagram
- To evaluate recent content performance and virality metrics (Save Rate, Share Ratio, Engagement Rate)
- To identify which visual styles, hooks, and topic niches generate the highest retention
- Before scripting upcoming reels to steer topic selection toward high-performing themes

## How to Run Analytics

### 1. Automated CLI Execution
Run the analytics engine directly from the workspace:
```bash
python automation/reel_analytics.py
```

### 2. Core Metrics Evaluated
- **Saves Rate (`saves / reach * 100%`)**: The single most potent algorithmic signal for educational 3D engineering content. High saves signal high bookmark value.
- **Viral Share Ratio (`shares / plays * 100%`)**: Measures DM forwarding and group chat velocity.
- **Engagement Rate (`(likes + comments + saves + shares) / reach * 100%`)**:
  - `> 8.0%`: S-Tier (Viral Breakout)
  - `5.0% - 8.0%`: A-Tier (Strong Community Resonance)
  - `2.5% - 5.0%`: B-Tier (Solid Baseline)
  - `< 2.5%`: C-Tier (Requires Hook/Visual Iteration)
- **Retention Drop-off Analysis**: Correlates the first 3 seconds (cover hook card & initial cutaway) with overall completion.

## Outputs
- **JSON Matrix**: `data/analytics_history.json`
- **Markdown Intelligence Brief**: `data/LATEST_ANALYTICS.md`
