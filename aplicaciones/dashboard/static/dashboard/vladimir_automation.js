(() => {
    const modal = () => document.getElementById("automation-modal");

    const openModal = () => {
        const node = modal();
        if (!node) return;
        node.classList.add("open");
        node.setAttribute("aria-hidden", "false");
        document.body.classList.add("automation-modal-open");
    };

    const closeModal = () => {
        const node = modal();
        if (!node) return;
        node.classList.remove("open");
        node.setAttribute("aria-hidden", "true");
        document.body.classList.remove("automation-modal-open");
    };

    const installModal = () => {
        document.querySelectorAll("[data-open-automation]").forEach((button) => {
            button.addEventListener("click", openModal);
        });
        document.querySelectorAll("[data-close-automation]").forEach((button) => {
            button.addEventListener("click", closeModal);
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeModal();
        });

        if (modal()?.classList.contains("open")) {
            document.body.classList.add("automation-modal-open");
        }
    };

    const installSensorEntry = () => {
        const form = document.getElementById("dashboard-filters");
        const sensor = document.getElementById("sensor-select");
        if (!form || !sensor) return;

        sensor.addEventListener("change", () => {
            let configure = form.querySelector('input[name="configure"]');
            if (!configure) {
                configure = document.createElement("input");
                configure.type = "hidden";
                configure.name = "configure";
                form.appendChild(configure);
            }
            configure.value = "1";
            form.submit();
        });
    };

    const installChannelState = () => {
        const pairs = [
            ["email-enabled", "email-recipients"],
            ["whatsapp-enabled", "whatsapp-recipients"],
        ];
        pairs.forEach(([checkboxId, inputId]) => {
            const checkbox = document.getElementById(checkboxId);
            const input = document.getElementById(inputId);
            if (!checkbox || !input) return;

            const sync = () => {
                input.disabled = !checkbox.checked;
                input.style.opacity = checkbox.checked ? "1" : ".55";
            };
            checkbox.addEventListener("change", sync);
            sync();
        });
    };

    document.addEventListener("DOMContentLoaded", () => {
        installModal();
        installSensorEntry();
        installChannelState();
    });
})();
