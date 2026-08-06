#!/usr/bin/env python3
"""generate_report.py -- Standalone HTML benchmark report generator.

Reads the CSV produced by control_monitor.py and writes a self-contained
HTML summary report.

CSV schema (control_monitor output):
  timestamp_s, case_id, cmd_linear_x, actual_linear_x, cmd_angular_z,
  actual_angular_z, steering_jerk_deg_s2, lat_error_m, pos_error_m,
  heading_error_rad, overshoot_m, linear_violation, angular_violation,
  jerk_instability, similarity_ratio

Usage (CLI):
  python3 generate_report.py \\
      --csv /tmp/mppi_controller_metrics.csv \\
      --out /tmp/mppi_report.html

Or via ros2 run / console_scripts entry point:
  generate_report --csv /tmp/mppi_controller_metrics.csv
"""

import argparse
import csv
import os
import sys
import webbrowser
from datetime import datetime

# --------------------------------------------------------------------------
# Thresholds (mirror control_monitor defaults so pass/fail is consistent)
# --------------------------------------------------------------------------
MAX_AVG_JERK_DEG_S2 = 150.0
MAX_LAT_ERROR_M = 0.20
MAX_AVG_LAG_M_S = 0.15


def analyze_log_data(csv_path: str):
    """Parse control_monitor CSV and return aggregated metrics + per-case breakdown."""
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"CSV file is empty or has no data rows: {csv_path}")

    # ---- Global arrays ----
    timestamps   = [float(r['timestamp_s'])          for r in rows]
    cmd_v        = [abs(float(r['cmd_linear_x']))     for r in rows]
    actual_v     = [abs(float(r['actual_linear_x']))  for r in rows]
    lat_errors   = [abs(float(r['lat_error_m']))      for r in rows]
    pos_errors   = [float(r['pos_error_m'])           for r in rows]
    overshoots   = [float(r['overshoot_m'])           for r in rows]
    jerks        = [abs(float(r['steering_jerk_deg_s2'])) for r in rows]
    lin_viols    = [int(r['linear_violation'])        for r in rows]
    ang_viols    = [int(r['angular_violation'])       for r in rows]
    jerk_instabs = [int(r['jerk_instability'])        for r in rows]

    n = len(rows)
    total_runtime = timestamps[-1] - timestamps[0] if n > 1 else 0.0
    avg_lag = sum(abs(c - a) for c, a in zip(cmd_v, actual_v)) / n

    metrics = {
        'total_runtime':    total_runtime,
        'total_samples':    n,
        'avg_lat_error':    sum(lat_errors) / n,
        'max_lat_error':    max(lat_errors),
        'avg_pos_error':    sum(pos_errors) / n,
        'max_pos_error':    max(pos_errors),
        'avg_overshoot':    sum(overshoots) / n,
        'max_overshoot':    max(overshoots),
        'avg_jerk':         sum(jerks) / n,
        'max_jerk':         max(jerks),
        'lin_violations':   sum(lin_viols),
        'ang_violations':   sum(ang_viols),
        'jerk_instabilities': sum(jerk_instabs),
        'avg_lag':          avg_lag,
        'similarity_ratio': float(rows[-1]['similarity_ratio']),
    }

    # ---- Per-case breakdown (preserves encounter order) ----
    cases_order: list = []
    cases_data: dict = {}
    for r in rows:
        cid = (r.get('case_id') or 'UNKNOWN').strip() or 'UNKNOWN'
        if cid not in cases_data:
            cases_data[cid] = []
            cases_order.append(cid)
        cases_data[cid].append(r)

    per_case: dict = {}
    for cid in cases_order:
        crows = cases_data[cid]
        c_lat  = [abs(float(r['lat_error_m']))          for r in crows]
        c_jerk = [abs(float(r['steering_jerk_deg_s2'])) for r in crows]
        c_over = [float(r['overshoot_m'])               for r in crows]
        c_lv   = sum(int(r['linear_violation'])         for r in crows)
        c_av   = sum(int(r['angular_violation'])        for r in crows)
        nc = len(crows)
        per_case[cid] = {
            'samples':       nc,
            'avg_lat':       sum(c_lat)  / nc,
            'max_lat':       max(c_lat),
            'avg_jerk':      sum(c_jerk) / nc,
            'max_jerk':      max(c_jerk),
            'avg_over':      sum(c_over) / nc,
            'max_over':      max(c_over),
            'lin_violations': c_lv,
            'ang_violations': c_av,
            'similarity':    float(crows[-1]['similarity_ratio']),
        }

    return metrics, per_case, cases_order


