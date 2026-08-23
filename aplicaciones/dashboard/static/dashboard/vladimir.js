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

    const cssColor = (name, fallback) =>
        getComputedStyle(document.body).getPropertyValue(name).trim() || fallback;

    const setupCanvas = (canvas, height) => {
        const width = Math.max(canvas.parentElement.clientWidth, 320);
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        const context = canvas.getContext("2d");
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        return { context, width, height };
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
        const radius = 78;
        const lineWidth = 17;

        context.lineCap = "round";
        if (!total) {
            context.beginPath();
            context.arc(center, center, radius, 0, Math.PI * 2);
            context.strokeStyle = "#e8eeeb";
            context.lineWidth = lineWidth;
            context.stroke();
            return;
        }

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

    const numericSeries = () =>
        readPayload("sensor-series-data", []).filter((point) => Number.isFinite(Number(point.value)));

    const drawTrend = () => {
        const canvas = document.getElementById("sensor-trend-chart");
        if (!canvas) return;
        const series = numericSeries();
        if (!series.length) return;

        const { context, width, height } = setupCanvas(canvas, 330);
        const primary = cssColor("--client-primary", "#176247");
        const padding = { top: 24, right: 24, bottom: 48, left: 62 };
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
            context.fillStyle = "#78867f";
            context.textAlign = "right";
            context.fillText(value.toFixed(1), padding.left - 10, yPosition);
        }

        context.beginPath();
        series.forEach((point, index) => {
            const high = Number(point.maximum ?? point.value);
            const method = index === 0 ? "moveTo" : "lineTo";
            context[method](x(index), y(high));
        });
        for (let index = series.length - 1; index >= 0; index -= 1) {
            const point = series[index];
            const low = Number(point.minimum ?? point.value);
            context.lineTo(x(index), y(low));
        }
        context.closePath();
        context.fillStyle = "rgba(23, 98, 71, 0.08)";
        context.fill();

        context.beginPath();
        series.forEach((point, index) => {
            const method = index === 0 ? "moveTo" : "lineTo";
            context[method](x(index), y(Number(point.value)));
        });
        context.strokeStyle = primary;
        context.lineWidth = 2.6;
        context.lineJoin = "round";
        context.lineCap = "round";
        context.stroke();

        const labelIndexes = [0, Math.floor((series.length - 1) / 2), series.length - 1];
        context.textBaseline = "top";
        [...new Set(labelIndexes)].forEach((index) => {
            const date = new Date(series[index].measured_at);
            context.textAlign = index === 0 ? "left" : index === series.length - 1 ? "right" : "center";
            context.fillStyle = "#78867f";
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
            const date = new Date(point.measured_at);
            const minimum = Number(point.minimum ?? point.value);
            const maximum = Number(point.maximum ?? point.value);

            tooltip.innerHTML = `${date.toLocaleString("es-CO", {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
            })}<br>Promedio: <strong>${Number(point.value).toFixed(2)}</strong><br>` +
                `Rango del bucket: ${minimum.toFixed(2)} – ${maximum.toFixed(2)}`;
            tooltip.style.left = `${canvas._aranetX(index) + 16}px`;
            tooltip.style.top = `${canvas._aranetY(Number(point.value))}px`;
            tooltip.hidden = false;
        });

        canvas.addEventListener("mouseleave", () => {
            tooltip.hidden = true;
        });
    };

    const installInventoryFilters = () => {
        const rows = [...document.querySelectorAll(".sensor-row")];
        if (!rows.length) return;

        const search = document.getElementById("sensor-search");
        const location = document.getElementById("filter-location");
        const type = document.getElementById("filter-type");
        const base = document.getElementById("filter-base");
        const status = document.getElementById("filter-status");
        const clear = document.getElementById("clear-filters");
        const counter = document.getElementById("sensor-result-count");

        const normalise = (value) => String(value || "").trim().toLocaleLowerCase("es");
        const apply = () => {
            const text = normalise(search?.value);
            const expectedLocation = normalise(location?.value);
            const expectedType = normalise(type?.value);
            const expectedBase = normalise(base?.value);
            const expectedStatus = normalise(status?.value);
            let visible = 0;

            rows.forEach((row) => {
                const matches =
                    (!text || normalise(row.dataset.search).includes(text)) &&
                    (!expectedLocation || normalise(row.dataset.location) === expectedLocation) &&
                    (!expectedType || normalise(row.dataset.type) === expectedType) &&
                    (!expectedBase || normalise(row.dataset.base) === expectedBase) &&
                    (!expectedStatus || normalise(row.dataset.status) === expectedStatus);
                row.hidden = !matches;
                if (matches) visible += 1;
            });
            if (counter) counter.textContent = `${visible} sensor${visible === 1 ? "" : "es"}`;
        };

        [search, location, type, base, status].forEach((control) => {
            control?.addEventListener(control === search ? "input" : "change", apply);
        });
        clear?.addEventListener("click", () => {
            if (search) search.value = "";
            [location, type, base, status].forEach((control) => {
                if (control) control.value = "";
            });
            apply();
        });
    };

    const installMetricSelector = () => {
        const metric = document.getElementById("metric-select");
        const probe = document.getElementById("probe-input");
        if (!metric || !probe) return;
        metric.addEventListener("change", () => {
            probe.value = metric.options[metric.selectedIndex]?.dataset.probe || "0";
        });
    };

    const renderCharts = () => {
        drawFleetHealth();
        drawTrend();
    };

    document.addEventListener("DOMContentLoaded", () => {
        renderCharts();
        installTrendTooltip();
        installInventoryFilters();
        installMetricSelector();

        let resizeTimer;
        window.addEventListener("resize", () => {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(renderCharts, 120);
        });
    });
})();
