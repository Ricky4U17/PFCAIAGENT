import os, math
import numpy as np
import matplotlib.pyplot as plt
from app.engines.interleaved_ccm import vpk_from_vac, duty_from_vin, delta_il_pp, kd_exact_piecewise

def _ensure_dir(path): os.makedirs(path, exist_ok=True)

def plot_topology_scores(ranking, output_dir):
    _ensure_dir(output_dir)
    names = [r["topology"] for r in ranking]; scores = [r["final_score"] for r in ranking]
    plt.figure(figsize=(8,4.5)); plt.bar(names, scores); plt.xticks(rotation=25, ha="right"); plt.ylabel("Final score"); plt.title("Topology Comparison"); plt.tight_layout()
    path = os.path.join(output_dir, "topology_scores.png"); plt.savefig(path); plt.close(); return path

def plot_duty_vs_line_angle(vac, vout, output_dir, line_freq=60.0):
    _ensure_dir(output_dir)
    theta_deg = np.linspace(0,180,2000); theta_rad = np.deg2rad(theta_deg); vpk = vpk_from_vac(vac); vin = vpk * np.abs(np.sin(theta_rad)); duty = np.clip(1.0 - vin/vout, 0.0, 1.0)
    plt.figure(figsize=(8,4.5)); plt.plot(theta_deg, duty); plt.xlabel("Line angle (deg)"); plt.ylabel("Duty"); plt.title(f"Duty Cycle vs Line Angle @ {vac} Vac"); plt.grid(True); plt.tight_layout()
    path = os.path.join(output_dir, f"duty_vs_line_angle_{int(vac)}Vac.png"); plt.savefig(path); plt.close(); return path
