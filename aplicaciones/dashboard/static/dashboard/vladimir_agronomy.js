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
                    <h2>Relaciones multivariable y multi-sensor</h2>
                    <p>Combina señales de distintos sensores para interpretar clima, suelo, fertirriego y cultivo como un solo sistema.</p>
                </div>
                <div class="agronomy-head-badge">
                    <span>Perfil activo</span>
                    <strong id="agronomy-profile-name">—</strong>
                    <small id="agronomy-sensor-name">Cargando sensor principal…</small>
                </div>
            </header>
            <div id="agronomy-body" class="agronomy-body">
                <div class="agronomy-loading"><span></span> Cargando sensores y variables…</div>
            </div>
        `;
        anchor.insertAdjacentElement("afterend", panel);
        return panel;
    };

    const metricMeta = (metric) => {
        const probe = Number(metric.probe_no || 0) ? `Sonda ${metric.probe_no}` : "";
        const unit = metric.unit || "";
        return [probe, unit].filter(Boolean).join(" · ") || "Variable Aranet";
    };

    const coordinates = (sensor) => {
        if (sensor.latitude == null || sensor.longitude == null) return "Sin coordenadas";
        return `${Number(sensor.latitude).toFixed(5)}, ${Number(sensor.longitude).toFixed(5)}`;
    };

    const locationSummary = (sensor) =>
        sensor.zone_path ||
        [sensor.city, sensor.department].filter(Boolean).join(" · ") ||
        "Sin ubicación configurada";

    const renderSuggestions = (suggestions) => {
        if (!suggestions.length) {
            return `
                <div class="agronomy-suggestion-empty">
                    <strong>No hay una combinación automática completa todavía.</strong>
                    <p>Puedes crear una relación personalizada combinando variables de cualquier sensor.</p>
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
                            <small>${item.variable_keys.length} variables · pueden provenir de sensores distintos</small>
                        </div>
                        <i>→</i>
                    </button>
                `,
            )
            .join("");
    };

    const renderSensorMetrics = (sensor, canEdit) => {
        if (sensor.metrics_error) {
            return `<div class="agronomy-sensor-error">${escapeHtml(sensor.metrics_error)}</div>`;
        }
        if (!sensor.metrics?.length) {
            return `<div class="agronomy-sensor-empty">Este sensor no expone variables disponibles.</div>`;
        }
        return sensor.metrics
            .map(
                (metric) => `
                    <label class="agronomy-variable-chip multisensor-variable">
                        <input
                            type="checkbox"
                            name="agronomy_variable"
                            value="${escapeHtml(metric.key)}"
                            ${canEdit ? "" : "disabled"}
                        >
                        <span>
                            <strong>${escapeHtml(metric.name)}</strong>
                            <small>${escapeHtml(metricMeta(metric))}</small>
                        </span>
                        <i></i>
                    </label>
                `,
            )
            .join("");
    };

    const renderSensorCatalog = (catalog, selectedSensor, canEdit) => {
        if (!catalog.length) {
            return `<div class="agronomy-sensor-empty">No hay sensores activos disponibles.</div>`;
        }
        return catalog
            .map((sensor) => {
                const isPrimary = sensor.sensor_id === selectedSensor;
                const search = [
                    sensor.sensor_name,
                    sensor.sensor_id,
                    sensor.sensor_detail,
                    sensor.productive_context,
                    sensor.facility_name,
                    sensor.zone_path,
                    sensor.city,
                    sensor.department,
                    ...(sensor.metrics || []).map((metric) => metric.name),
                ]
                    .filter(Boolean)
                    .join(" ");
                return `
                    <details
                        class="agronomy-sensor-card"
                        data-sensor-search="${escapeHtml(search)}"
                        ${isPrimary ? "open" : ""}
                    >
                        <summary>
                            <div class="agronomy-sensor-identity">
                                <span class="agronomy-sensor-icon">S</span>
                                <div>
                                    <strong>${escapeHtml(sensor.sensor_name)}</strong>
                                    <small>ID ${escapeHtml(sensor.sensor_id)} · ${escapeHtml(locationSummary(sensor))}</small>
                                </div>
                            </div>
                            <div class="agronomy-sensor-summary-meta">
                                ${isPrimary ? '<span class="primary">PRINCIPAL</span>' : ""}
                                <span class="${sensor.dashboard_enabled ? "visible" : "hidden"}">
                                    ${escapeHtml(sensor.dashboard_label)}
                                </span>
                                <b>${Number(sensor.metric_count || 0)} vars.</b>
                            </div>
                        </summary>
                        <div class="agronomy-sensor-content">
                            <div class="agronomy-sensor-config-grid">
                                <div><span>Actividad</span><strong>${escapeHtml(sensor.activity_label || "Sin definir")}</strong></div>
                                <div><span>Producto / especie</span><strong>${escapeHtml(sensor.product_name || "Sin definir")}</strong></div>
                                <div><span>Finca / invernadero</span><strong>${escapeHtml(sensor.facility_name || "Sin definir")}</strong></div>
                                <div><span>Zona</span><strong>${escapeHtml(sensor.zone_path || "Sin definir")}</strong></div>
                                <div><span>Ciudad / departamento</span><strong>${escapeHtml([sensor.city, sensor.department].filter(Boolean).join(" · ") || "Sin definir")}</strong></div>
                                <div><span>Coordenadas</span><strong>${escapeHtml(coordinates(sensor))}</strong></div>
                                <div><span>Altitud</span><strong>${sensor.altitude_m == null ? "Sin definir" : `${escapeHtml(sensor.altitude_m)} m`}</strong></div>
                                <div><span>Detalle</span><strong>${escapeHtml(sensor.sensor_detail || "Sin detalle")}</strong></div>
                            </div>
                            <div class="agronomy-sensor-variable-head">
                                <strong>Variables de este sensor</strong>
                                <small>Selecciona una o varias para agregarlas a la relación.</small>
                            </div>
                            <div class="agronomy-variable-grid multisensor-grid">
                                ${renderSensorMetrics(sensor, canEdit)}
                            </div>
                        </div>
                    </details>
                `;
            })
            .join("");
    };

    const renderRelationships = (relationships, canEdit) => {
        if (!relationships.length) {
            return `
                <div class="agronomy-empty-list">
                    <span>+</span>
                    <strong>Aún no hay relaciones guardadas.</strong>
                    <p>Crea una relación usando variables de uno o varios sensores.</p>
                </div>
            `;
        }
        return relationships
            .map((item) => {
                const variables = (item.variable_details || []).length
                    ? item.variable_details
                          .map(
                              (variable) => `
                                  <span class="agronomy-saved-variable ${variable.available ? "" : "unavailable"}">
                                      <b>${escapeHtml(variable.sensor_name)}</b>
                                      ${escapeHtml(variable.name)}
                                  </span>
                              `,
                          )
                          .join("")
                    : (item.variable_names || [])
                          .map((name) => `<span>${escapeHtml(name)}</span>`)
                          .join("");
                return `
                    <article class="agronomy-saved-card">
                        <div class="agronomy-saved-top">
                            <div>
                                <span>${escapeHtml(item.relationship_type_label)}</span>
                                <strong>${escapeHtml(item.name)}</strong>
                            </div>
                            <span class="agronomy-state ${item.is_enabled ? "on" : "off"}">
                                ${item.is_enabled ? "ACTIVA" : "PAUSADA"}
                            </span>
                        </div>
                        <div class="agronomy-variable-list">${variables}</div>
                        ${item.agronomic_goal ? `<p>${escapeHtml(item.agronomic_goal)}</p>` : ""}
                        ${
                            canEdit
                                ? `<button type="button" class="agronomy-delete" data-relationship-id="${item.id}">Eliminar relación</button>`
                                : ""
                        }
                    </article>
                `;
            })
            .join("");
    };

    const renderBody = (payload) => {
        const body = document.getElementById("agronomy-body");
        if (!body) return;
        document.getElementById("agronomy-profile-name").textContent =
            payload.crop_name || "Cultivo";
        document.getElementById("agronomy-sensor-name").textContent =
            `Principal: ${payload.sensor_name || payload.sensor_id}`;

        body.innerHTML = `
            <section class="agronomy-reference">
                <div class="agronomy-reference-copy">
                    <span>MODELO MULTI-SENSOR</span>
                    <h3>Relaciona el cultivo completo</h3>
                    <p>Una relación puede combinar temperatura ambiental de un sensor, humedad o EC de otro y CO₂ o radiación de un tercero. OSIRIS conserva el origen de cada variable.</p>
                </div>
                <div class="agronomy-reference-points">
                    <div><b>01</b><span><strong>Clima</strong><small>Temperatura + humedad de ambiente.</small></span></div>
                    <div><b>02</b><span><strong>Raíz / fertirriego</strong><small>Humedad + EC + pH + T° de suelo.</small></span></div>
                    <div><b>03</b><span><strong>Fotosíntesis</strong><small>CO₂ + luz/PAR + temperatura.</small></span></div>
                </div>
            </section>

            <div class="agronomy-grid">
                <section class="agronomy-editor">
                    <div class="agronomy-section-title">
                        <span>Recomendaciones</span>
                        <h3>Relaciones sugeridas con toda la red de sensores</h3>
                        <p>Las sugerencias ahora pueden tomar variables de sensores diferentes.</p>
                    </div>
                    <div class="agronomy-suggestions" id="agronomy-suggestions">
                        ${renderSuggestions(payload.suggestions || [])}
                    </div>

                    <form id="agronomy-form" class="agronomy-form" ${payload.can_edit ? "" : "data-readonly='1'"}>
                        <div class="agronomy-section-title compact">
                            <span>Configurador</span>
                            <h3>Crea una relación multi-sensor</h3>
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
                                <input name="name" maxlength="200" placeholder="Ej. Balance clima-raíz sector norte" ${payload.can_edit ? "" : "disabled"}>
                            </label>
                        </div>

                        <div class="agronomy-variable-picker multisensor-picker">
                            <div class="agronomy-picker-head">
                                <div>
                                    <strong>Variables relacionadas</strong>
                                    <small>Selecciona mínimo dos variables. Pueden pertenecer a sensores diferentes.</small>
                                </div>
                                <input id="agronomy-sensor-search" type="search" placeholder="Buscar sensor, zona, producto o variable…">
                            </div>
                            <div id="agronomy-sensor-catalog" class="agronomy-sensor-catalog">
                                ${renderSensorCatalog(payload.sensor_catalog || [], payload.sensor_id, payload.can_edit)}
                            </div>
                        </div>

                        <div class="agronomy-selection-summary">
                            <span>Variables seleccionadas</span>
                            <strong id="agronomy-selected-count">0</strong>
                            <small id="agronomy-selected-sensors">0 sensores involucrados</small>
                        </div>

                        <div class="agronomy-form-grid">
                            <label class="full">
                                <span>Objetivo agronómico</span>
                                <input name="agronomic_goal" maxlength="500" placeholder="¿Qué queremos entender o anticipar?" ${payload.can_edit ? "" : "disabled"}>
                            </label>
                            <label class="full">
                                <span>Interpretación / instrucción experta</span>
                                <textarea name="expert_guidance" rows="4" maxlength="2500" placeholder="Ej. Evaluar clima, humedad del sustrato y EC antes de recomendar una acción…" ${payload.can_edit ? "" : "disabled"}></textarea>
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
                        <p>Cada etiqueta conserva el sensor de origen de la variable.</p>
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

    const updateSelectionSummary = () => {
        const checked = [
            ...document.querySelectorAll('input[name="agronomy_variable"]:checked'),
        ];
        const sensors = new Set(
            checked.map((input) => String(input.value).split("::", 1)[0]),
        );
        const count = document.getElementById("agronomy-selected-count");
        const sensorCount = document.getElementById("agronomy-selected-sensors");
        if (count) count.textContent = String(checked.length);
        if (sensorCount) {
            sensorCount.textContent = `${sensors.size} sensor${sensors.size === 1 ? "" : "es"} involucrado${sensors.size === 1 ? "" : "s"}`;
        }
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
            if (input.checked) input.closest("details")?.setAttribute("open", "");
        });
        updateSelectionSummary();
        form.scrollIntoView({ behavior: "smooth", block: "center" });
    };

    const installSensorSearch = () => {
        const search = document.getElementById("agronomy-sensor-search");
        const cards = [...document.querySelectorAll(".agronomy-sensor-card")];
        if (!search || !cards.length) return;
        search.addEventListener("input", () => {
            const query = search.value.trim().toLocaleLowerCase("es");
            cards.forEach((card) => {
                const haystack = String(card.dataset.sensorSearch || "").toLocaleLowerCase("es");
                card.hidden = Boolean(query) && !haystack.includes(query);
                if (query && !card.hidden) card.open = true;
            });
        });
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
            button.addEventListener("click", () =>
                applySuggestion(payload, Number(button.dataset.suggestion)),
            );
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

        document.querySelectorAll('input[name="agronomy_variable"]').forEach((input) => {
            input.addEventListener("change", updateSelectionSummary);
        });
        installSensorSearch();
        updateSelectionSummary();

        const form = document.getElementById("agronomy-form");
        if (!form || form.dataset.readonly === "1") return;
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const selectedVariables = [
                ...form.querySelectorAll('input[name="agronomy_variable"]:checked'),
            ].map((input) => input.value);
            if (selectedVariables.length < 2) {
                showMessage(
                    "Selecciona al menos dos variables. Pueden ser de sensores distintos.",
                    true,
                );
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
                if (!response.ok) {
                    throw new Error(result.error || "No fue posible guardar la relación.");
                }
                await loadPayload();
                showMessage("Relación multi-sensor guardada correctamente.");
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
            if (body) {
                body.innerHTML = `<div class="agronomy-error">${escapeHtml(error.message)}</div>`;
            }
        });
    };

    document.addEventListener("DOMContentLoaded", start);
})();
