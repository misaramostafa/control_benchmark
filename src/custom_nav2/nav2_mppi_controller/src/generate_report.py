import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def analyze_log_data(csv_path):
    """
    Expects CSV with columns: [timestamp, v_cmd, w_cmd, pose_x, pose_y, ld_dist, theta]
    """
    df = pd.read_csv(csv_path)
    
    # Calculate time differences and velocity deltas
    df['time_diff'] = df['timestamp'].diff()
    df['pose_delta'] = np.sqrt(df['pose_x'].diff()**2 + df['pose_y'].diff()**2)
    
    # Detect stuck states: v_cmd active but zero displacement
    stuck_frames = df[(df['v_cmd'] > 0.1) & (df['pose_delta'] < 0.001)]
    stuck_time_total = stuck_frames['time_diff'].sum()
    
    # Compute performance stats
    metrics = {
        "total_runtime": df['timestamp'].iloc[-1] - df['timestamp'].iloc[0],
        "max_loop_gap": df['time_diff'].max(),
        "stuck_duration": stuck_time_total,
        "avg_v_cmd": df['v_cmd'].mean(),
        "status": "FAIL (Stuck Detected)" if stuck_time_total > 3.0 else "PASS"
    }
    return df, metrics

def generate_plots(df, output_img="velocity_plot.png"):
    plt.figure(figsize=(7, 3))
    plt.plot(df['timestamp'] - df['timestamp'].iloc[0], df['v_cmd'], label='v_cmd (m/s)', color='#005587')
    plt.plot(df['timestamp'] - df['timestamp'].iloc[0], df['pose_delta'] / df['time_diff'], label='v_actual (m/s)', color='#E05A47')
    plt.title("Controller Command vs Displacement Velocity")
    plt.xlabel("Time (s)")
    plt.ylabel("Velocity")
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(output_img, dpi=200)
    plt.close()

def build_pdf_report(metrics, plot_path, pdf_path="erc_navigation_report.pdf"):
    doc = SimpleDocTemplate(pdf_path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#1A2B4C'))
    story.append(Paragraph("ERC Autonomous Navigation Analytics Report", title_style))
    story.append(Spacer(1, 12))

    # Metrics Summary Table
    table_data = [
        ["Metric", "Value", "Threshold / Status"],
        ["Total Test Duration", f"{metrics['total_runtime']:.2f} s", "N/A"],
        ["Max Control Loop Latency", f"{metrics['max_loop_gap']:.3f} s", "< 0.500 s" if metrics['max_loop_gap'] < 0.5 else "WARN"],
        ["Stuck / Stale State Time", f"{metrics['stuck_duration']:.2f} s", "CRITICAL" if metrics['stuck_duration'] > 3.0 else "OK"],
        ["Overall Run Result", metrics['status'], "PASS" if metrics['status'] == "PASS" else "FAIL"]
    ]
    
    t = Table(table_data, colWidths=[200, 150, 150])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A2B4C')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
    ]))
    story.append(t)
    story.append(Spacer(1, 18))

    # Velocity and Displacement Plot
    story.append(Paragraph("<b>Velocity & Displacement Trace</b>", styles['Heading2']))
    story.append(Spacer(1, 6))
    story.append(Image(plot_path, width=500, height=214))

    doc.build(story)

if __name__ == "__main__":
    # Example pipeline run
    # df, metrics = analyze_log_data("test_run.csv")
    # generate_plots(df)
    # build_pdf_report(metrics, "velocity_plot.png")
    pass
