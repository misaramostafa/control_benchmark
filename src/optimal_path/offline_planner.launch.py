"""Offline Path Generation: D* Lite global planner + Offline Sequence Script.

This launch file isolates the global planner to run against pre-defined CSV 
maps and waypoints without launching the local MPPI controller or live simulator.
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    pkg_share = get_package_share_directory('dstar_navigation')

    # Resolved file paths
    dstar_params = os.path.join(pkg_share, 'config', 'dstar_params.yaml')
    rviz_config  = os.path.join(pkg_share, 'config', 'rviz', 'dstar_test.rviz')

    # ── Global planner nodes ─────────────────────────────────────────────────

    # D* Lite global planner — Action Server for path generation
    dstar_node = Node(
        package='dstar_navigation',
        executable='dstar_node',
        name='dstar_global_planner',
        parameters=[dstar_params],
        output='screen',
    )

    # Offline Sequence Planner — Publishes CSV map, teleports odom, requests paths
    offline_planner_node = Node(
        package='dstar_navigation',
        executable='offline_sequence_planner.py',
        name='offline_sequence_planner',
        output='screen',
    )

    # Static map → odom transform
    static_tf_node = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='map_to_odom_tf',
        arguments=['0', '0', '0', '0', '0', '0', 'map', 'odom'],
        output='screen',
    )

    # ── Visualisation ────────────────────────────────────────────────────────
    
    # RViz2 to watch the sequence generation live
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        output='screen',
    )

    return LaunchDescription([
        dstar_node,
        offline_planner_node,
        static_tf_node,
        rviz_node,
    ])