def build_html_report(
    metrics: dict,
    per_case: dict,
    cases_order: list,
    output_path: str,
    csv_path: str = '',
) -> None:
    """Render a self-contained HTML report and write it to *output_path*."""

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    jerk_ok   = metrics['avg_jerk'] <= MAX_AVG_JERK_DEG_S2
    bounds_ok = (metrics['lin_violations'] + metrics['ang_violations']) == 0
    lag_ok    = metrics['avg_lag'] < MAX_AVG_LAG_M_S
    track_ok  = metrics['max_lat_error'] <= MAX_LAT_ERROR_M
    global_pass = jerk_ok and bounds_ok and lag_ok and track_ok

    def badge(text: str, ok: bool) -> str:
        color = '#1a7a4a' if ok else '#c0392b'
        return (
            f'<span style="background:{color};color:#fff;padding:3px 12px;'
            f'border-radius:3px;font-weight:bold;font-size:12px;letter-spacing:0.5px">'
            f'{text}</span>'
        )

    def val_color(ok: bool) -> str:
        return '#1a7a4a' if ok else '#c0392b'

    # ---- per-case table rows ----
    case_rows_html = ''
    for cid in cases_order:
        c = per_case[cid]
        c_pass = (
            c['avg_jerk'] <= MAX_AVG_JERK_DEG_S2
            and (c['lin_violations'] + c['ang_violations']) == 0
            and c['max_lat'] <= MAX_LAT_ERROR_M
        )
        case_rows_html += f"""
        <tr>
          <td><strong>{cid}</strong></td>
          <td>{c['samples']}</td>
          <td>{c['similarity'] * 100:.1f}%</td>
          <td>{c['avg_lat']:.4f}</td>
          <td style="font-weight:bold;color:{val_color(c['max_lat'] <= MAX_LAT_ERROR_M)}">{c['max_lat']:.4f}</td>
          <td>{c['avg_over']:.4f}</td>
          <td>{c['max_over']:.4f}</td>
          <td>{c['avg_jerk']:.1f}</td>
          <td>{c['max_jerk']:.1f}</td>
          <td>{c['lin_violations'] + c['ang_violations']}</td>
          <td>{badge('PASS', True) if c_pass else badge('FAIL', False)}</td>
        </tr>"""

    csv_link_html = ''
    if csv_path and os.path.exists(csv_path):
        import pathlib
        csv_uri = pathlib.Path(csv_path).resolve().as_uri()
        csv_filename = os.path.basename(csv_path)
        csv_link_html = (
            f'<div style="text-align:right;margin-bottom:20px">'
            f'<a href="{csv_uri}" download style="display:inline-flex;align-items:center;'
            f'gap:6px;background:#fff;color:#0B0B0B;border:1px solid #0B0B0B;'
            f'padding:8px 16px;border-radius:4px;text-decoration:none;font-weight:bold;'
            f'font-size:13px">&#8595; Download CSV ({csv_filename})</a></div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Benchmark Report — {ts}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f0f2f5; color: #1a1a2e; }}
    .header {{ background: #0B0B0B; color: #fff; padding: 24px 40px; border-bottom: 4px solid #D62828; }}
    .header h1 {{ font-size: 22px; letter-spacing: 2px; text-transform: uppercase; font-weight: 800; }}
    .header .sub {{ color: #aaa; margin-top: 5px; font-size: 13px; }}
    .container {{ max-width: 1100px; margin: 30px auto; padding: 0 20px 40px; }}
    .banner {{ text-align: center; padding: 18px; border-radius: 4px; font-size: 20px;
               font-weight: bold; margin-bottom: 24px; letter-spacing: 1px; background: #0B0B0B;
               color: #fff; border: 2px solid {'#1a7a4a' if global_pass else '#D62828'}; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }}
    .card {{ background: #fff; border-radius: 4px; padding: 18px 14px; border: 1px solid #e2e2e2;
             border-top: 3px solid #D62828; text-align: center; }}
    .card h4 {{ font-size: 10px; text-transform: uppercase; color: #777; letter-spacing: 0.5px;
                margin-bottom: 10px; }}
    .card .val {{ font-size: 24px; font-weight: bold; }}
    .section {{ background: #fff; border-radius: 4px; padding: 22px 20px; margin-bottom: 24px;
                border: 1px solid #e2e2e2; border-top: 3px solid #0B0B0B; }}
    .section h3 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px;
                   border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 14px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #e2e2e2; padding: 10px 12px; text-align: center; font-size: 13px; }}
    th {{ background: #0B0B0B; color: #fff; font-size: 11px; text-transform: uppercase;
          letter-spacing: 0.5px; }}
    tr:nth-child(even) td {{ background: #fafafa; }}
    .footer {{ text-align: center; color: #999; font-size: 12px; padding-top: 10px; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>ASU <span style="color:#D62828">ROAR</span> &mdash; Benchmark Report</h1>
    <div class="sub">
      Generated: {ts} &nbsp;&bull;&nbsp;
      {metrics['total_samples']} samples &nbsp;&bull;&nbsp;
      {metrics['total_runtime']:.1f}s runtime
    </div>
  </div>
  <div class="container">
    {csv_link_html}
    <div class="banner">
      OVERALL: {'&#10004; PASSED — STABILITY &amp; TRACKING AUDIT' if global_pass else '&#10008; CRITICAL SIGNALS DETECTED / ENVELOPE BREACHED'}
    </div>

    <!-- KPI cards -->
    <div class="grid">
      <div class="card">
        <h4>Path Similarity</h4>
        <div class="val">{metrics['similarity_ratio'] * 100:.1f}<small style="font-size:14px">%</small></div>
      </div>
      <div class="card">
        <h4>Avg Actuator Jerk</h4>
        <div class="val" style="color:{val_color(jerk_ok)}">{metrics['avg_jerk']:.1f}<small style="font-size:14px"> &deg;/s&sup2;</small></div>
      </div>
      <div class="card">
        <h4>Envelope Breaches</h4>
        <div class="val" style="color:{val_color(bounds_ok)}">{metrics['lin_violations'] + metrics['ang_violations']}</div>
      </div>
      <div class="card">
        <h4>Ctrl&rarr;Odom Lag</h4>
        <div class="val" style="color:{val_color(lag_ok)}">{metrics['avg_lag']:.3f}<small style="font-size:14px"> m/s</small></div>
      </div>
    </div>

    <!-- Global error statistics -->
    <div class="section">
      <h3>Global Error Statistics</h3>
      <table>
        <thead>
          <tr><th>Metric</th><th>Average</th><th>Maximum</th></tr>
        </thead>
        <tbody>
          <tr>
            <td>Lateral Error (m)</td>
            <td>{metrics['avg_lat_error']:.4f}</td>
            <td style="font-weight:bold;color:{val_color(metrics['max_lat_error'] <= MAX_LAT_ERROR_M)}">{metrics['max_lat_error']:.4f}</td>
          </tr>
          <tr>
            <td>Positional Error (m)</td>
            <td>{metrics['avg_pos_error']:.4f}</td>
            <td>{metrics['max_pos_error']:.4f}</td>
          </tr>
          <tr>
            <td>Rotational Overshoot (m)</td>
            <td>{metrics['avg_overshoot']:.4f}</td>
            <td>{metrics['max_overshoot']:.4f}</td>
          </tr>
          <tr>
            <td>Actuator Jerk (&deg;/s&sup2;)</td>
            <td style="color:{val_color(jerk_ok)}">{metrics['avg_jerk']:.1f}</td>
            <td style="font-weight:bold">{metrics['max_jerk']:.1f}</td>
          </tr>
          <tr>
            <td>Lin. Velocity Violations</td>
            <td colspan="2" style="color:{val_color(metrics['lin_violations']==0)}">{metrics['lin_violations']}</td>
          </tr>
          <tr>
            <td>Ang. Velocity Violations</td>
            <td colspan="2" style="color:{val_color(metrics['ang_violations']==0)}">{metrics['ang_violations']}</td>
          </tr>
          <tr>
            <td>Jerk Instabilities</td>
            <td colspan="2" style="color:{val_color(metrics['jerk_instabilities']==0)}">{metrics['jerk_instabilities']}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Per-test breakdown -->
    <div class="section">
      <h3>Per-Test Breakdown</h3>
      <table>
        <thead>
          <tr>
            <th>Case</th><th>Samples</th><th>Similarity</th>
            <th>Avg Lat (m)</th><th>Max Lat (m)</th>
            <th>Avg Over (m)</th><th>Max Over (m)</th>
            <th>Avg Jerk</th><th>Max Jerk</th>
            <th>Violations</th><th>Status</th>
          </tr>
        </thead>
        <tbody>{case_rows_html}
        </tbody>
      </table>
    </div>

    <div class="footer">
      benchmark harness &middot; adaptive_pure_pursuit &middot; {ts}
    </div>
  </div>
</body>
</html>"""

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'[generate_report] HTML report written -> {output_path}')


def main(argv=None) -> int:
    """CLI entry point called by console_scripts and by the launch shutdown chain."""
    parser = argparse.ArgumentParser(
        description='Generate HTML benchmark report from control_monitor CSV'
    )
    parser.add_argument(
        '--csv',
        default='/tmp/mppi_controller_metrics.csv',
        help='Path to the CSV produced by control_monitor (default: %(default)s)',
    )
    parser.add_argument(
        '--out',
        default='/tmp/mppi_controller_report.html',
        help='Output path for the HTML report (default: %(default)s)',
    )
    parser.add_argument(
        '--open', dest='open_browser', action='store_true',
        help='Open the report in the default browser after generation',
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.csv):
        print(f'[generate_report] ERROR: CSV not found: {args.csv}', file=sys.stderr)
        return 1

    try:
        metrics, per_case, cases_order = analyze_log_data(args.csv)
        build_html_report(metrics, per_case, cases_order, args.out, csv_path=args.csv)
        if args.open_browser:
            import pathlib
            webbrowser.open(pathlib.Path(args.out).resolve().as_uri())
    except Exception as exc:
        print(f'[generate_report] ERROR: {exc}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
