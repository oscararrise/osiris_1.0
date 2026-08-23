(() => {
    const readPayload = (id, fallback = []) => {
        const node = document.getElementById(id);
        if (!node) return fallback;
        try {
            return JSON.parse(node.textContent);
        } catch (_error) {
            return fallback;
        }
    };

    const cssColor = (name, fallback) =>
        getComputedStyle(document.body).getPropertyValue(name).trim() || fallback;

    const fitCanvas = (canvas, height) => {
        const parent = canvas.parentElement;
        const width = Math.max(parent.clientWidth, 280);
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        const context = canvas.getContext("2d");
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        context.clearRect(0, 0, width, height);
        return { context, width, height };
    };

    const extent = (values) => {
        if (!values.length) return [0, 1];
        let minimum = Math.min(...values);
        let maximum = Math.max(...values);
        if (minimum === maximum) {
            const padding = Math.max(Math.abs(minimum) * 0.1, 1);
            minimum -= padding;
            maximum += padding;
        } else {
            const padding = (maximum - minimum) * 0.08;
            minimum -= padding;
            maximum += padding;
        }
        return [minimum, maximum];
    };

    const drawAxes = (context, width, height, padding, xTicks = 4, yTicks = 4) => {
        const grid = "#e6ece9";
        const text = "#7a8982";
        context.font = "10px Inter, system-ui, sans-serif";
        context.lineWidth = 1;
        context.strokeStyle = grid;
        context.fillStyle = text;

        for (let index = 0; index <= yTicks; index += 1) {
            const y = padding.top + ((height - padding.top - padding.bottom) * index) / yTicks;
            context.beginPath();
            context.moveTo(padding.left, y);
            context.lineTo(width - padding.right, y);
            context.stroke();
        }
        for (let index = 0; index <= xTicks; index += 1) {
            const x = padding.left + ((width - padding.left - padding.right) * index) / xTicks;
            context.beginPath();
            context.moveTo(x, padding.top);
            context.lineTo(x, height - padding.bottom);
            context.stroke();
        }
    };

    const drawCorrelation = () => {
        const canvas = document.getElementById("correlation-chart");
        if (!canvas) return;
        const pairs = readPayload("correlation-data", []).filter(
            (row) => Number.isFinite(Number(row.primary)) && Number.isFinite(Number(row.secondary)),
        );
        const { context, width, height } = fitCanvas(canvas, 310);
        const padding = { top: 18, right: 22, bottom: 44, left: 58 };
        drawAxes(context, width, height, padding);
        if (!pairs.length) {
            context.fillStyle = "#7a8982";
            context.font = "12px Inter, system-ui, sans-serif";
            context.textAlign = "center";
            context.fillText("No hay buckets coincidentes para comparar", width / 2, height / 2);
            return;
        }

        const xs = pairs.map((row) => Number(row.primary));
        const ys = pairs.map((row) => Number(row.secondary));
        const [minX, maxX] = extent(xs);
        const [minY, maxY] = extent(ys);
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        const x = (value) => padding.left + ((value - minX) / (maxX - minX)) * chartWidth;
        const y = (value) => padding.top + (1 - (value - minY) / (maxY - minY)) * chartHeight;
        const primary = cssColor("--client-primary", "#176247");

        context.fillStyle = primary;
        pairs.forEach((row) => {
            context.globalAlpha = 0.58;
            context.beginPath();
            context.arc(x(Number(row.primary)), y(Number(row.secondary)), 3.4, 0, Math.PI * 2);
            context.fill();
        });
        context.globalAlpha = 1;

        const meanX = xs.reduce((sum, value) => sum + value, 0) / xs.length;
        const meanY = ys.reduce((sum, value) => sum + value, 0) / ys.length;
        const denominator = xs.reduce((sum, value) => sum + (value - meanX) ** 2, 0);
        if (denominator > 0) {
            const slope = xs.reduce(
                (sum, value, index) => sum + (value - meanX) * (ys[index] - meanY),
                0,
            ) / denominator;
            const intercept = meanY - slope * meanX;
            const startY = slope * minX + intercept;
            const endY = slope * maxX + intercept;
            context.strokeStyle = primary;
            context.lineWidth = 2;
            context.setLineDash([7, 5]);
            context.beginPath();
            context.moveTo(x(minX), y(startY));
            context.lineTo(x(maxX), y(endY));
            context.stroke();
            context.setLineDash([]);
        }

        context.fillStyle = "#7a8982";
        context.font = "10px Inter, system-ui, sans-serif";
        context.textAlign = "center";
        for (let index = 0; index <= 4; index += 1) {
            const value = minX + ((maxX - minX) * index) / 4;
            context.fillText(value.toFixed(1), padding.left + (chartWidth * index) / 4, height - 18);
        }
        context.textAlign = "right";
        for (let index = 0; index <= 4; index += 1) {
            const value = maxY - ((maxY - minY) * index) / 4;
            context.fillText(value.toFixed(1), padding.left - 9, padding.top + (chartHeight * index) / 4 + 3);
        }
    };

    const drawHourlyProfile = () => {
        const canvas = document.getElementById("hourly-profile-chart");
        if (!canvas) return;
        const rows = readPayload("hourly-profile-data", []);
        const valid = rows.filter((row) => row.average !== null && Number.isFinite(Number(row.average)));
        const { context, width, height } = fitCanvas(canvas, 260);
        const padding = { top: 18, right: 16, bottom: 36, left: 48 };
        drawAxes(context, width, height, padding, 6, 4);
        if (!valid.length) return;

        const values = valid.map((row) => Number(row.average));
        const [minimum, maximum] = extent(values);
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        const barWidth = Math.max((chartWidth / 24) * 0.58, 2);
        const primary = cssColor("--client-primary", "#176247");

        rows.forEach((row) => {
            if (row.average === null || !Number.isFinite(Number(row.average))) return;
            const value = Number(row.average);
            const x = padding.left + ((Number(row.hour) + 0.5) / 24) * chartWidth;
            const y = padding.top + (1 - (value - minimum) / (maximum - minimum)) * chartHeight;
            context.fillStyle = primary;
            context.globalAlpha = 0.78;
            context.fillRect(x - barWidth / 2, y, barWidth, height - padding.bottom - y);
        });
        context.globalAlpha = 1;
        context.fillStyle = "#75847d";
        context.font = "10px Inter, system-ui, sans-serif";
        context.textAlign = "center";
        [0, 4, 8, 12, 16, 20, 23].forEach((hour) => {
            const x = padding.left + ((hour + 0.5) / 24) * chartWidth;
            context.fillText(`${String(hour).padStart(2, "0")}:00`, x, height - 15);
        });
    };

    const drawDistribution = () => {
        const canvas = document.getElementById("distribution-chart");
        if (!canvas) return;
        const bins = readPayload("distribution-data", []).filter((row) => Number(row.count) >= 0);
        const { context, width, height } = fitCanvas(canvas, 260);
        const padding = { top: 18, right: 16, bottom: 42, left: 42 };
        drawAxes(context, width, height, padding, 5, 4);
        if (!bins.length) return;

        const maxCount = Math.max(...bins.map((row) => Number(row.count)), 1);
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        const slot = chartWidth / bins.length;
        const primary = cssColor("--client-primary", "#176247");

        bins.forEach((row, index) => {
            const count = Number(row.count);
            const barHeight = (count / maxCount) * chartHeight;
            context.fillStyle = primary;
            context.globalAlpha = 0.72 + (index / Math.max(bins.length - 1, 1)) * 0.22;
            context.fillRect(
                padding.left + index * slot + slot * 0.08,
                height - padding.bottom - barHeight,
                slot * 0.84,
                barHeight,
            );
        });
        context.globalAlpha = 1;
        context.fillStyle = "#75847d";
        context.font = "10px Inter, system-ui, sans-serif";
        context.textAlign = "center";
        const first = bins[0];
        const last = bins[bins.length - 1];
        context.fillText(Number(first.start).toFixed(1), padding.left, height - 15);
        context.fillText(
            Number((Number(first.start) + Number(last.end)) / 2).toFixed(1),
            padding.left + chartWidth / 2,
            height - 15,
        );
        context.fillText(Number(last.end).toFixed(1), width - padding.right, height - 15);
    };

    const drawFleetBenchmark = () => {
        const canvas = document.getElementById("fleet-benchmark-chart");
        if (!canvas) return;
        const rawRows = readPayload("fleet-metric-data", []).filter((row) => Number.isFinite(Number(row.value)));
        let rows = rawRows.slice(0, 12);
        const selectedRow = rawRows.find((row) => {
            const selected = document.querySelector(".vxa-benchmark-table .selected-row");
            if (!selected) return false;
            const selectedName = selected.querySelector("td:nth-child(2) strong")?.textContent?.trim();
            return selectedName && row.sensor_name === selectedName;
        });
        if (selectedRow && !rows.some((row) => row.sensor_id === selectedRow.sensor_id)) {
            rows = [...rows.slice(0, 11), selectedRow];
        }

        const height = Math.max(300, rows.length * 27 + 60);
        const { context, width } = fitCanvas(canvas, height);
        if (!rows.length) return;
        const padding = { top: 16, right: 52, bottom: 28, left: Math.min(Math.max(width * 0.26, 105), 185) };
        const values = rows.map((row) => Number(row.value));
        const minimum = Math.min(...values);
        const maximum = Math.max(...values);
        const baseline = minimum > 0 ? 0 : minimum;
        const range = maximum - baseline || 1;
        const chartWidth = width - padding.left - padding.right;
        const slot = (height - padding.top - padding.bottom) / rows.length;
        const primary = cssColor("--client-primary", "#176247");

        context.font = "10px Inter, system-ui, sans-serif";
        rows.forEach((row, index) => {
            const value = Number(row.value);
            const y = padding.top + index * slot + slot * 0.16;
            const barHeight = slot * 0.60;
            const barWidth = Math.max(((value - baseline) / range) * chartWidth, 2);
            const isSelected = selectedRow && row.sensor_id === selectedRow.sensor_id;
            context.fillStyle = isSelected ? primary : "#b8c8c1";
            context.fillRect(padding.left, y, barWidth, barHeight);
            context.fillStyle = isSelected ? "#173328" : "#596a62";
            context.textAlign = "right";
            const label = String(row.sensor_name || row.sensor_code || row.sensor_id).slice(0, 24);
            context.fillText(label, padding.left - 9, y + barHeight * 0.72);
            context.textAlign = "left";
            context.fillText(value.toFixed(1), padding.left + barWidth + 7, y + barHeight * 0.72);
        });
    };

    const wireFilters = () => {
        const metric = document.getElementById("metric-select");
        const probe = document.getElementById("probe-input");
        if (metric && probe) {
            metric.addEventListener("change", () => {
                probe.value = metric.options[metric.selectedIndex]?.dataset.probe || "0";
            });
        }

        const compareMetric = document.getElementById("compare-metric-select");
        const compareProbe = document.getElementById("compare-probe-input");
        if (compareMetric && compareProbe) {
            compareMetric.addEventListener("change", () => {
                compareProbe.value = compareMetric.options[compareMetric.selectedIndex]?.dataset.probe || "0";
            });
        }

        document.querySelectorAll(".vxa-metric-button").forEach((button) => {
            button.addEventListener("click", () => {
                const url = new URL(window.location.href);
                url.searchParams.set("metric", button.dataset.metricId || "");
                url.searchParams.set("probe", button.dataset.probe || "0");
                window.location.assign(url.toString());
            });
        });
    };

    const wireSectionNavigation = () => {
        document.querySelectorAll(".vxa-analysis-nav button").forEach((button) => {
            button.addEventListener("click", () => {
                document.querySelectorAll(".vxa-analysis-nav button").forEach((item) => item.classList.remove("active"));
                button.classList.add("active");
                const target = document.getElementById(button.dataset.scrollTarget || "");
                target?.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        });
    };

    const render = () => {
        drawCorrelation();
        drawHourlyProfile();
        drawDistribution();
        drawFleetBenchmark();
    };

    document.addEventListener("DOMContentLoaded", () => {
        wireFilters();
        wireSectionNavigation();
        render();
        let timer;
        window.addEventListener("resize", () => {
            window.clearTimeout(timer);
            timer = window.setTimeout(render, 140);
        });
    });
})();
