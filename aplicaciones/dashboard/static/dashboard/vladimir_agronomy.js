(() => {
    const endpoint = "/s2/agronomy";

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

    const selectedSensorId = () =>
        String(document.getElementById("sensor-select")?.value || "").trim();

    const inventoryAnchor = () =>
        document.getElementById("sensor-search")?.closest(".aranet-section") || null;

    const compactInventory = () => {
        const anchor = inventoryAnchor();
        const wrapper = anchor?.querySelector(".aranet-table-wrap");
        if (wrapper) wrapper.classList.add("compact-sensor-inventory");
    };

    const createPanel = () => {
        const anchor = inventoryAnchor();
        if (!anchor || document.getElementById("agronomy-workbench")) return null;

        const panel = document.createElement("section");
        panel.id = "agronomy-workbench";
        panel.className = "agronomy-workbench";
        panel.innerHTML = `
            <header class="agronomy-head">
                <div>
                    <div class="agronomy-kicker"><i></i> AGRONOMIC INTELLIGENCE</div>
                    <h2>Relaciones entre variables</h2>
                    <p>Combina varias señales del sensor para interpretar el cultivo como un sistema y no como variables aisladas.</p>
                </div>
                <div class="agronomy-head-badge">
                    <span>Perfil activo</span>
                    <strong id="agronomy-profile-name">—</strong>
                    <small id="agronomy-sensor-name">Cargando sensor…</small>
                </div>
            </header>
            <div id="agronomy-body" class="agronomy-body">
                <div class="agronomy-loading"><span></span> Cargando variables disponibles…</div>
            </div>
        `;
        anchor.insertAdjacentElement("afterend", panel);
        return panel;
    };

    const metricLabel = (metric) => {
        const probe = Number(metric.probe_no || 0) ? ` · Sonda ${metric.probe_no}` : "";
        const unit = metric.unit ? ` · ${metric.unit}` : "";
        return `${metric.name}${probe}${unit}`;
    };

    const renderSuggestions = (suggestions) => {
        if (!suggestions.length) {
            return `
                <div class="agronomy-suggestion-empty">
                    <strong>No hay una combinación automática completa todavía.</strong>
                    <p>Puedes crear una relación personalizada con cualquiera de las variables disponibles abajo.</p>
                </div>
            `;
        }
        return suggestions
            .map(
                (item, index) => `
                    <button class="agronomy-suggestion" type="button" data-suggestion="${index}">
                        <span class="agronomy-suggestion-number">0${index + 1}</span>
                        <div>
                            <strong>${escapeHtml(item.name)}</strong>
                            <p>${escapeHtml(item.agronomic_goal)}</p>
                            <small>${item.variable_keys.length} variables relacionadas</small>
                        </div>
                        <i>→</i>
                    </button>
                `,
            )
            .join("");
    };

    const renderMetrics = (metrics) =>
        metrics
            .map(
                (metric) => `
                    <label class="agronomy-variable-chip">
                        <input type="checkbox" name="agronomy_variable" value="${escapeHtml(metric.key)}">
                        <span>
                            <strong>${escapeHtml(metric.name)}</strong>
                            <small>${escapeHtml(metricLabel(metric).replace(`${metric.name}`, "").replace(/^ · /, "")) || "Variable Aranet"}</small>
                        </span>
                        <i></i>
                    </label>
                `,
            )
            .join("");

    const renderRelationships = (relationships, canEdit) => {
        if (!relationships.length) {
            return `
                <div class="agronomy-empty-list">
                    <span>+</span>
                    <strong>Aún no hay relaciones guardadas.</strong>
                    <p>Usa una recomendación o crea la primera relación manualmente.</p>
                </div>
            `;
        }
        return relationships
            .map(
                (item) => `
                    <article class="agronomy-saved-card">
                        <div class="agronomy-saved-top">
                            <div>
                                <span>${escapeHtml(item.relationship_type_label)}</span>
                                <strong>${escapeHtml(item.name)}</strong>
                            </div>
                            <span class="agronomy-state ${item.is_enabled ? "on" : "off"}">${item.is_enabled ? "ACTIVA" : "PAUSADA"}</span>
                        </div>
                        <div class="agronomy-variable-list">
                            ${item.variable_names.map((name) => `<span>${escapeHtml(name)}</span>`).join("")}
                        </div>
                        ${item.agronomic_goal ? `<p>${escapeHtml(item.agronomic_goal)}</p>` : ""}
                        ${
                            canEdit
                                ? `<button type="button" class="agronomy-delete" data-relationship-id="${item.id}">Eliminar relación</button>`
                                : ""
                        }
                    </article>
                `,
            )
            .join("");
    };

    const renderBody = (payload) => {
        const body = document.getElementById("agronomy-body");
        if (!body) return;
        document.getElementById("agronomy-profile-name").textContent = payload.crop_name || "Cultivo";
        document.getElementById("agronomy-sensor-name").textContent = payload.sensor_name || payload.sensor_id;

        body.innerHTML = `
            <section class="agronomy-reference">
                <div class="agronomy-reference-copy">
                    <span>CASO BASE · ALSTROEMERIA</span>
                    <h3>Qué conviene relacionar</h3>
                    <p>La lectura agronómica gana valor cuando combinamos clima, zona radicular y ambiente fotosintético. Los valores objetivo deben ajustarse por cultivar, sustrato, etapa y manejo local.</p>
                </div>
                <div class="agronomy-reference-points">
                    <div><b>01</b><span><strong>Temperatura + humedad</strong><small>Estrés climático y demanda evaporativa.</small></span></div>
                    <div><b>02</b><span><strong>Humedad + EC + pH + T° raíz</strong><small>Riego, sales y disponibilidad nutricional.</small></span></div>
                    <div><b>03</b><span><strong>CO₂ + luz/PAR + temperatura</strong><small>Ambiente fotosintético y floración.</small></span></div>
                </div>
            </section>

            <div class="agronomy-grid">
                <section class="agronomy-editor">
                    <div class="agronomy-section-title">
                        <span>Recomendaciones</span>
                        <h3>Relaciones sugeridas con tus variables reales</h3>
                        <p>Solo aparecen combinaciones que pueden construirse con las métricas que este sensor reporta.</p>
                    </div>
                    <div class="agronomy-suggestions" id="agronomy-suggestions">
                        ${renderSuggestions(payload.suggestions || [])}
                    </div>

                    <form id="agronomy-form" class="agronomy-form" ${payload.can_edit ? "" : "data-readonly='1'"}>
                        <div class="agronomy-section-title compact">
                            <span>Configurador</span>
                            <h3>Crea una relación multivariable</h3>
                        </div>
                        <div class="agronomy-form-grid">
                            <label>
                                <span>Cultivo</span>
                                <input name="crop_name" maxlength="160" value="${escapeHtml(payload.crop_name || "Astromelia")}" ${payload.can_edit ? "" : "disabled"}>
                            </label>
                            <label>
                                <span>Tipo de relación</span>
                                <select name="relationship_type" ${payload.can_edit ? "" : "disabled"}>
                                    ${(payload.relationship_types || [])
                                        .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`)
                                        .join("")}
                                </select>
                            </label>
                            <label class="full">
                                <span>Nombre</span>
                                <input name="name" maxlength="200" placeholder="Ej. Balance climático de floración" ${payload.can_edit ? "" : "disabled"}>
                            </label>
                        </div>

                        <div class="agronomy-variable-picker">
                            <div>
                                <strong>Variables relacionadas</strong>
                                <small>Selecciona mínimo dos. Puedes combinar todas las que tengan sentido agronómico.</small>
                            </div>
                            <div class="agronomy-variable-grid">
                                ${renderMetrics(payload.metrics || [])}
                            </div>
                        </div>

                        <div class="agronomy-form-grid">
                            <label class="full">
                                <span>Objetivo agronómico</span>
                                <input name="agronomic_goal" maxlength="500" placeholder="¿Qué queremos entender o anticipar?" ${payload.can_edit ? "" : "disabled"}>
                            </label>
                            <label class="full">
                                <span>Interpretación / instrucción experta</span>
                                <textarea name="expert_guidance" rows="4" maxlength="2500" placeholder="Ej. Evaluar temperatura junto con humedad antes de recomendar ventilación…" ${payload.can_edit ? "" : "disabled"}></textarea>
                            </label>
                        </div>

                        <div id="agronomy-form-message" class="agronomy-form-message" hidden></div>
                        ${
                            payload.can_edit
                                ? `<footer class="agronomy-actions"><label><input type="checkbox" name="is_enabled" checked> Relación activa</label><button type="submit">Guardar relación</button></footer>`
                                : `<div class="agronomy-readonly">Tu nivel de acceso permite consultar relaciones, pero no modificarlas.</div>`
                        }
                    </form>
                </section>

                <aside class="agronomy-saved">
                    <div class="agronomy-section-title">
                        <span>Modelo operativo</span>
                        <h3>Relaciones guardadas</h3>
                        <p>Estas relaciones quedan en OSIRIS y podrán alimentar análisis, recomendaciones y automatización.</p>
                    </div>
                    <div id="agronomy-saved-list" class="agronomy-saved-list">
                        ${renderRelationships(payload.relationships || [], payload.can_edit)}
                    </div>
                </aside>
            </div>
        `;

        installInteractions(payload);
    };

    const showMessage = (message, error = false) => {
        const node = document.getElementById("agronomy-form-message");
        if (!node) return;
        node.textContent = message;
        node.classList.toggle("error", error);
        node.hidden = false;
    };

    const applySuggestion = (payload, index) => {
        const suggestion = payload.suggestions?.[index];
        const form = document.getElementById("agronomy-form");
        if (!suggestion || !form || form.dataset.readonly === "1") return;

        form.elements.name.value = suggestion.name || "";
        form.elements.relationship_type.value = suggestion.relationship_type || "custom";
        form.elements.agronomic_goal.value = suggestion.agronomic_goal || "";
        form.elements.expert_guidance.value = suggestion.expert_guidance || "";
        const wanted = new Set(suggestion.variable_keys || []);
        form.querySelectorAll('input[name="agronomy_variable"]').forEach((input) => {
            input.checked = wanted.has(input.value);
        });
        form.scrollIntoView({ behavior: "smooth", block: "center" });
    };

    const loadPayload = async () => {
        const sensor = selectedSensorId();
        if (!sensor) return;
        const response = await fetch(`${endpoint}?sensor=${encodeURIComponent(sensor)}`, {
            headers: { Accept: "application/json" },
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "No fue posible cargar agronomía.");
        renderBody(payload);
    };

    const deleteRelationship = async (relationshipId) => {
        const data = new FormData();
        data.append("sensor", selectedSensorId());
        data.append("action", "delete");
        data.append("relationship_id", relationshipId);
        data.append("csrfmiddlewaretoken", csrfToken());
        const response = await fetch(endpoint, { method: "POST", body: data });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "No fue posible eliminar la relación.");
        await loadPayload();
    };

    const installInteractions = (payload) => {
        document.querySelectorAll("[data-suggestion]").forEach((button) => {
            button.addEventListener("click", () => applySuggestion(payload, Number(button.dataset.suggestion)));
        });

        document.querySelectorAll(".agronomy-delete").forEach((button) => {
            button.addEventListener("click", async () => {
                button.disabled = true;
                try {
                    await deleteRelationship(button.dataset.relationshipId);
                } catch (error) {
                    button.disabled = false;
                    showMessage(error.message, true);
                }
            });
        });

        const form = document.getElementById("agronomy-form");
        if (!form || form.dataset.readonly === "1") return;
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const selectedVariables = [...form.querySelectorAll('input[name="agronomy_variable"]:checked')].map(
                (input) => input.value,
            );
            if (selectedVariables.length < 2) {
                showMessage("Selecciona al menos dos variables para construir una relación.", true);
                return;
            }

            const data = new FormData(form);
            data.append("sensor", selectedSensorId());
            data.append("variable_ids", JSON.stringify(selectedVariables));
            data.append("is_enabled", form.elements.is_enabled.checked ? "1" : "0");
            data.append("csrfmiddlewaretoken", csrfToken());

            const button = form.querySelector('button[type="submit"]');
            button.disabled = true;
            try {
                const response = await fetch(endpoint, { method: "POST", body: data });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || "No fue posible guardar la relación.");
                await loadPayload();
                showMessage("Relación agronómica guardada correctamente.");
            } catch (error) {
                button.disabled = false;
                showMessage(error.message, true);
            }
        });
    };

    const start = () => {
        if (!document.getElementById("dashboard-filters") || !inventoryAnchor()) return;
        compactInventory();
        createPanel();
        loadPayload().catch((error) => {
            const body = document.getElementById("agronomy-body");
            if (body) body.innerHTML = `<div class="agronomy-error">${escapeHtml(error.message)}</div>`;
        });
    };

    document.addEventListener("DOMContentLoaded", start);
})();
