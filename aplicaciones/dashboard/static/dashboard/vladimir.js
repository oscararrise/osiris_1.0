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

    const numberPoints = (points) =>
        (points || []).filter((point) => Number.isFinite(Number(point.value)));

    const cssColor = (name, fallback) =>
        getComputedStyle(document.body).getPropertyValue(name).trim() || fallback;

    const hexToRgba = (hex, alpha) => {
        const clean = hex.replace("#", "").trim();
        if (!/^[0-9a-fA-F]{6}$/.test(clean)) return `rgba(23, 98, 71, ${alpha})`;
        const red = Number.parseInt(clean.slice(0, 2), 16);
        const green = Number.parseInt(clean.slice(2, 4), 16);
        const blue = Number.parseInt(clean.slice(4, 6), 16);
        return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
    };

    const setupCanvas = (canvas, height) => {
        const parentWidth = Math.max(canvas.parentElement.clientWidth, 320);
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(parentWidth * ratio);
        canvas.height = Math.floor(height * ratio);
        canvas.style.width = `${parentWidth}px`;
        canvas.style.height = `${height}px`;
        const context = canvas.getContext("2d");
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        return { context, width: parentWidth, height };
    };

    const drawComparisonChart = () => {
        const canvas = document.getElementById("comparison-chart");
        if (!canvas) return;

        const current = numberPoints(readPayload("current-series-data", []));
        const previous = numberPoints(readPayload("previous-series-data", []));
        if (!current.length && !previous.length) return;

        const { context, width, height } = setupCanvas(canvas, 345);
        const primary = cssColor("--client-primary", "#176247");
        const previousColor = "#aab6b0";
        const gridColor = "#e8eeeb";
        const textColor = "#78867f";
        const padding = { top: 24, right: 24, bottom: 48, left: 64 };
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        const allValues = [...current, ...previous].map((point) => Number(point.value));
        let minimum = Math.min(...allValues);
        let maximum = Math.max(...allValues);
        const spread = maximum - minimum || Math.max(Math.abs(maximum) * 0.1, 1);
        minimum -= spread * 0.12;
        maximum += spread * 0.12;

        const x = (index, length) =>
            padding.left + (index / Math.max(length - 1, 1)) * chartWidth;
        const y = (value) =>
            padding.top + (1 - (value - minimum) / (maximum - minimum)) * chartHeight;

        context.clearRect(0, 0, width, height);
        context.font = "11px Inter, system-ui, sans-serif";
        context.lineWidth = 1;
        context.textAlign = "right";
        context.textBaseline = "middle";

        for (let row = 0; row <= 4; row += 1) {
            const value = maximum - ((maximum - minimum) * row) / 4;
            const yPosition = padding.top + (chartHeight * row) / 4;
            context.strokeStyle = gridColor;
            context.beginPath();
            context.moveTo(padding.left, yPosition);
            context.lineTo(width - padding.right, yPosition);
            context.stroke();
            context.fillStyle = textColor;
            context.fillText(value.toFixed(1), padding.left - 11, yPosition);
        }

        const drawLine = (points, color, dashed, fill) => {
            if (!points.length) return;
            if (fill) {
                const gradient = context.createLinearGradient(0, padding.top, 0, height);
                gradient.addColorStop(0, hexToRgba(primary, 0.17));
                gradient.addColorStop(1, hexToRgba(primary, 0.01));
                context.beginPath();
                points.forEach((point, index) => {
                    const method = index === 0 ? "moveTo" : "lineTo";
                    context[method](x(index, points.length), y(Number(point.value)));
                });
                context.lineTo(x(points.length - 1, points.length), padding.top + chartHeight);
                context.lineTo(x(0, points.length), padding.top + chartHeight);
                context.closePath();
                context.fillStyle = gradient;
                context.fill();
            }

            context.save();
            context.beginPath();
            points.forEach((point, index) => {
                const method = index === 0 ? "moveTo" : "lineTo";
                context[method](x(index, points.length), y(Number(point.value)));
            });
            context.strokeStyle = color;
            context.lineWidth = dashed ? 1.8 : 2.7;
            context.lineJoin = "round";
            context.lineCap = "round";
            if (dashed) context.setLineDash([7, 6]);
            context.stroke();
            context.restore();
        };

        drawLine(previous, previousColor, true, false);
        drawLine(current, primary, false, true);

        if (current.length) {
            const indexes = [0, Math.floor((current.length - 1) / 2), current.length - 1];
            context.textBaseline = "top";
            [...new Set(indexes)].forEach((index) => {
                const date = new Date(current[index].measured_at);
                context.textAlign = index === 0 ? "left" : index === current.length - 1 ? "right" : "center";
                context.fillStyle = textColor;
                context.fillText(
                    date.toLocaleString("es-CO", {
                        day: "2-digit",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                    }),
                    x(index, current.length),
                    padding.top + chartHeight + 16,
                );
            });
        }

        canvas.dataset.chartLeft = String(padding.left);
        canvas.dataset.chartWidth = String(chartWidth);
        canvas._vxCurrent = current;
        canvas._vxPrevious = previous;
        canvas._vxX = x;
        canvas._vxY = y;
        canvas._vxDimensions = { padding, chartHeight };
    };

    const installTooltip = () => {
        const canvas = document.getElementById("comparison-chart");
        const tooltip = document.getElementById("comparison-tooltip");
        if (!canvas || !tooltip) return;

        canvas.addEventListener("mousemove", (event) => {
            const current = canvas._vxCurrent || [];
            if (!current.length) return;
            const rect = canvas.getBoundingClientRect();
            const pointerX = event.clientX - rect.left;
            const chartLeft = Number(canvas.dataset.chartLeft || 0);
            const chartWidth = Number(canvas.dataset.chartWidth || 1);
            const ratio = Math.min(Math.max((pointerX - chartLeft) / chartWidth, 0), 1);
            const index = Math.round(ratio * Math.max(current.length - 1, 0));
            const point = current[index];
            const previous = canvas._vxPrevious || [];
            const previousIndex = previous.length
                ? Math.round((index / Math.max(current.length - 1, 1)) * (previous.length - 1))
                : -1;
            const previousPoint = previousIndex >= 0 ? previous[previousIndex] : null;
            const xPosition = canvas._vxX(index, current.length);
            const yPosition = canvas._vxY(Number(point.value));
            const date = new Date(point.measured_at);
            const previousText = previousPoint
                ? `<br>Anterior: <strong>${Number(previousPoint.value).toFixed(2)}</strong>`
                : "";

            tooltip.innerHTML = `${date.toLocaleString("es-CO", {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
            })}<br>Actual: <strong>${Number(point.value).toFixed(2)}</strong>${previousText}`;
            tooltip.style.left = `${xPosition + 18}px`;
            tooltip.style.top = `${yPosition}px`;
            tooltip.hidden = false;
        });

        canvas.addEventListener("mouseleave", () => {
            tooltip.hidden = true;
        });
    };

    const drawFleetHealth = () => {
        const canvas = document.getElementById("fleet-health-chart");
        if (!canvas) return;
        const fleet = readPayload("fleet-health-data", null);
        if (!fleet) return;

        const ratio = window.devicePixelRatio || 1;
        const size = 230;
        canvas.width = size * ratio;
        canvas.height = size * ratio;
        canvas.style.width = `${size}px`;
        canvas.style.height = `${size}px`;
        const context = canvas.getContext("2d");
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        context.clearRect(0, 0, size, size);

        const values = [Number(fleet.online || 0), Number(fleet.delayed || 0), Number(fleet.offline || 0)];
        const colors = ["#2da97a", "#dfa142", "#cb6060"];
        const total = values.reduce((sum, value) => sum + value, 0);
        const center = size / 2;
        const radius = 84;
        const lineWidth = 18;

        context.lineCap = "round";
        if (!total) {
            context.beginPath();
            context.arc(center, center, radius, 0, Math.PI * 2);
            context.strokeStyle = "#e8eeeb";
            context.lineWidth = lineWidth;
            context.stroke();
            return;
        }

        let startAngle = -Math.PI / 2;
        values.forEach((value, index) => {
            if (!value) return;
            const segment = (value / total) * Math.PI * 2;
            const gap = Math.min(0.035, segment * 0.08);
            context.beginPath();
            context.arc(center, center, radius, startAngle + gap, startAngle + segment - gap);
            context.strokeStyle = colors[index];
            context.lineWidth = lineWidth;
            context.stroke();
            startAngle += segment;
        });
    };

    const render = () => {
        drawComparisonChart();
        drawFleetHealth();
    };

    document.addEventListener("DOMContentLoaded", () => {
        render();
        installTooltip();
        let resizeTimer;
        window.addEventListener("resize", () => {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(render, 120);
        });
    });
})();
