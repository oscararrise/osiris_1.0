(() => {
    const canvas = document.getElementById("trend-chart");
    const payload = document.getElementById("series-data");
    if (!canvas || !payload) return;

    const points = JSON.parse(payload.textContent).filter((point) => Number.isFinite(Number(point.value)));
    if (points.length < 1) return;

    const context = canvas.getContext("2d");
    const ratio = window.devicePixelRatio || 1;
    const containerWidth = canvas.parentElement.clientWidth;
    const width = Math.max(containerWidth, 320);
    const height = 310;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.scale(ratio, ratio);

    const padding = { top: 22, right: 18, bottom: 42, left: 58 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const values = points.map((point) => Number(point.value));
    let minimum = Math.min(...values);
    let maximum = Math.max(...values);
    const spread = maximum - minimum || Math.max(Math.abs(maximum) * 0.1, 1);
    minimum -= spread * 0.12;
    maximum += spread * 0.12;

    const x = (index) => padding.left + (index / Math.max(points.length - 1, 1)) * chartWidth;
    const y = (value) => padding.top + (1 - (value - minimum) / (maximum - minimum)) * chartHeight;
    const primary = getComputedStyle(document.body).getPropertyValue("--client-primary").trim() || "#176247";

    context.font = "12px Inter, system-ui, sans-serif";
    context.lineWidth = 1;
    context.textAlign = "right";
    context.textBaseline = "middle";
    for (let row = 0; row <= 4; row += 1) {
        const value = maximum - ((maximum - minimum) * row) / 4;
        const yPosition = padding.top + (chartHeight * row) / 4;
        context.strokeStyle = "#e8eeeb";
        context.beginPath();
        context.moveTo(padding.left, yPosition);
        context.lineTo(width - padding.right, yPosition);
        context.stroke();
        context.fillStyle = "#73817b";
        context.fillText(value.toFixed(1), padding.left - 10, yPosition);
    }

    const gradient = context.createLinearGradient(0, padding.top, 0, padding.top + chartHeight);
    gradient.addColorStop(0, `${primary}32`);
    gradient.addColorStop(1, `${primary}02`);
    context.beginPath();
    points.forEach((point, index) => {
        const command = index === 0 ? "moveTo" : "lineTo";
        context[command](x(index), y(Number(point.value)));
    });
    context.lineTo(x(points.length - 1), padding.top + chartHeight);
    context.lineTo(x(0), padding.top + chartHeight);
    context.closePath();
    context.fillStyle = gradient;
    context.fill();

    context.beginPath();
    points.forEach((point, index) => {
        const command = index === 0 ? "moveTo" : "lineTo";
        context[command](x(index), y(Number(point.value)));
    });
    context.strokeStyle = primary;
    context.lineWidth = 2.5;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.stroke();

    const labelIndexes = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
    context.textBaseline = "top";
    labelIndexes.forEach((index) => {
        const date = new Date(points[index].measured_at);
        context.textAlign = index === 0 ? "left" : index === points.length - 1 ? "right" : "center";
        context.fillStyle = "#73817b";
        context.fillText(
            date.toLocaleString("es-CO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }),
            x(index),
            padding.top + chartHeight + 15,
        );
    });
})();
