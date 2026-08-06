# Comprehensive Development & User Guide

This guide details how to build, configure, and execute both **Offline Path Generation** and the **Full Live Navigation Stack** (D* Lite + MPPI Controller) with the Gazebo Marsyard simulation.

---

## Workspace Setup & Prerequisites

Before running any ROS 2 commands, ensure all workspace dependencies are installed and built:

```bash
# Navigate to workspace root
cd ~/ros_ws/navStack_2026

# Install required ROS 2 Humble packages (if not already installed)
sudo apt update && sudo apt install -y \
  ros-humble-nav2-bringup \
  ros-humble-nav2-bt-navigator \
  ros-humble-nav2-controller \
  ros-humble-nav2-planner \
  ros-humble-nav2-map-server \
  ros-humble-nav2-lifecycle-manager \
  ros-humble-nav2-behaviors \
  ros-humble-nav2-mppi-controller \
  ros-humble-ros-gz-bridge \
  ros-humble-ros-gz-sim \
  ros-humble-gz-ros2-control \
  ros-humble-diff-drive-controller \
  ros-humble-joint-state-broadcaster \
  ros-humble-robot-state-publisher \
  ros-humble-xacro \
  ros-humble-tf2-ros \
  ros-humble-tf2-tools

# Build the complete workspace
colcon build --symlink-install

# Source the workspace environment
source install/setup.bash
```

---

# SECTION 1: Offline Sequence Path Generation

Use this section to generate an offline 3D path trajectory (`combined_offline_path.csv`) from a terrain grayscale heightmap image and a set of waypoints without running Gazebo or the local controller.

### 1. Inputs Required

Place the following two input files inside your working directory or `path-planning/globalPlanner/offline_tools/`:

1. **`heightmap.png`**: An 8-bit or 16-bit grayscale image where pixel intensities ($0..255$ or $0..65535$) represent terrain elevation.
2. **`waypoints.csv`**: A CSV file listing the $(X, Y)$ coordinates for each waypoint:
   ```csv
   0.0, 0.0
   400.0, 23.0
   126.0, 67.0
   13.0, 2.0
   230.0, 55.0
   ```

### 2. Build & Launch Offline Sequence Planner

Open a terminal and run:

```bash
# 1. Navigate to workspace root and source environment
cd ~/ros_ws/navStack_2026
source install/setup.bash

### 2. Configurable Launch Parameters

The offline planner launch file (`launch/offline_planner.launch.py`) accepts arguments to tune map scaling, bounding box origin, and slope thresholds:

| Parameter | Default Value | Description |
| :--- | :--- | :--- |
| **`heightmap_png`** | `'heightmap.png'` | Path to input grayscale heightmap image file (8-bit or 16-bit). |
| **`resolution`** | `'0.05'` | Map resolution in meters per pixel (5 cm/pixel). |
| **`min_height`** | `'0.0'` | Minimum terrain elevation $Z$ in meters. |
| **`max_height`** | `'1.5'` | Maximum terrain elevation $Z$ in meters (Set to $1.5\text{m}$ for realistic field terrain). |
| **`origin_x`** | `'0.0'` | World frame origin $X$ position in meters. |
| **`origin_y`** | `'0.0'` | World frame origin $Y$ position in meters. |
| **`center_origin`** | `'true'` | Auto-centers map $(0,0)$ at middle of image ($X: -W/2..+W/2, Y: -H/2..+H/2$). |
| **`max_safe_slope_deg`**| `'25.0'` | Maximum traversable terrain slope angle in degrees. |
| **`max_safe_step_m`** | `'0.30'` | Maximum traversable vertical step height in meters. |

### 3. Build & Launch Offline Sequence Planner

Open a terminal and run:

```bash
# 1. Navigate to workspace root and source environment
cd ~/ros_ws/navStack_2026
source install/setup.bash

# 2. Launch with default parameters (max_height=1.5m, auto-centered origin)
ros2 launch dstar_navigation offline_planner.launch.py

# Or customize launch arguments directly on command line:
ros2 launch dstar_navigation offline_planner.launch.py \
  heightmap_png:=path-planning/globalPlanner/offline_tools/heightmap.png \
  resolution:=0.05 \
  min_height:=0.0 \
  max_height:=1.5 \
  max_safe_slope_deg:=25.0
