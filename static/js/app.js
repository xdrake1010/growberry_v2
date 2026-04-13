const app = {
    init() {
        this.cacheDOM();
        this.bindEvents();
        this.initMobileMenu();
        this.startClock();
        this.fetchStats();
        this.initCharts();
        
        // Refresh stats and charts every 30 seconds (matches sensor cache)
        setInterval(() => {
            this.fetchStats();
            this.updateCharts();
            if(document.getElementById('timelapse').classList.contains('active')) {
                this.fetchCameraStatus();
            }
        }, 30000);
    },

    initMobileMenu() {
        const toggle = document.getElementById('mobile-toggle');
        const sidebar = document.querySelector('.sidebar');
        if (toggle && sidebar) {
            toggle.addEventListener('click', () => {
                sidebar.classList.toggle('open');
                const icon = toggle.querySelector('i');
                if (sidebar.classList.contains('open')) {
                    icon.classList.replace('fa-bars', 'fa-xmark');
                } else {
                    icon.classList.replace('fa-xmark', 'fa-bars');
                }
            });
            
            // Close menu when a link is clicked
            document.querySelectorAll('.nav-links li').forEach(li => {
                li.addEventListener('click', () => {
                    sidebar.classList.remove('open');
                    toggle.querySelector('i').classList.replace('fa-xmark', 'fa-bars');
                });
            });
        }
    },

    cacheDOM() {
        this.tabs = document.querySelectorAll('.nav-links li');
        this.contents = document.querySelectorAll('.tab-content');
        this.timeEl = document.getElementById('current-time');
        this.toastEl = document.getElementById('toast');
        this.configEditor = document.getElementById('config-editor');
        this.advancedModeContainer = document.getElementById('advanced-config');
        this.cyclesList = document.getElementById('cycles-list');
        this.harvestSelector = document.getElementById('cfg-load-selector');
    },

    bindEvents() {
        this.tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const target = tab.dataset.tab;
                
                this.tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                this.contents.forEach(c => c.classList.remove('active'));
                document.getElementById(target).classList.add('active');

                // Load config JSON if entering settings
                if(target === 'settings') {
                    this.loadConfigToForm();
                }
                
                if(target === 'dashboard') {
                    this.updateCharts();
                }

                if(target === 'history') {
                    this.loadFullHistory();
                }

                if(target === 'timelapse') {
                    this.loadGallery();
                    this.fetchCameraStatus();
                }
            });
        });
    },

    initCharts() {
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            },
            plugins: { legend: { display: false } },
            elements: { line: { tension: 0.4 }, point: { radius: 0 } }
        };

        this.tempChart = new Chart(document.getElementById('tempChart'), {
            type: 'line',
            data: { labels: [], datasets: [{ data: [], borderColor: '#f59e0b', borderWidth: 2, fill: true, backgroundColor: 'rgba(245,158,11,0.05)' }] },
            options: chartOptions
        });

        this.humChart = new Chart(document.getElementById('humChart'), {
            type: 'line',
            data: { labels: [], datasets: [{ data: [], borderColor: '#3b82f6', borderWidth: 2, fill: true, backgroundColor: 'rgba(59,130,246,0.05)' }] },
            options: chartOptions
        });

        // Full History Chart (Detailed View)
        this.fullHistoryChart = new Chart(document.getElementById('fullHistoryChart'), {
            type: 'line',
            data: { labels: [], datasets: [{ data: [], borderColor: '#10b981', borderWidth: 2, fill: true, backgroundColor: 'rgba(16,185,129,0.05)' }] },
            options: {
                ...chartOptions,
                plugins: { legend: { display: false } },
                scales: {
                    y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
                    x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', maxRotation: 45, minRotation: 45 } }
                }
            }
        });
    },

    async updateCharts() {
        try {
            const [tempRes, humRes] = await Promise.all([
                fetch('/api/history?sensor=temperature&limit=50'),
                fetch('/api/history?sensor=humidity&limit=50')
            ]);
            
            const parseDate = (isoStr) => {
                if(!isoStr) return "";
                const t = isoStr.split(/[- : T .]/);
                return `${t[3]}:${t[4]}`; // HH:MM
            };

            if (tempRes.ok) {
                const temps = await tempRes.json();
                this.tempChart.data.labels = temps.map(d => parseDate(d.timestamp));
                this.tempChart.data.datasets[0].data = temps.map(d => d.value);
                this.tempChart.update('none');
            }

            if (humRes.ok) {
                const hums = await humRes.json();
                this.humChart.data.labels = hums.map(d => parseDate(d.timestamp));
                this.humChart.data.datasets[0].data = hums.map(d => d.value);
                this.humChart.update('none');
            }
        } catch(e) { console.error("Chart update failed", e); }
    },

    async loadFullHistory() {
        try {
            const sensor = document.getElementById('hist-sensor-select').value;
            const res = await fetch(`/api/history?sensor=${sensor}&limit=500`);
            const data = await res.json();

            // Update Chart
            this.fullHistoryChart.data.labels = data.map(d => new Date(d.timestamp).toLocaleString([], {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit'}));
            this.fullHistoryChart.data.datasets[0].data = data.map(d => d.value);
            this.fullHistoryChart.data.datasets[0].borderColor = sensor === 'temperature' ? '#f59e0b' : (sensor === 'humidity' ? '#3b82f6' : '#10b981');
            this.fullHistoryChart.update();

            // Update Table
            const tbody = document.getElementById('history-table-body');
            tbody.innerHTML = '';
            // Show last 50 in table for performance
            data.slice().reverse().slice(0, 50).forEach(row => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${new Date(row.timestamp).toLocaleString()}</td>
                    <td style="font-weight:700;">${row.value}${sensor === 'temperature' ? '°C' : (sensor === 'humidity' ? '%' : ' L')}</td>
                `;
                tbody.appendChild(tr);
            });

        } catch(e) {
            console.error("Full history load failed", e);
            this.showToast("Failed to load history data", true);
        }
    },

    startClock() {
        setInterval(() => {
            const now = new Date();
            this.timeEl.textContent = now.toLocaleTimeString();
        }, 1000);
    },

    showToast(msg, isError=false) {
        this.toastEl.textContent = msg;
        this.toastEl.className = `toast show ${isError ? 'error' : ''}`;
        setTimeout(() => {
            this.toastEl.classList.remove('show');
        }, 3000);
    },

    async fetchStats() {
        try {
            const res = await fetch('/api/statistics');
            if(!res.ok) throw new Error('Failed to fetch');
            const data = await res.json();
            
            // Basic Environment
            document.getElementById('val-temp').textContent = data.temperature ? `${data.temperature}°C` : '--°C';
            document.getElementById('val-hum').textContent = data.humidity ? `${data.humidity}%` : '--%';
            
            // Hardware Status
            this.updateBadge('st-main-led', data.leds?.main?.state);
            this.updateBadge('st-ir-led', data.leds?.infrared?.state);
            this.updateBadge('st-ub-led', data.leds?.ultrablue?.state);
            this.updateBadge('st-vent', data.ventilation);
            this.updateBadge('st-tank', data.tank);
            this.updateBadge('st-irr', data.irrigation);

            // Cycle Data
            const cycleEl = document.getElementById('val-cycle');
            if(data.cycle_info && data.cycle_info.status === 'active') {
                const c = data.cycle_info;
                const hoursTxt = c.current_light_hours ? ` (${c.current_light_hours}h)` : '';
                cycleEl.textContent = `${c.current_cycle.toUpperCase()}${hoursTxt}`;
                
                document.getElementById('cyc-elapsed').textContent = c.days_elapsed;
                document.getElementById('cyc-rem').textContent = c.days_remaining;
                
                const total = c.days_elapsed + c.days_remaining;
                const perc = (c.days_elapsed / total) * 100;
                document.getElementById('cyc-progress').style.width = `${perc}%`;
                
                document.getElementById('cyc-start').textContent = c.cycle_start_date.split('T')[0];
                document.getElementById('cyc-end').textContent = c.cycle_end_date.split('T')[0];
            } else {
                cycleEl.textContent = 'INACTIVE';
                document.getElementById('cyc-elapsed').textContent = '0';
                document.getElementById('cyc-rem').textContent = '0';
                document.getElementById('cyc-progress').style.width = '0%';
            }

        } catch (e) {
            console.error(e);
        }
    },

    updateBadge(id, state) {
        const el = document.getElementById(id);
        if(state) {
            el.textContent = 'ON';
            el.className = 'badge on';
        } else {
            el.textContent = 'OFF';
            el.className = 'badge off';
        }
    },

    async toggleAction(type, target, action) {
        try {
            let url = `/api/${type}/${action}`;
            if(target) url = `/api/${type}/${target}/${action}`;
            
            const res = await fetch(url);
            const data = await res.json();
            
            if(data.status === 'success') {
                this.showToast(`${type} ${target ? target + ' ' : ''}turned ${action.toUpperCase()}`);
                this.fetchStats();
            } else {
                throw new Error(data.message);
            }
        } catch(e) {
            this.showToast(`Error: ${e.message}`, true);
        }
    },

    reloadFeed() {
        const img = document.getElementById('live-video');
        img.src = '';
        setTimeout(() => {
            img.src = '/api/video_feed?' + new Date().getTime();
        }, 100);
        this.showToast('Camera feed reloaded');
    },

    async captureFrame() {
        try {
            const res = await fetch('/api/timelapse/capture', {method: 'POST'});
            const data = await res.json();
            if(data.status==='success') {
                 this.showToast(data.message);
                 // Reload gallery if we are on the timelapse tab
                 if(document.getElementById('timelapse').classList.contains('active')) {
                     this.loadGallery();
                 }
            } else {
                 throw new Error(data.message);
            }
        } catch(e) {
            this.showToast(e.message, true);
        }
    },

    async loadGallery() {
        const container = document.getElementById('gallery-container');
        this.loadExports(); // Also load video history
        try {
            const res = await fetch('/api/timelapse/index');
            if(!res.ok) throw new Error('Failed to fetch gallery index');
            const data = await res.json();
            
            if(!data || data.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fa-solid fa-images"></i>
                        <p>No images found yet. Captures happen every hour.</p>
                        <p style="font-size: 0.8em; margin-top: 10px;">If you already took a "Manual Capture", check the camera health indicator above.</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = '';
            
            data.forEach(cosecha => {
                const cosechaEl = document.createElement('div');
                cosechaEl.className = 'cosecha-group';
                cosechaEl.innerHTML = `<h3><i class="fa-solid fa-folder-open"></i> ${cosecha.name}</h3>`;
                
                cosecha.dates.forEach(dateEntry => {
                    const dateEl = document.createElement('div');
                    dateEl.className = 'date-group';
                    dateEl.innerHTML = `<h4>${dateEntry.date}</h4>`;
                    
                    const grid = document.createElement('div');
                    grid.className = 'gallery-grid';
                    
                    dateEntry.images.forEach(img => {
                        const card = document.createElement('div');
                        card.className = 'image-card';
                        card.onclick = () => this.openLightbox(img.url, `${cosecha.name} - ${dateEntry.date} ${img.timestamp}`);
                        
                        card.innerHTML = `
                            <img src="${img.url}" alt="${img.name}" loading="lazy">
                            <div class="img-info">${img.timestamp.match(/.{1,2}/g).join(':')}</div>
                        `;
                        grid.appendChild(card);
                    });
                    
                    dateEl.appendChild(grid);
                    cosechaEl.appendChild(dateEl);
                });
                
                container.appendChild(cosechaEl);
            });

        } catch(e) {
            console.error("Gallery load failed", e);
            this.showToast("Failed to load image gallery", true);
        }
    },

    async exportTimelapse() {
        this.showToast("Starting video generation. This may take several minutes...", false);
        try {
            const res = await fetch('/api/timelapse/export', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ cosecha: this.active_cosecha, fps: 10 })
            });
            const data = await res.json();
            if(data.status === 'success') {
                this.showToast(data.message);
                setTimeout(() => this.loadExports(), 5000); // Check after 5s
            } else {
                throw new Error(data.message);
            }
        } catch(e) {
            this.showToast(e.message, true);
        }
    },

    async loadExports() {
        const container = document.getElementById('exports-container');
        const list = document.getElementById('exports-list');
        try {
            const res = await fetch('/api/timelapse/exports');
            const data = await res.json();
            
            if(!data || data.length === 0) {
                container.classList.add('hidden');
                return;
            }

            container.classList.remove('hidden');
            list.innerHTML = '';
            
            data.forEach(video => {
                const el = document.createElement('div');
                el.className = 'export-item glass-panel sm';
                el.innerHTML = `
                    <div class="video-info">
                        <strong>${video.name}</strong>
                        <span>${video.date} • ${video.size}</span>
                    </div>
                    <a href="/api/timelapse/download/${video.name}" class="btn primary sm"><i class="fa-solid fa-download"></i></a>
                `;
                list.appendChild(el);
            });
        } catch(e) { console.error("Failed to load exports", e); }
    },

    openLightbox(url, caption) {
        const lb = document.getElementById('lightbox');
        const img = document.getElementById('lightbox-img');
        const cap = document.getElementById('lightbox-caption');
        
        img.src = url;
        cap.textContent = caption;
        lb.classList.remove('hidden');
        document.body.style.overflow = 'hidden'; // Prevent scrolling
    },

    closeLightbox() {
        const lb = document.getElementById('lightbox');
        lb.classList.add('hidden');
        document.body.style.overflow = 'auto';
    },

    async fetchCameraStatus() {
        try {
            const res = await fetch('/api/camera/status');
            const data = await res.json();
            
            const dot = document.getElementById('cam-indicator');
            const txt = document.getElementById('cam-status-text');
            
            if(!dot || !txt) return;

            if(data.status === 'online') {
                dot.className = 'indicator-dot online';
                txt.textContent = `Camera Online (Index ${data.active_index})`;
            } else {
                dot.className = 'indicator-dot offline';
                txt.textContent = data.available_indices.length > 0 
                    ? `Camera Detected at ${data.available_indices.join(',')} but OFFLINE`
                    : 'No Camera Detected';
            }
        } catch(e) { console.error("Failed to fetch camera status", e); }
    },

    async loadConfigToForm() {
        try {
            const res = await fetch('/api/configs');
            const data = await res.json();
            this.fullConfig = data; // Cache full config for saving
            
            // Advanced raw editor update
            this.configEditor.value = JSON.stringify(data, null, 4);

            // Populate Selector
            this.harvestSelector.innerHTML = '<option value="">-- Create New / Select --</option>';
            const plants = data.plants || {};
            Object.keys(plants).forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                if(name === data.active_cosecha) opt.selected = true;
                this.harvestSelector.appendChild(opt);
            });
            
            // Set global interval
            if (document.getElementById('cfg-timelapse-interval')) {
                document.getElementById('cfg-timelapse-interval').value = data.timelapse_interval_minutes || 60;
            }
            if (document.getElementById('cfg-timelapse-enabled')) {
                document.getElementById('cfg-timelapse-enabled').checked = data.timelapse_enabled !== false;
            }
            
            this.renderHarvestData(data.active_cosecha || 'default');

        } catch(e) { console.error("Failed loading config into form", e); }
    },

    loadSelectedHarvest() {
        const name = this.harvestSelector.value;
        if(!name) {
            // Reset form for "New"
            document.getElementById('cfg-cosecha-name').value = '';
            document.getElementById('cfg-start-date').value = '';
            this.cyclesList.innerHTML = '';
            return;
        }
        this.renderHarvestData(name);
    },

    renderHarvestData(cosechaName) {
        const plantData = this.fullConfig?.plants?.[cosechaName] || {};
        document.getElementById('cfg-cosecha-name').value = cosechaName;
        document.getElementById('cfg-start-date').value = plantData.start_date || '';

        // Render Cycles
        this.cyclesList.innerHTML = '';
        const cycles = plantData.cycles || [];
        if (Array.isArray(cycles)) {
            cycles.forEach(cycle => {
                this.addCycleField(cycle.name, cycle);
            });
        } else {
            // Backward compatibility for old dict format
            Object.keys(cycles).forEach(name => {
                this.addCycleField(name, cycles[name]);
            });
        }
    },

    addCycleField(name = '', config = {}) {
        const id = 'cycle_' + Date.now();
        // Support legacy mapping if profiles exist
        let rs = config.ultra_red_sunrise, rf = config.ultra_red_full;
        let bs = config.infra_blue_sunrise, bf = config.infra_blue_full;
        
        if (config.logic_profile === 'vegetation') { rs=true; rf=false; bs=true; bf=true; }
        if (config.logic_profile === 'blooming') { rs=true; rf=true; bs=false; bf=false; }

        const html = `
            <div class="cycle-item" id="${id}">
                <div class="input-group" style="margin-bottom:12px;">
                    <label>Cycle Name</label>
                    <input type="text" class="cyc-name" value="${name}" placeholder="e.g. vegetation">
                </div>
                <div class="cycle-grid">
                    <div class="input-group"><label>Duration (days)</label><input type="number" class="cyc-duration" value="${config.duration_days || 7}"></div>
                    <div class="input-group"><label>Start Hour (0-23)</label><input type="number" class="cyc-light-start" value="${config.initial_time || 8}"></div>
                    <div class="input-group"><label>Red Step (mins)</label><input type="number" class="cyc-red-step" value="${config.ultra_red_step_mins || 15}"></div>
                    <div class="input-group"><label>Blue Step (mins)</label><input type="number" class="cyc-blue-step" value="${config.infra_blue_step_mins || 15}"></div>
                    
                    <div class="input-group"><label>Start Hours</label><input type="number" class="cyc-hours" value="${config.total_hours || 18}"></div>
                    <div class="input-group"><label>Target Hours (End)</label><input type="number" class="cyc-target-hours" value="${config.target_total_hours || config.total_hours || 18}"></div>
                    
                    <div class="input-group"><label>Irrigation Time</label><input type="time" class="cyc-irr-start" value="${config.irrigation_start_time || '08:00'}"></div>
                    <div class="input-group"><label>Irrigation Secs</label><input type="number" class="cyc-irr-timer" value="${config.irrigation_timer || 15}"></div>
                    <div class="input-group"><label>Target Volume (L)</label><input type="number" step="0.1" class="cyc-volume" value="${config.target_volume_liters || 0}"></div>
                </div>

                <div class="lighting-flags" style="margin-top:10px; display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
                    <div class="flag-col">
                        <label style="display:block; font-size: 0.8em; font-weight:600; margin-bottom:5px;">Ultra Red (Red)</label>
                        <label class="check-label"><input type="checkbox" class="cyc-rs" ${rs ? 'checked' : ''}> Sunrise/Sunset</label>
                        <label class="check-label"><input type="checkbox" class="cyc-rf" ${rf ? 'checked' : ''}> Full Cycle</label>
                    </div>
                    <div class="flag-col">
                        <label style="display:block; font-size: 0.8em; font-weight:600; margin-bottom:5px;">Infra Blue (Blue)</label>
                        <label class="check-label"><input type="checkbox" class="cyc-bs" ${bs ? 'checked' : ''}> Sunrise/Sunset</label>
                        <label class="check-label"><input type="checkbox" class="cyc-bf" ${bf ? 'checked' : ''}> Full Cycle</label>
                    </div>
                </div>

                <div class="watering-days-selector" style="margin-top:10px;">
                    <label style="display:block; font-size: 0.8em; margin-bottom:5px;">Watering Days</label>
                    <div style="display:flex; gap: 8px; flex-wrap: wrap;">
                        ${['M','T','W','T','F','S','S'].map((day, i) => `
                            <label style="font-size: 0.7em; cursor:pointer;">
                                <input type="checkbox" class="cyc-days" value="${i}" ${(config.watering_days || [0,1,2,3,4,5,6]).includes(i) ? 'checked' : ''}> ${day}
                            </label>
                        `).join('')}
                    </div>
                </div>
                <button class="btn danger-sm" style="margin-top:12px;" onclick="document.getElementById('${id}').remove()">Remove Cycle</button>
            </div>
        `;
        this.cyclesList.insertAdjacentHTML('beforeend', html);
    },

    setStartDateToday() {
        const now = new Date();
        const offset = now.getTimezoneOffset();
        const local = new Date(now.getTime() - (offset * 60 * 1000));
        const today = local.toISOString().split('T')[0];
        document.getElementById('cfg-start-date').value = today;
    },
    async generateAndSaveConfig() {
        const cosechaName = document.getElementById('cfg-cosecha-name').value;
        const startDate = document.getElementById('cfg-start-date').value;
        const timelapseInterval = parseInt(document.getElementById('cfg-timelapse-interval').value) || 60;
        const timelapseEnabled = document.getElementById('cfg-timelapse-enabled').checked;
        
        if(!cosechaName) {
            this.showToast("Please provide a name for the Cosecha", true);
            return;
        }

        const newConfig = JSON.parse(JSON.stringify(this.fullConfig));
        newConfig.active_cosecha = cosechaName;
        newConfig.timelapse_interval_minutes = timelapseInterval;
        newConfig.timelapse_enabled = timelapseEnabled;

        const cycles = [];
        document.querySelectorAll('.cycle-item').forEach(item => {
            const name = item.querySelector('.cyc-name').value;
            if(!name) return;
            
            const selectedDays = [];
            item.querySelectorAll('.cyc-days:checked').forEach(cb => selectedDays.push(parseInt(cb.value)));

            cycles.push({
                name: name,
                duration_days: parseInt(item.querySelector('.cyc-duration').value),
                initial_time: parseInt(item.querySelector('.cyc-light-start').value),
                total_hours: parseInt(item.querySelector('.cyc-hours').value),
                target_total_hours: parseInt(item.querySelector('.cyc-target-hours').value),
                
                ultra_red_step_mins: parseInt(item.querySelector('.cyc-red-step').value),
                infra_blue_step_mins: parseInt(item.querySelector('.cyc-blue-step').value),
                
                ultra_red_sunrise: item.querySelector('.cyc-rs').checked,
                ultra_red_full: item.querySelector('.cyc-rf').checked,
                infra_blue_sunrise: item.querySelector('.cyc-bs').checked,
                infra_blue_full: item.querySelector('.cyc-bf').checked,
                
                irrigation_start_time: item.querySelector('.cyc-irr-start').value,
                irrigation_timer: parseInt(item.querySelector('.cyc-irr-timer').value),
                target_volume_liters: parseFloat(item.querySelector('.cyc-volume').value),
                watering_days: selectedDays,
                multiplier: 1,
                tank_time: 15
            });
        });

        // Ensure we preserve other plants
        if(!this.fullConfig.plants) this.fullConfig.plants = {};
        
        this.fullConfig.active_cosecha = cosechaName;
        this.fullConfig.plants[cosechaName] = { 
            name: cosechaName, 
            start_date: startDate, 
            cycles: cycles 
        };

        this.configEditor.value = JSON.stringify(this.fullConfig, null, 4);
        await this.saveConfig();
        this.loadConfigToForm(); // Update selector list
    },

    toggleAdvancedMode() {
        this.advancedModeContainer.classList.toggle('hidden');
    },

    async loadConfig() {
        // ... (legacy kept for backup/direct call)
        this.loadConfigToForm();
    },

    async saveConfig() {
        try {
            const parsed = JSON.parse(this.configEditor.value);
            const res = await fetch('/api/configs', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(parsed)
            });
            const data = await res.json();
            if(data.status === 'success') {
                this.showToast("Configuration saved!");
                this.fetchStats();
            } else { throw new Error(data.message); }
        } catch(e) { this.showToast(`Error: ${e.message}`, true); }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    app.init();
});
