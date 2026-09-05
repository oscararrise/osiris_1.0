(() => {
    const currentScript = document.currentScript;
    const staticBase = currentScript ? new URL("./", currentScript.src) : null;

    const ensureStylesheet = (href, id) => {
        if (document.getElementById(id)) return;
        const link = document.createElement("link");
        link.id = id;
        link.rel = "stylesheet";
        link.href = href;
        document.head.appendChild(link);
    };

    if (staticBase) {
        ensureStylesheet(new URL("vladimir_context.css?v=20260905-1", staticBase).href, "osiris-context-css");
    }
    ensureStylesheet(
        "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
        "osiris-leaflet-css",
    );

    const text = (value, fallback = "—") => {
        const normalized = String(value ?? "").trim();
        return normalized || fallback;
    };

    const coordinateLabel = (item) => {
        if (!item?.has_coordinates) return "Pendientes";
        return `${Number(item.latitude).toFixed(6)}, ${Number(item.longitude).toFixed(6)}`;
    };

    const productiveLabel = (item) => {
        const activity = text(item?.activity_label, "Sin actividad");
        const product = String(item?.product_name || "").trim();
        return product ? `${activity} · ${product}` : activity;
    };

    const loadLeaflet = () => {
        if (window.L) return Promise.resolve(window.L);
        return new Promise((resolve, reject) => {
            const existing = document.getElementById("osiris-leaflet-js");
            if (existing) {
                existing.addEventListener("load", () => resolve(window.L), { once: true });
                existing.addEventListener("error", reject, { once: true });
                return;
            }
            const script = document.createElement("script");
            script.id = "osiris-leaflet-js";
            script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
            script.async = true;
            script.addEventListener("load", () => resolve(window.L), { once: true });
            script.addEventListener("error", reject, { once: true });
            document.head.appendChild(script);
        });
    };

    const buildShell = () => {
        const section = document.createElement("section");
        section.className = "osiris-context-shell";
        section.id = "osiris-operational-context";
        section.innerHTML = `
            <article class="osiris-context-card">
                <header class="osiris-context-head">
                    <div>
                        <div class="osiris-context-kicker"><i></i> Contexto OSIRIS</div>
                        <h2>Configuración del sensor</h2>
                        <p>Datos operativos agregados por tu equipo sobre la telemetría de Aranet.</p>
                    </div>
                    <span class="osiris-context-badge">Metadata local</span>
                </header>
                <div data-context-content></div>
            </article>
            <article class="osiris-map-card">
                <header class="osiris-map-head">
                    <div>
                        <div class="osiris-context-kicker"><i></i> Geolocalización</div>
                        <h2>Mapa operativo de sensores</h2>
                        <p>Solo muestra dispositivos visibles en el dashboard que tengan coordenadas configuradas.</p>
                    </div>
                    <span class="osiris-map-count" data-map-count>0 ubicados</span>
                </header>
                <div class="osiris-map-layout">
                    <div class="osiris-sensor-map" id="osiris-sensor-map"></div>
                    <aside class="osiris-map-sidebar" data-map-sidebar>
                        <div class="osiris-map-sidebar-title"><span>Sensores ubicados</span><span data-unmapped-count></span></div>
                    </aside>
                </div>
            </article>
        `;
        return section;
    };

    const renderContext = (shell, data) => {
        const target = shell.querySelector("[data-context-content]");
        const item = data.selected;
        if (!item) {
            target.innerHTML = `
                <div class="osiris-context-empty">
                    No encontramos configuración local para el sensor seleccionado. Sincroniza el inventario o configura el sensor desde el módulo de administración de sensores.
                </div>
            `;
            return;
        }

        target.innerHTML = `
            <div class="osiris-context-identity">
                <div class="osiris-context-avatar" data-context-avatar></div>
                <div>
                    <strong data-context-name></strong>
                    <small data-context-detail></small>
                </div>
            </div>
            <div class="osiris-context-grid">
                <div class="osiris-context-field"><span>Actividad</span><strong data-context-activity></strong><small data-context-product></small></div>
                <div class="osiris-context-field"><span>Finca / Invernadero</span><strong data-context-facility></strong><small data-context-zone></small></div>
                <div class="osiris-context-field"><span>Ciudad / Departamento</span><strong data-context-city></strong><small data-context-department></small></div>
                <div class="osiris-context-field"><span>Coordenadas</span><strong data-context-coordinates></strong><small data-context-altitude></small></div>
            </div>
            <div class="osiris-context-actions">
                <span>Este contexto pertenece a OSIRIS y no modifica la base de Aranet.</span>
                <a class="osiris-context-edit" data-context-edit hidden>Editar configuración →</a>
            </div>
        `;

        target.querySelector("[data-context-avatar]").textContent = text(item.sensor_name, "S").slice(0, 1).toUpperCase();
        target.querySelector("[data-context-name]").textContent = text(item.sensor_name);
        target.querySelector("[data-context-detail]").textContent = text(item.sensor_detail, item.sensor_id);
        target.querySelector("[data-context-activity]").textContent = text(item.activity_label, "Sin definir");
        target.querySelector("[data-context-product]").textContent = item.product_name ? `Producto / especie: ${item.product_name}` : "Producto / especie sin definir";
        target.querySelector("[data-context-facility]").textContent = text(item.facility_name, "Sin definir");
        target.querySelector("[data-context-zone]").textContent = item.zone_path ? `Zona: ${item.zone_path}` : "Zona sin definir";
        target.querySelector("[data-context-city]").textContent = text(item.city, "Sin definir");
        target.querySelector("[data-context-department]").textContent = text(item.department, "Departamento sin definir");
        target.querySelector("[data-context-coordinates]").textContent = coordinateLabel(item);
        target.querySelector("[data-context-altitude]").textContent = item.altitude_m == null ? "Altura sin definir" : `Altura: ${Number(item.altitude_m).toFixed(0)} m`;

        const edit = target.querySelector("[data-context-edit]");
        if (item.configure_url) {
            edit.href = item.configure_url;
            edit.hidden = false;
        }
    };

    const buildPopup = (point, filters) => {
        const wrapper = document.createElement("div");
        wrapper.className = "osiris-map-popup";
        const name = document.createElement("strong");
        name.textContent = text(point.sensor_name);
        wrapper.appendChild(name);

        const productive = document.createElement("span");
        productive.textContent = productiveLabel(point);
        wrapper.appendChild(productive);

        const location = document.createElement("small");
        location.textContent = text(point.location_label || point.city, "Ubicación configurada");
        wrapper.appendChild(location);

        const button = document.createElement("button");
        button.type = "button";
        button.textContent = point.is_selected ? "Sensor seleccionado" : "Ver este sensor";
        button.disabled = Boolean(point.is_selected);
        button.addEventListener("click", () => {
            const sensorSelect = document.getElementById("sensor-select");
            if (!sensorSelect || !filters) return;
            sensorSelect.value = String(point.sensor_id);
            filters.submit();
        });
        wrapper.appendChild(button);
        return wrapper;
    };

    const renderSidebar = (shell, data, markersBySensor, map) => {
        const sidebar = shell.querySelector("[data-map-sidebar]");
        const title = sidebar.querySelector(".osiris-map-sidebar-title");
        sidebar.replaceChildren(title);
        title.querySelector("[data-unmapped-count]").textContent = data.unmapped_count ? `${data.unmapped_count} sin coordenadas` : "";

        data.map_points.forEach((point) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = `osiris-map-sensor${point.is_selected ? " selected" : ""}`;
            const name = document.createElement("strong");
            name.textContent = text(point.sensor_name);
            const detail = document.createElement("span");
            detail.textContent = `${productiveLabel(point)} · ${text(point.location_label || point.city, "Ubicación")}`;
            button.append(name, detail);
            button.addEventListener("click", () => {
                const marker = markersBySensor.get(String(point.sensor_id));
                if (!marker) return;
                map.setView(marker.getLatLng(), Math.max(map.getZoom(), 15), { animate: true });
                marker.openPopup();
            });
            sidebar.appendChild(button);
        });
    };

    const renderMapUnavailable = (shell, message) => {
        const mapNode = shell.querySelector("#osiris-sensor-map");
        mapNode.innerHTML = "";
        const empty = document.createElement("div");
        empty.className = "osiris-map-empty";
        const title = document.createElement("strong");
        title.textContent = "Mapa no disponible";
        const copy = document.createElement("p");
        copy.textContent = message;
        empty.append(title, copy);
        mapNode.appendChild(empty);
    };

    const renderMap = async (shell, data, filters) => {
        shell.querySelector("[data-map-count]").textContent = `${data.mapped_count} ubicados`;
        const mapNode = shell.querySelector("#osiris-sensor-map");
        if (!data.map_points.length) {
            mapNode.innerHTML = `
                <div class="osiris-map-empty">
                    <strong>Aún no hay sensores con coordenadas</strong>
                    <p>Agrega latitud y longitud desde Configuración de sensores para empezar a construir el mapa operativo.</p>
                </div>
            `;
            return;
        }

        try {
            const L = await loadLeaflet();
            if (!L) throw new Error("Leaflet unavailable");
            const map = L.map(mapNode, {
                scrollWheelZoom: false,
                zoomControl: true,
            });
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: "&copy; OpenStreetMap contributors",
                maxZoom: 19,
            }).addTo(map);

            const markersBySensor = new Map();
            const bounds = [];
            data.map_points.forEach((point) => {
                const lat = Number(point.latitude);
                const lng = Number(point.longitude);
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
                const icon = L.divIcon({
                    className: "osiris-map-marker-wrapper",
                    html: `<span class="osiris-map-marker${point.is_selected ? " selected" : ""}"></span>`,
                    iconSize: point.is_selected ? [27, 27] : [22, 22],
                    iconAnchor: point.is_selected ? [13, 26] : [11, 21],
                    popupAnchor: [0, -22],
                });
                const marker = L.marker([lat, lng], { icon }).addTo(map);
                marker.bindPopup(buildPopup(point, filters));
                markersBySensor.set(String(point.sensor_id), marker);
                bounds.push([lat, lng]);
                if (point.is_selected) marker.openPopup();
            });

            if (bounds.length === 1) {
                map.setView(bounds[0], 15);
            } else if (bounds.length > 1) {
                map.fitBounds(bounds, { padding: [36, 36], maxZoom: 16 });
            }
            renderSidebar(shell, data, markersBySensor, map);
            window.setTimeout(() => map.invalidateSize(), 80);
        } catch (_error) {
            renderMapUnavailable(
                shell,
                "Las coordenadas siguen disponibles en OSIRIS, pero la capa cartográfica externa no pudo cargarse en esta red.",
            );
        }
    };

    const fetchContext = async (sensorId) => {
        const endpoint = new URL(`${window.location.pathname.replace(/\/$/, "")}/context`, window.location.origin);
        endpoint.searchParams.set("sensor", sensorId || "");
        const response = await fetch(endpoint, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        });
        if (!response.ok) throw new Error(`Context request failed: ${response.status}`);
        return response.json();
    };

    const install = async () => {
        const filters = document.getElementById("dashboard-filters");
        const sensorSelect = document.getElementById("sensor-select");
        if (!filters || !sensorSelect || document.getElementById("osiris-operational-context")) return;

        const shell = buildShell();
        filters.insertAdjacentElement("afterend", shell);
        try {
            const data = await fetchContext(sensorSelect.value);
            renderContext(shell, data);
            await renderMap(shell, data, filters);
        } catch (_error) {
            const target = shell.querySelector("[data-context-content]");
            target.innerHTML = '<div class="osiris-context-empty">No fue posible cargar el contexto local de OSIRIS en este momento.</div>';
            renderMapUnavailable(shell, "No fue posible consultar la información geográfica local.");
        }
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", install, { once: true });
    } else {
        install();
    }
})();