```

### 4. What Happens Automatically
* The script reads `heightmap.png`, applies `cv2.flip(img, 0)` for true ROS OccupancyGrid orientation, and converts pixel intensities into elevation meters ($Z$).
* Publishes all required map layers with `TRANSIENT_LOCAL` QoS:
  * `/active_map/heightmap` (Normalized 0..100 elevation grid)
  * `/active_map/heightmap_range` (`[min_z, z_range]` in meters)
  * `/terrain_costmap` (Sobel steepness + Laplacian roughness OpenCV filters)
  * `/map` (Continuous OccupancyGrid with crisp details filtered by `medianBlur(3)`)
* Teleports robot `/odom` across each leg in `waypoints.csv`.
* Queries D* Lite to solve optimal 3D routes for each waypoint leg.
* **Output Files Generated**:
  ```
  combined_offline_path.csv   # Combined 3D path coordinates (x, y, z)
  costmap.csv                 # 2D obstacle costmap grid for path editor
  ```

---

# SECTION 2: Offline Path Editor (`path_editor.py`)

The **Offline Path Editor** is an interactive GUI tool built with Pygame that allows you to inspect, fine-tune, or hand-redraw generated 3D paths on top of the costmap before competition day.

### 1. Launching the Path Editor

Ensure you have run the offline sequence planner at least once to generate `costmap.csv` and `combined_offline_path.csv`, then run:

```bash
python3 path-planning/globalPlanner/offline_tools/path_editor.py
```

### 2. Editing Modes

Toggle between modes using the **`TAB`** key:

* **WAYPOINT Mode** (Default):
  * **Left-click** empty space to add a new point.
  * **Left-click + Drag** an existing point (red dot) to move it around obstacles.
  * **Right-click** an existing point to delete it from the path.
* **DRAW Mode** (Freehand Redrawing):
  * **Left-click + Hold & Drag** to draw a freehand path line across the map.
  * Upon releasing the mouse button, the drawn stroke is automatically spliced into the path between the two nearest existing waypoints, replacing the segment in between.

### 3. Controls Summary

| Control | Action |
| :--- | :--- |
| **`Left-Click / Drag`** | Add or relocate waypoints (WAYPOINT mode) or draw freehand stroke (DRAW mode). |
| **`Right-Click`** | Delete nearest waypoint. |
| **`Mouse Wheel`** | Zoom in / out (centered on cursor). |
| **`Middle-Mouse Drag`** | Pan camera view across the map. |
| **`TAB`** | Toggle between **WAYPOINT** and **DRAW** mode. |
| **`Ctrl + Z`** | Undo last edit action. |
| **`Ctrl + Y` / `Ctrl + Shift + Z`** | Redo last edit action. |
| **`R`** | Reset camera view (zoom & pan). |
| **`S`** | Save modified path to `edited_offline_path.csv`. |
| **`ESC`** | Exit Path Editor. |

---

# SECTION 3: Running the Full Navigation Stack in Gazebo Simulation

To run the complete system in simulation (Gazebo Marsyard + D* Lite Global Planner + MPPI Local Controller + Waypoint Follower), open **3 separate terminals**.

---

### Terminal 1 — Gazebo Marsyard Simulation Environment

This terminal launches the Gazebo simulation world, spawns the ROAR rover, and starts ROS 2 control interfaces (`diff_drive_controller`).

```bash
# 1. Source workspace
cd ~/ros_ws/navStack_2026
source install/setup.bash

# 2. Launch Gazebo Marsyard Simulation
ros2 launch roar_simulation basic_rover_mars.launch.py
```

> ⚠️ **Wait Notice**: Wait until you see `Configured and activated diff_drive_controller` in the console output before starting Terminal 2.

---

### Terminal 2 — Full Nav2 Stack & Testing Suite

This terminal launches the complete Nav2 motion planning stack, bringing up the **D* Lite Global Planner**, **MPPI Local Controller**, **Behavior Trees**, and **Costmap Servers**.

```bash
# 1. Source workspace
cd ~/ros_ws/navStack_2026
source install/setup.bash

# 2. Launch Full Motion Planning Stack
ros2 launch navstack_nav2 roar_motion_planning_testing.launch.py
```

> ⚠️ **Wait Notice**: Wait until you see `Managed nodes are active` in the console output before sending waypoints from Terminal 3.

---

### Terminal 3 — ERC Waypoint Follower Script

This terminal executes the automated waypoint follower script, which connects to the `/navigate_to_pose` Action Server and feeds waypoint goals sequentially.

```bash
# 1. Source workspace
cd ~/ros_ws/navStack_2026
source install/setup.bash

# 2. Run ERC Waypoint Follower Script
python3 path-planning/globalPlanner/scripts/erc_waypoint_follower.py
```

#### How Waypoints are Loaded
The script reads the waypoints automatically from the configuration file at `navstack_nav2/config/roar_nav2_sim.yaml`, located at the end of the `planner_server` parameters section:

```yaml
planner_server:
  ros__parameters:
    ...
    # ── ERC Waypoint Parameters ───────────────────────────────────────
    start_end: [0.0, 0.0]
    waypoints: [3.0, 2.0, 3.0, -10.0, -15.0, 5.0, -10.0, 8.0]
```

The script parses these coordinates, sends each goal sequentially to D* Lite and MPPI, tracks navigation progress, and logs distance errors upon arrival at each waypoint.
