(() => {
    const shell = document.getElementById("relationship-detail");
    if (!shell) return;

    const apiUrl = shell.dataset.apiUrl;
    const alertUrl = shell.dataset.alertUrl;
    const canEdit = shell.dataset.canEdit === "1";
    const palette = ["#176247", "#d58b3e", "#4d7ea8", "#a45a77", "#6f8d52", "#7a63a8"];
    let payload = null;
    let selectedRange = "24h";
    let resizeTimer = null;

    const escapeHtml = (value) =>
        String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");

    const csrfToken = () => {
        const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (input?.value) return input.value;
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    };

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

    const niceNumber = (value, digits = 2) => {
        if (value == null || !Number.isFinite(Number(value))) return "—";
        return Number(value).toLocaleString("es-CO", {
            maximumFractionDigits: digits,
            minimumFractionDigits: 0,
        });
    };

    const formatDate = (value, long = false) => {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "—";
        return date.toLocaleString("es-CO", long
            ? { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
            : { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
    };

    const variableStats = (variable) => payload?.statistics?.[variable.key] || {};

    const renderKpis = () => {
        const container = document.getElementById("relationship-kpis");
        const variables = (payload.variables || []).filter((item) => item.available);
        container.innerHTML = variables
            .map((variable) => {
                const stats = variableStats(variable);
                return `
                    <article class="relationship-kpi">
                        <span>${escapeHtml(variable.derived ? "Variable derivada" : variable.sensor_name)}</span>
                        <strong>${niceNumber(stats.current)} ${escapeHtml(variable.unit || "")}</strong>
                        <small>${escapeHtml(variable.name)} · min ${niceNumber(stats.minimum)} · prom ${niceNumber(stats.average)} · max ${niceNumber(stats.maximum)}</small>
                    </article>
                `;
            })
            .join("");
    };

    const valueRange = (rows, key) => {
        const values = rows
            .map((row) => row.values?.[key])
            .filter((value) => value != null && Number.isFinite(Number(value)))
            .map(Number);
        if (!values.length) return null;
        let minimum = Math.min(...values);
        let maximum = Math.max(...values);
        const spread = maximum - minimum || Math.max(Math.abs(maximum) * 0.1, 1);
        minimum -= spread * 0.1;
        maximum += spread * 0.1;
        return { minimum, maximum };
    };

    const drawTrend = () => {
        const canvas = document.getElementById("relationship-trend-chart");
        if (!canvas || !payload) return;
        const rows = payload.rows || [];
        const variables = (payload.variables || []).filter((item) => item.available);
        if (!rows.length || !variables.length) return;

        const { context, width, height } = setupCanvas(canvas, 350);
        const padding = { top: 28, right: 70, bottom: 48, left: 70 };
        const chartWidth = Math.max(width - padding.left - padding.right, 20);
        const chartHeight = Math.max(height - padding.top - padding.bottom, 20);
        const ranges = Object.fromEntries(
            variables.map((variable) => [variable.key, valueRange(rows, variable.key)])
        );
        const x = (index) => padding.left + (index / Math.max(rows.length - 1, 1)) * chartWidth;
        const yFor = (key, value) => {
            const range = ranges[key];
            if (!range) return padding.top + chartHeight / 2;
            return padding.top + (1 - (Number(value) - range.minimum) / (range.maximum - range.minimum)) * chartHeight;
        };

        context.clearRect(0, 0, width, height);
        context.font = "11px Inter, system-ui, sans-serif";
        context.textBaseline = "middle";

        for (let rowIndex = 0; rowIndex <= 4; rowIndex += 1) {
            const y = padding.top + (chartHeight * rowIndex) / 4;
            context.strokeStyle = "#e8eeeb";
            context.lineWidth = 1;
            context.beginPath();
            context.moveTo(padding.left, y);
            context.lineTo(width - padding.right, y);
            context.stroke();
        }

        [variables[0], variables[1]].filter(Boolean).forEach((variable, axisIndex) => {
            const range = ranges[variable.key];
            if (!range) return;
            for (let tick = 0; tick <= 4; tick += 1) {
                const value = range.maximum - ((range.maximum - range.minimum) * tick) / 4;
                const y = padding.top + (chartHeight * tick) / 4;
                context.fillStyle = palette[axisIndex];
                context.textAlign = axisIndex === 0 ? "right" : "left";
                context.fillText(
                    `${niceNumber(value, 1)}${variable.unit ? ` ${variable.unit}` : ""}`,
                    axisIndex === 0 ? padding.left - 10 : width - padding.right + 10,
                    y,
                );
            }
        });

        variables.forEach((variable, variableIndex) => {
            context.beginPath();
            let started = false;
            rows.forEach((row, index) => {
                const value = row.values?.[variable.key];
                if (value == null || !ranges[variable.key]) return;
                if (!started) {
                    context.moveTo(x(index), yFor(variable.key, value));
                    started = true;
                } else {
                    context.lineTo(x(index), yFor(variable.key, value));
                }
            });
            context.strokeStyle = palette[variableIndex % palette.length];
            context.lineWidth = variable.derived ? 2.2 : 2.6;
            context.setLineDash(variable.derived ? [6, 4] : []);
            context.lineJoin = "round";
            context.lineCap = "round";
            context.stroke();
            context.setLineDash([]);
        });

        const labelIndexes = [0, Math.floor((rows.length - 1) / 2), rows.length - 1];
        [...new Set(labelIndexes)].forEach((index) => {
            context.fillStyle = "#7b8982";
            context.textBaseline = "top";
            context.textAlign = index === 0 ? "left" : index === rows.length - 1 ? "right" : "center";
            context.fillText(formatDate(rows[index].measured_at), x(index), padding.top + chartHeight + 15);
        });

        canvas._relationshipRows = rows;
        canvas._relationshipVariables = variables;
        canvas._relationshipX = x;
        canvas.dataset.left = String(padding.left);
        canvas.dataset.chartWidth = String(chartWidth);
    };

    const installTrendTooltip = () => {
        const canvas = document.getElementById("relationship-trend-chart");
        const tooltip = document.getElementById("relationship-trend-tooltip");
        if (!canvas || !tooltip || canvas.dataset.tooltipBound === "1") return;
        canvas.dataset.tooltipBound = "1";
        canvas.addEventListener("mousemove", (event) => {
            const rows = canvas._relationshipRows || [];
            const variables = canvas._relationshipVariables || [];
            if (!rows.length) return;
            const rect = canvas.getBoundingClientRect();
            const pointerX = event.clientX - rect.left;
            const left = Number(canvas.dataset.left || 0);
            const chartWidth = Number(canvas.dataset.chartWidth || 1);
            const ratio = Math.min(Math.max((pointerX - left) / chartWidth, 0), 1);
            const index = Math.round(ratio * Math.max(rows.length - 1, 0));
            const row = rows[index];
            tooltip.innerHTML = `<strong>${escapeHtml(formatDate(row.measured_at, true))}</strong><br>` + variables
                .map((variable) => `${escapeHtml(variable.name)}: <b>${niceNumber(row.values?.[variable.key])} ${escapeHtml(variable.unit || "")}</b>`)
                .join("<br>");
            tooltip.style.left = `${Math.min(canvas._relationshipX(index) + 14, rect.width - 190)}px`;
            tooltip.style.top = "35px";
            tooltip.hidden = false;
        });
        canvas.addEventListener("mouseleave", () => { tooltip.hidden = true; });
    };

    const drawScatter = () => {
        const canvas = document.getElementById("relationship-scatter-chart");
        const vpd = (payload.variables || []).find((item) => item.key === "__vpd__");
        if (!canvas || !vpd) return;
        const temperature = (payload.variables || []).find((item) => item.key === vpd.temperature_key);
        const humidity = (payload.variables || []).find((item) => item.key === vpd.humidity_key);
        const points = (payload.rows || [])
            .map((row) => ({ x: row.values?.[vpd.temperature_key], y: row.values?.[vpd.humidity_key] }))
            .filter((point) => point.x != null && point.y != null)
            .map((point) => ({ x: Number(point.x), y: Number(point.y) }));
        if (!points.length) return;

        const { context, width, height } = setupCanvas(canvas, 280);
        const padding = { top: 22, right: 25, bottom: 48, left: 58 };
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        let minX = Math.min(...points.map((point) => point.x));
        let maxX = Math.max(...points.map((point) => point.x));
        let minY = Math.min(...points.map((point) => point.y));
        let maxY = Math.max(...points.map((point) => point.y));
        const xSpread = maxX - minX || 1;
        const ySpread = maxY - minY || 1;
        minX -= xSpread * 0.08; maxX += xSpread * 0.08;
        minY -= ySpread * 0.08; maxY += ySpread * 0.08;
        const x = (value) => padding.left + ((value - minX) / (maxX - minX)) * chartWidth;
        const y = (value) => padding.top + (1 - (value - minY) / (maxY - minY)) * chartHeight;

        context.clearRect(0, 0, width, height);
        context.font = "11px Inter, system-ui, sans-serif";
        for (let tick = 0; tick <= 4; tick += 1) {
            const gridY = padding.top + (chartHeight * tick) / 4;
            const yValue = maxY - ((maxY - minY) * tick) / 4;
            context.strokeStyle = "#e9efec";
            context.beginPath(); context.moveTo(padding.left, gridY); context.lineTo(width - padding.right, gridY); context.stroke();
            context.fillStyle = "#7a8982"; context.textAlign = "right"; context.textBaseline = "middle";
            context.fillText(niceNumber(yValue, 1), padding.left - 8, gridY);
        }
        points.forEach((point) => {
            context.beginPath(); context.arc(x(point.x), y(point.y), 3.2, 0, Math.PI * 2);
            context.fillStyle = "rgba(23,98,71,.55)"; context.fill();
        });
        context.fillStyle = "#667a70"; context.textAlign = "center"; context.textBaseline = "bottom";
        context.fillText(`${temperature?.name || "Temperatura"} (${temperature?.unit || "°C"})`, padding.left + chartWidth / 2, height - 5);
        context.save(); context.translate(13, padding.top + chartHeight / 2); context.rotate(-Math.PI / 2);
        context.fillText(`${humidity?.name || "Humedad"} (${humidity?.unit || "%"})`, 0, 0); context.restore();
    };

    const drawVpd = () => {
        const canvas = document.getElementById("relationship-vpd-chart");
        const rows = (payload.rows || []).filter((row) => row.values?.__vpd__ != null);
        if (!canvas || !rows.length) return;
        const { context, width, height } = setupCanvas(canvas, 280);
        const padding = { top: 22, right: 22, bottom: 45, left: 55 };
        const chartWidth = width - padding.left - padding.right;
        const chartHeight = height - padding.top - padding.bottom;
        const values = rows.map((row) => Number(row.values.__vpd__));
        let minimum = Math.min(...values); let maximum = Math.max(...values);
        const spread = maximum - minimum || 0.5; minimum = Math.max(0, minimum - spread * 0.12); maximum += spread * 0.12;
        const x = (index) => padding.left + (index / Math.max(rows.length - 1, 1)) * chartWidth;
        const y = (value) => padding.top + (1 - (value - minimum) / (maximum - minimum)) * chartHeight;
        context.clearRect(0, 0, width, height); context.font = "11px Inter, system-ui, sans-serif";
        for (let tick = 0; tick <= 4; tick += 1) {
            const gridY = padding.top + (chartHeight * tick) / 4;
            const value = maximum - ((maximum - minimum) * tick) / 4;
            context.strokeStyle = "#e9efec"; context.beginPath(); context.moveTo(padding.left, gridY); context.lineTo(width - padding.right, gridY); context.stroke();
            context.fillStyle = "#7a8982"; context.textAlign = "right"; context.textBaseline = "middle"; context.fillText(`${niceNumber(value, 2)}`, padding.left - 8, gridY);
        }
        context.beginPath(); rows.forEach((row, index) => context[index ? "lineTo" : "moveTo"](x(index), y(Number(row.values.__vpd__))));
        context.strokeStyle = "#d58b3e"; context.lineWidth = 2.6; context.lineJoin = "round"; context.stroke();
        context.fillStyle = "#697b72"; context.textAlign = "right"; context.textBaseline = "bottom"; context.fillText("kPa", width - padding.right, 15);
    };

    const renderLegend = () => {
        const legend = document.getElementById("relationship-legend");
        legend.innerHTML = (payload.variables || []).filter((item) => item.available).map((variable, index) => `
            <span><i style="background:${palette[index % palette.length]}"></i>${escapeHtml(variable.sensor_name)} · <b>${escapeHtml(variable.name)}</b>${variable.unit ? ` (${escapeHtml(variable.unit)})` : ""}</span>
        `).join("");
    };

    const renderTable = () => {
        const variables = (payload.variables || []).filter((item) => item.available);
        const head = document.getElementById("relationship-table-head");
        const body = document.getElementById("relationship-table-body");
        head.innerHTML = `<tr><th>Fecha / hora</th>${variables.map((variable) => `<th>${escapeHtml(variable.name)}${variable.unit ? ` · ${escapeHtml(variable.unit)}` : ""}</th>`).join("")}</tr>`;
        body.innerHTML = (payload.latest_rows || []).map((row) => `
            <tr><td>${escapeHtml(formatDate(row.measured_at, true))}</td>${variables.map((variable) => `<td>${niceNumber(row.values?.[variable.key])}</td>`).join("")}</tr>
        `).join("") || `<tr><td colspan="${variables.length + 1}">No hay registros para este periodo.</td></tr>`;
        const latest = payload.rows?.[payload.rows.length - 1];
        document.getElementById("relationship-last-update").textContent = latest ? `Último intervalo: ${formatDate(latest.measured_at, true)}` : "Sin registros";
    };

    const renderAlerts = () => {
        const list = document.getElementById("relationship-alert-list");
        const alerts = payload.alerts || [];
        if (!alerts.length) {
            list.innerHTML = `<div class="relationship-empty">Todavía no hay alertas configuradas para esta relación.</div>`;
            return;
        }
        list.innerHTML = alerts.map((alert) => {
            const evaluation = alert.evaluation || {};
            const status = !alert.is_enabled ? "PAUSADA" : evaluation.triggered_preview ? "CONDICIÓN ACTIVA" : "NORMAL";
            return `
                <article class="relationship-alert-card">
                    <div class="top">
                        <div><h3>${escapeHtml(alert.name)}</h3><p>${escapeHtml(alert.severity_label)} · duración ${alert.duration_minutes} min · cooldown ${alert.cooldown_minutes} min</p></div>
                        <span class="status ${evaluation.triggered_preview ? "triggered" : ""}">${status}</span>
                    </div>
                    <p><b>${escapeHtml(alert.variable_a_sensor)} · ${escapeHtml(alert.variable_a_name)}</b> ${escapeHtml(alert.operator_a_label)} ${niceNumber(alert.threshold_a)} <strong>${escapeHtml(alert.logic_label)}</strong> <b>${escapeHtml(alert.variable_b_sensor)} · ${escapeHtml(alert.variable_b_name)}</b> ${escapeHtml(alert.operator_b_label)} ${niceNumber(alert.threshold_b)}.</p>
                    <p>Vista previa: ${niceNumber(evaluation.sustained_minutes, 0)} min consecutivos cumpliendo la regla en los datos cargados.</p>
                    ${canEdit ? `<button type="button" data-delete-alert="${alert.id}">Eliminar alerta</button>` : ""}
                </article>
            `;
        }).join("");
        list.querySelectorAll("[data-delete-alert]").forEach((button) => {
            button.addEventListener("click", () => deleteAlert(button.dataset.deleteAlert));
        });
    };

    const populateAlertForm = () => {
        const form = document.getElementById("relationship-alert-form");
        if (!form) return;
        const variables = payload.alert_variables || [];
        const options = variables.map((variable) => `<option value="${escapeHtml(variable.key)}">${escapeHtml(variable.sensor_name)} · ${escapeHtml(variable.name)}${variable.unit ? ` (${escapeHtml(variable.unit)})` : ""}</option>`).join("");
        form.elements.variable_a_key.innerHTML = options;
        form.elements.variable_b_key.innerHTML = options;
        if (variables.length > 1) form.elements.variable_b_key.selectedIndex = 1;
    };

    const render = () => {
        renderKpis(); renderLegend(); renderTable(); renderAlerts(); populateAlertForm();
        document.getElementById("relationship-bucket-note").textContent = `Intervalos de ${payload.bucket_minutes} min · ${payload.rows.length} puntos alineados.`;
        document.getElementById("relationship-derived-section").hidden = !payload.vpd_available;
        drawTrend(); installTrendTooltip();
        if (payload.vpd_available) { drawScatter(); drawVpd(); }
    };

    const setLoading = (loading) => {
        document.getElementById("relationship-loading").hidden = !loading;
        document.getElementById("relationship-content").hidden = loading;
    };

    const load = async (range = selectedRange) => {
        selectedRange = range;
        setLoading(true);
        const error = document.getElementById("relationship-error");
        error.hidden = true;
        try {
            const response = await fetch(`${apiUrl}?range=${encodeURIComponent(range)}`, { headers: { Accept: "application/json" } });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "No fue posible cargar la relación.");
            payload = data;
            document.querySelectorAll("#relationship-ranges [data-range]").forEach((button) => button.classList.toggle("active", button.dataset.range === selectedRange));
            setLoading(false);
            render();
        } catch (exception) {
            setLoading(false);
            document.getElementById("relationship-content").hidden = true;
            error.textContent = exception.message;
            error.hidden = false;
        }
    };

    const showAlertMessage = (message, isError = false) => {
        const node = document.getElementById("relationship-alert-message");
        if (!node) return;
        node.textContent = message;
        node.classList.toggle("error", isError);
        node.hidden = false;
    };

    const deleteAlert = async (alertId) => {
        const data = new FormData();
        data.append("action", "delete"); data.append("alert_id", alertId); data.append("csrfmiddlewaretoken", csrfToken());
        const response = await fetch(alertUrl, { method: "POST", body: data });
        const result = await response.json();
        if (!response.ok) { showAlertMessage(result.error || "No se pudo eliminar la alerta.", true); return; }
        await load(selectedRange);
    };

    const installAlertForm = () => {
        const form = document.getElementById("relationship-alert-form");
        if (!form) return;
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (form.elements.variable_a_key.value === form.elements.variable_b_key.value) {
                showAlertMessage("Selecciona dos variables diferentes.", true); return;
            }
            const data = new FormData(form);
            data.set("email_enabled", form.elements.email_enabled.checked ? "1" : "0");
            data.set("whatsapp_enabled", form.elements.whatsapp_enabled.checked ? "1" : "0");
            data.set("is_enabled", form.elements.is_enabled.checked ? "1" : "0");
            data.set("csrfmiddlewaretoken", csrfToken());
            const button = form.querySelector('button[type="submit"]'); button.disabled = true;
            try {
                const response = await fetch(alertUrl, { method: "POST", body: data });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || "No se pudo guardar la alerta.");
                showAlertMessage("Alerta guardada correctamente.");
                form.reset(); form.elements.duration_minutes.value = "10"; form.elements.cooldown_minutes.value = "30"; form.elements.severity.value = "medium"; form.elements.is_enabled.checked = true;
                await load(selectedRange);
            } catch (exception) {
                showAlertMessage(exception.message, true);
            } finally { button.disabled = false; }
        });
    };

    document.querySelectorAll("#relationship-ranges [data-range]").forEach((button) => button.addEventListener("click", () => load(button.dataset.range)));
    installAlertForm();
    window.addEventListener("resize", () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => { if (payload) { drawTrend(); if (payload.vpd_available) { drawScatter(); drawVpd(); } } }, 140);
    });
    load("24h");
})();
