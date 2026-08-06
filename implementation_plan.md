# Merge Bridge into Orchestrator + Wire generate_report.py

## Background

The current architecture has the benchmark driver split across **two separate ROS 2 nodes**:

- `test_orchestrator` — publishes `/path`, `/odometry/filtered`, `/testing/current_case`; consumes `/cmd_vel` to update simulated pose.
- `nav2_bench_bridge` — subscribes to `/path` + `/odometry/filtered` and forwards each path as a `FollowPath` action goal to Nav2's `controller_server`.

This coupling means neither node is independently useful: the orchestrator can't drive a controller by itself, and the bridge is a pure relay with no test logic. The user wants a **single, self-contained test node** that acts as the black-box harness, while the controller under test (Nav2 MPPI, AdaptiveLd, or any future plugin) remains untouched.

Additionally, `generate_report.py` is documented as being invoked at shutdown, but the launch file **never actually calls it**. This needs to be wired up.

---

## Proposed Changes

### Component 1 — `test_orchestrator.py`

#### [MODIFY] [test_orchestrator.py](file:///wsl.localhost/Ubuntu-22.04/home/misara/benchmarking/src/Control/AdaptivePurePursuit/adaptive_pure_pursuit/test_orchestrator.py)

Absorb all bridge functionality directly into `TestOrchestratorNode`:

- Add `rclpy.action.ActionClient` import and `FollowPath` import.
- In `__init__`: add bridge parameters (`odom_frame`, `base_frame`), declare `ActionClient(self, FollowPath, 'follow_path')`, add an `odom_pub` that republishes `/odometry/filtered` on `/odom` (as Nav2 expects), track `_last_path_signature` / `_goal_in_progress` / `_active_goal_handle` fields.
- Move `_path_signature()` helper into the class.
- After each path publish (on path change), call the bridge's `_send_follow_path_goal()` logic directly.
- Move `odom_callback` → `_relay_odom()` called inline in `_publish_current_state()`.
- Remove the `tf_broadcaster` that was duplicated in the bridge (keep the one already in the orchestrator).
- Add `goal_response_callback` and `goal_result_callback` as methods.

> **Black-box guarantee preserved**: The node still only reads `/cmd_vel` and publishes `/path` + `/odometry/filtered`. Anything that subscribes to those and publishes `/cmd_vel` will be tested — the action interface is an *optional* acceleration for Nav2-style controllers.

---

### Component 2 — `nav2_bench_bridge.py`

#### [MODIFY] [nav2_bench_bridge.py](file:///wsl.localhost/Ubuntu-22.04/home/misara/benchmarking/src/Control/AdaptivePurePursuit/adaptive_pure_pursuit/nav2_bench_bridge.py)

Keep the file (so the entry point still builds), but gut it to a **stub** with a deprecation warning and an immediate clean exit, so nothing breaks if someone accidentally launches it:

```python
# DEPRECATED — bridge logic merged into test_orchestrator (v2).
# This file is intentionally a no-op stub.
```

---

### Component 3 — `generate_report.py`

#### [MODIFY] [generate_report.py](file:///wsl.localhost/Ubuntu-22.04/home/misara/benchmarking/src/Control/AdaptivePurePursuit/adaptive_pure_pursuit/generate_report.py)

The current `generate_report.py` expects columns `[timestamp, v_cmd, w_cmd, pose_x, pose_y, ld_dist, theta]` but `control_monitor.py` writes:
`[timestamp_s, case_id, cmd_linear_x, actual_linear_x, cmd_angular_z, actual_angular_z, steering_jerk_deg_s2, lat_error_m, pos_error_m, heading_error_rad, overshoot_m, linear_violation, angular_violation, jerk_instability, similarity_ratio]`

Fix `generate_report.py` to:
- Accept a `--csv` argument (path to the CSV).
- Accept a `--pdf` argument (output PDF path).
- Read `control_monitor`'s actual CSV columns instead of the old schema.
- `analyze_log_data()` → maps `timestamp_s → timestamp`, `cmd_linear_x → v_cmd`, `cmd_angular_z → w_cmd`, `pos_error_m → pose_delta`, etc.
- `generate_plots()` → uses the correct columns.
- `build_pdf_report()` → unchanged structure, just fed correct data.
- `if __name__ == '__main__'` block fully implemented (not `pass`) — parses args and runs the pipeline.

---

### Component 4 — `mppi_control_nodes.launch.py`

#### [MODIFY] [mppi_control_nodes.launch.py](file:///wsl.localhost/Ubuntu-22.04/home/misara/benchmarking/src/Control/AdaptivePurePursuit/launch/mppi_control_nodes.launch.py)

- **Remove** `bridge_node` from the `return` list (it's now embedded in the orchestrator).
- **Add** an `ExecuteProcess` for `generate_report.py` after the orchestrator exits:
  ```
  python3 <path>/generate_report.py \
      --csv /tmp/mppi_controller_metrics.csv \
      --pdf /tmp/mppi_controller_report.pdf
  ```
- Hook it into `orchestrator_exit_handler` → chain: stop bag → run generate_report → shutdown.

---

### Component 5 — `setup.py`

#### [MODIFY] [setup.py](file:///wsl.localhost/Ubuntu-22.04/home/misara/benchmarking/src/Control/AdaptivePurePursuit/setup.py)

- Add `'generate_report = adaptive_pure_pursuit.generate_report:main'` to `console_scripts` so it can be invoked via `ros2 run` or `python3 -m`.

---

## Data Flow After Change

```
test_orchestrator (merged node)
  ├─ publishes /path  ─────────────────────────────────────────────► controller_server (Nav2 MPPI or any)
  ├─ publishes /odometry/filtered  ────────────────────────────────► controller_server
  ├─ sends FollowPath action goal  ────────────────────────────────► controller_server
  ├─ publishes /odom  (relay for Nav2 internal use)
  └─ subscribes /cmd_vel  ◄────────────────────────────────────────  controller_server

control_monitor
  ├─ subscribes /path, /odometry/filtered, /cmd_vel, /testing/current_case
  └─ writes CSV + HTML report on shutdown

[on orchestrator exit]
  stop rosbag → generate_report.py (PDF from CSV) → Shutdown
```

---

## Open Questions

> [!IMPORTANT]
> **Q1**: Should `nav2_bench_bridge.py` be fully deleted (entry point removed from `setup.py`), or kept as a stub for backwards compatibility with any existing launch files that reference it?  
> _Current plan: keep as stub so the package still builds without errors and old scripts don't break._

> [!IMPORTANT]
> **Q2**: The `generate_report.py` PDF uses `reportlab`. Is `reportlab` installed in the venv?  
> _If not, the PDF step will silently fail. The HTML report from `control_monitor` will still be generated._

## Verification Plan

### Automated
- Confirm the file parses cleanly: `python3 -c "import adaptive_pure_pursuit.test_orchestrator"` after build.
- Run `python3 generate_report.py --csv /tmp/mppi_controller_metrics.csv --pdf /tmp/test.pdf` against a sample CSV.

### Manual
- `colcon build --symlink-install && source install/setup.bash`
- `ros2 launch adaptive_pure_pursuit mppi_control_nodes.launch.py`
- Confirm only one node (not two) handles the path → Nav2 bridge loop.
- Confirm PDF is written to `/tmp/mppi_controller_report.pdf` at end of run.
