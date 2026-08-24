// ============================================
// Points Chart page — Chart.js bar chart
// ============================================

let pointsChart = null;

async function loadChart() {
  const status = document.getElementById("chart-status");
  const position = document.getElementById("chart-position").value;
  const metric = document.getElementById("chart-metric").value;

  status.textContent = "Loading chart…";
  status.style.display = "block";

  try {
    const res = await fetch(`/api/chart-data?position=${position}&metric=${metric}&n=15`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Request failed");

    if (data.labels.length === 0) {
      status.textContent = "No players found for this filter.";
      if (pointsChart) pointsChart.destroy();
      return;
    }

    status.style.display = "none";

    const values = metric === "total_points" ? data.total_points : data.predicted_points;
    const label = metric === "total_points" ? "Total Points (season)" : "Predicted Points";

    const ctx = document.getElementById("points-chart").getContext("2d");
    if (pointsChart) pointsChart.destroy();

    pointsChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: label,
            data: values,
            backgroundColor: "rgba(201, 162, 39, 0.75)",
            borderColor: "#C9A227",
            borderWidth: 1,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: "#ECEDEA" } },
        },
        scales: {
          x: {
            ticks: { color: "#8A9A93" },
            grid: { color: "rgba(255,255,255,0.06)" },
          },
          y: {
            ticks: { color: "#8A9A93" },
            grid: { color: "rgba(255,255,255,0.06)" },
            beginAtZero: true,
          },
        },
      },
    });
  } catch (e) {
    status.textContent = `Error: ${e.message}`;
    status.style.display = "block";
  }
}

document.getElementById("chart-position").addEventListener("change", loadChart);
document.getElementById("chart-metric").addEventListener("change", loadChart);
loadChart();
