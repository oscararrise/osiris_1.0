(() => {
    const readPayload = (id, fallback) => {
        const node = document.getElementById(id);
        if (!node) return fallback;
        try {
            return JSON.parse(node.textContent);
        } catch (_error) {
            return fallback;
        }
    };

    const primaryColor = () =>
        getComputedStyle(document.body).getPropertyValue("--client-primary").trim() || "#176247";

    const setupCanvas = (canvas, height) => {
        const width = Math.max(canvas.parentElement.clientWidth, 280);
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        const context = canvas.getContext("2d");
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        return { context, width, height };
    };

    const numericSeries = () =>
        readPayload("sensor-series-data", []).filter((point) => Number.isFinite(Number(point.value)));

    const drawTrend = () => {
        const canvas = document.getElementById("sensor-trend-chart");
        if (!canvas) return;
        const series = numericSeries();
        if (!series.length) return;

        const { context, width, height } = setupCanvas(canvas, 340);
        const primary = primaryColor();
        const padding = { top: 22, right: 22, bottom: 48, left: 60 };
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        const lows = series.map((point) => Number(point.minimum ?? point.value));
        const highs = series.map((point) => Number(point.maximum ?? point.value));
        let minimum = Math.min(...lows);
        let maximum = Math.max(...highs);
        const spread = maximum - minimum || Math.max(Math.abs(maximum) * 0.1, 1);
        minimum -= spread * 0.12;
        maximum += spread * 0.12;

        const x = (index) =>
            padding.left + (index / Math.max(series.length - 1, 1)) * chartWidth;
        const y = (value) =>
            padding.top + (1 - (value - minimum) / (maximum - minimum)) * chartHeight;

        context.clearRect(0, 0, width, height);
        context.font = "11px Inter, system-ui, sans-serif";
        context.lineWidth = 1;
        context.textBaseline = "middle";

        for (let row = 0; row <= 4; row += 1) {
            const value = maximum - ((maximum - minimum) * row) / 4;
            const yPosition = padding.top + (chartHeight * row) / 4;
            context.strokeStyle = "#e8eeeb";
            context.beginPath();
            context.moveTo(padding.left, yPosition);
            context.lineTo(width - padding.right, yPosition);
            context.stroke();
            context.fillStyle = "#7b8982";
            context.textAlign = "right";
            context.fillText(value.toFixed(1), padding.left - 10, yPosition);
        }

        context.beginPath();
        series.forEach((point, index) => {
            const high = Number(point.maximum ?? point.value);
            context[index === 0 ? "moveTo" : "lineTo"](x(index), y(high));
        });
        for (let index = series.length - 1; index >= 0; index -= 1) {
            const low = Number(series[index].minimum ?? series[index].value);
            context.lineTo(x(index), y(low));
        }
        context.closePath();
        context.fillStyle = "rgba(23, 98, 71, 0.09)";
        context.fill();

        context.beginPath();
        series.forEach((point, index) => {
            context[index === 0 ? "moveTo" : "lineTo"](x(index), y(Number(point.value)));
        });
        context.strokeStyle = primary;
        context.lineWidth = 2.7;
        context.lineJoin = "round";
        context.lineCap = "round";
        context.stroke();

        const labelIndexes = [0, Math.floor((series.length - 1) / 2), series.length - 1];
        context.textBaseline = "top";
        [...new Set(labelIndexes)].forEach((index) => {
            const date = new Date(series[index].measured_at);
            context.textAlign = index === 0 ? "left" : index === series.length - 1 ? "right" : "center";
            context.fillStyle = "#7b8982";
            context.fillText(
                date.toLocaleString("es-CO", {
                    day: "2-digit",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                }),
                x(index),
                padding.top + chartHeight + 16,
            );
        });

        canvas._aranetSeries = series;
        canvas._aranetX = x;
        canvas._aranetY = y;
        canvas.dataset.left = String(padding.left);
        canvas.dataset.chartWidth = String(chartWidth);
    };

    const installTrendTooltip = () => {
        const canvas = document.getElementById("sensor-trend-chart");
        const tooltip = document.getElementById("sensor-trend-tooltip");
        if (!canvas || !tooltip) return;

        canvas.addEventListener("mousemove", (event) => {
            const series = canvas._aranetSeries || [];
            if (!series.length) return;
            const rect = canvas.getBoundingClientRect();
            const pointerX = event.clientX - rect.left;
            const left = Number(canvas.dataset.left || 0);
            const chartWidth = Number(canvas.dataset.chartWidth || 1);
            const ratio = Math.min(Math.max((pointerX - left) / chartWidth, 0), 1);
            const index = Math.round(ratio * Math.max(series.length - 1, 0));
            const point = series[index];
            const minimum = Number(point.minimum ?? point.value);
            const maximum = Number(point.maximum ?? point.value);
            const date = new Date(point.measured_at);

            tooltip.innerHTML = `${date.toLocaleString("es-CO", {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
            })}<br>Valor: <strong>${Number(point.value).toFixed(2)}</strong><br>` +
                `Rango: ${minimum.toFixed(2)} – ${maximum.toFixed(2)}`;
            tooltip.style.left = `${canvas._aranetX(index) + 15}px`;
            tooltip.style.top = `${canvas._aranetY(Number(point.value))}px`;
            tooltip.hidden = false;
        });

        canvas.addEventListener("mouseleave", () => {
            tooltip.hidden = true;
        });
    };

    const drawFleetHealth = () => {
        const canvas = document.getElementById("fleet-health-chart");
        if (!canvas) return;
        const health = readPayload("fleet-health-data", null);
        if (!health) return;

        const ratio = window.devicePixelRatio || 1;
        const size = 220;
        canvas.width = size * ratio;
        canvas.height = size * ratio;
        canvas.style.width = `${size}px`;
        canvas.style.height = `${size}px`;
        const context = canvas.getContext("2d");
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        context.clearRect(0, 0, size, size);

        const values = [
            Number(health.online || 0),
            Number(health.delayed || 0),
            Number(health.offline || 0),
        ];
        const colors = ["#2fa879", "#e0a342", "#cc6565"];
        const total = values.reduce((sum, value) => sum + value, 0);
        const center = size / 2;
        const radius = 76;
        const lineWidth = 17;

        if (!total) return;
        context.lineCap = "round";
        let start = -Math.PI / 2;
        values.forEach((value, index) => {
            if (!value) return;
            const segment = (value / total) * Math.PI * 2;
            const gap = Math.min(0.035, segment * 0.09);
            context.beginPath();
            context.arc(center, center, radius, start + gap, start + segment - gap);
            context.strokeStyle = colors[index];
            context.lineWidth = lineWidth;
            context.stroke();
            start += segment;
        });
    };

    const drawHorizontalBars = (canvasId, data, valueKey, maxItems, heightPerRow) => {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !Array.isArray(data) || !data.length) return;
        const rows = data.slice(0, maxItems);
        const height = Math.max(230, rows.length * heightPerRow + 34);
        const { context, width } = setupCanvas(canvas, height);
        const primary = primaryColor();
        const labelWidth = Math.min(150, width * 0.38);
        const rightPadding = 34;
        const barWidth = Math.max(width - labelWidth - rightPadding - 18, 80);
        const maximum = Math.max(...rows.map((row) => Number(row[valueKey] || 0)), 1);

        context.clearRect(0, 0, width, height);
        context.font = "11px Inter, system-ui, sans-serif";
        context.textBaseline = "middle";

        rows.forEach((row, index) => {
            const value = Number(row[valueKey] || 0);
            const y = 22 + index * heightPerRow;
            const barY = y - 7;
            const actualWidth = (value / maximum) * barWidth;

            context.fillStyle = "#64736b";
            context.textAlign = "left";
            const label = String(row.name || row.id || "Sensor");
            const shortLabel = label.length > 20 ? `${label.slice(0, 18)}…` : label;
            context.fillText(shortLabel, 0, y);

            context.fillStyle = "#edf2ef";
            context.fillRect(labelWidth, barY, barWidth, 14);
            context.fillStyle = primary;
            context.fillRect(labelWidth, barY, actualWidth, 14);

            context.fillStyle = "#3a4d43";
            context.textAlign = "right";
            context.fillText(String(value), width - 2, y);
        });
    };

    const drawSensorTypes = () => {
        drawHorizontalBars(
            "sensor-types-chart",
            readPayload("sensor-types-data", []),
            "count",
            7,
            33,
        );
    };

    const drawMetricCoverage = () => {
        drawHorizontalBars(
            "metric-coverage-chart",
            readPayload("metric-coverage-data", []),
            "sensor_count",
            10,
            30,
        );
    };

    const installMetricSelector = () => {
        const metric = document.getElementById("metric-select");
        const probe = document.getElementById("probe-input");
        if (!metric || !probe) return;
        metric.addEventListener("change", () => {
            probe.value = metric.options[metric.selectedIndex]?.dataset.probe || "0";
        });
    };

    const installSensorSearch = () => {
        const search = document.getElementById("sensor-search");
        const rows = [...document.querySelectorAll(".sensor-row")];
        if (!search || !rows.length) return;

        search.addEventListener("input", () => {
            const query = search.value.trim().toLocaleLowerCase("es");
            rows.forEach((row) => {
                const haystack = String(row.dataset.search || "").toLocaleLowerCase("es");
                row.hidden = Boolean(query) && !haystack.includes(query);
            });
        });
    };

    const renderCharts = () => {
        drawTrend();
        drawFleetHealth();
        drawSensorTypes();
        drawMetricCoverage();
    };

    document.addEventListener("DOMContentLoaded", () => {
        renderCharts();
        installTrendTooltip();
        installMetricSelector();
        installSensorSearch();

        let resizeTimer;
        window.addEventListener("resize", () => {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(renderCharts, 140);
        });
    });
})();
