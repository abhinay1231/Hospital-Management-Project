import matplotlib.pyplot as plt
import numpy as np
import os

# Create output directory
output_dir = "performance_graphs"
os.makedirs(output_dir, exist_ok=True)

# Models
models = ["LLaMA 3 (8B)", "Gemma (7B)", "Qwen (7B)", "Mistral (7B)"]

# -------------------------
# Performance Data
# -------------------------
recall = [0.812, 0.745, 0.795, 0.770]
f1 = [0.682, 0.625, 0.641, 0.630]
rouge = [0.715, 0.655, 0.685, 0.670]

latency_p50 = [0.72, 0.60, 1.20, 0.55]
latency_p95 = [0.85, 0.78, 1.55, 0.90]

x = np.arange(len(models))
width = 0.25

plt.style.use("seaborn-v0_8-muted")

# ======================================================
# GRAPH 1 : MULTI-METRIC MODEL PERFORMANCE COMPARISON
# ======================================================

fig, ax = plt.subplots(figsize=(11,6))

bars1 = ax.bar(x - width, f1, width, label="F1 Score")
bars2 = ax.bar(x, recall, width, label="Recall@3")
bars3 = ax.bar(x + width, rouge, width, label="ROUGE-L")

# Add value labels
def add_labels(bars):
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2,
                height + 0.01,
                f"{height:.3f}",
                ha='center', va='bottom', fontsize=9)

add_labels(bars1)
add_labels(bars2)
add_labels(bars3)

# Add performance trend line (average score)
avg_scores = [(f1[i] + recall[i] + rouge[i]) / 3 for i in range(len(models))]
ax.plot(x, avg_scores, marker='o', linewidth=2, label="Average Performance Trend")

ax.set_ylabel("Evaluation Score")
ax.set_title("Comparative Performance of LLMs under MedRAG Evaluation")
ax.set_xticks(x)
ax.set_xticklabels(models)
ax.set_ylim(0.5, 1.0)
ax.legend()

plt.savefig(os.path.join(output_dir, "model_performance_analysis.png"), dpi=300)
plt.close()

# ======================================================
# GRAPH 2 : LATENCY AND INFERENCE EFFICIENCY ANALYSIS
# ======================================================

fig, ax = plt.subplots(figsize=(11,6))

bars_p50 = ax.bar(x - width/2, latency_p50, width, label="P50 Latency")
bars_p95 = ax.bar(x + width/2, latency_p95, width, label="P95 Latency")

# Add numerical labels
for bars in [bars_p50, bars_p95]:
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2,
                height + 0.03,
                f"{height:.2f}s",
                ha='center', va='bottom', fontsize=9)

# Add latency trend line
ax.plot(x, latency_p95, marker='o', linestyle='--', linewidth=2,
        label="High Percentile Latency Trend")

ax.set_ylabel("Latency (seconds)")
ax.set_title("Inference Latency Comparison across Models (MedRAG Pipeline)")
ax.set_xticks(x)
ax.set_xticklabels(models)

ax.legend()

plt.savefig(os.path.join(output_dir, "latency_efficiency_analysis.png"), dpi=300)
plt.close()

print("Graphs successfully saved in 'performance_graphs' folder.")