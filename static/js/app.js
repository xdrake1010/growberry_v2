const app = {
    init() {
        console.log("Growberry App initializing...");
        try { this.cacheDOM(); } catch(e) { console.error("DOM Cache failed", e); }
        try { this.bindEvents(); } catch(e) { console.error("Events binding failed", e); }
        try { this.initMobileMenu(); } catch(e) { console.error("Mobile menu failed", e); }
        try { this.startClock(); } catch(e) { console.error("Clock failed", e); }
        try { this.initCharts(); } catch(e) { console.error("Charts failed", e); }
        
        try {
            this.galleryState = { cosecha: null, date: null, rawData: [] };
            this.fetchStats();
            this.loadConfigToForm(); // Pre-load config for quick settings access
            
            // Refresh stats and charts every 30 seconds
            setInterval(async () => {
                await this.fetchStats();
                await this.updateCharts();
                if(document.getElementById('timelapse') && document.getElementById('timelapse').classList.contains('active')) {
                    this.fetchCameraStatus();
                }
            }, 30000);
        } catch(e) { console.error("Main loop failed", e); }
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
                    this.loadTimelapseQuickSettings();
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
            elements: { 
                line: { tension: 0.4 }, 
                point: { radius: 4, hitRadius: 10, hoverRadius: 6 } // Increased for visibility
            }
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
            const harvest = this.activeCosecha || '';
            const [tempRes, humRes] = await Promise.all([
                fetch(`/api/history?sensor=temperature&limit=50&harvest=${harvest}`),
                fetch(`/api/history?sensor=humidity&limit=50&harvest=${harvest}`)
            ]);
            
            const parseDate = (isoStr) => {
                if(!isoStr) return "";
                const parts = isoStr.split(/[T.Z\-\s:]/);
                // Safe extraction of HH:MM (usually indices 3 and 4)
                if (parts.length < 5) return isoStr; 
                return `${parts[3]}:${parts[4]}`;
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
            const harvest = this.activeCosecha || '';
            const res = await fetch(`/api/history?sensor=${sensor}&limit=500&harvest=${harvest}`);
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
            if(!res.ok) throw new Error(`Server Error (${res.status})`);
            const data = await res.json();
            
            this.activeCosecha = data.active_cosecha || data.cycle_info?.cosecha_name;

            // Dashboard & Overlay Harvest Name
            const dashNameEl = document.getElementById('dash-cosecha-name');
            if (dashNameEl) dashNameEl.textContent = this.activeCosecha || 'No Active Harvest';
            
            const ovNameEl = document.getElementById('ov-cosecha');
            if (ovNameEl) ovNameEl.textContent = this.activeCosecha || 'None';

            // Basic Environment
            const tempStr = data.temperature ? `${data.temperature}°C` : '--°C';
            const humStr = data.humidity ? `${data.humidity}%` : '--%';
            
            document.getElementById('val-temp').textContent = tempStr;
            document.getElementById('val-hum').textContent = humStr;
            
            const ovTempEl = document.getElementById('ov-temp');
            const ovHumEl = document.getElementById('ov-hum');
            if (ovTempEl) ovTempEl.innerHTML = `<i class="fa-solid fa-temperature-half"></i> ${tempStr}`;
            if (ovHumEl) ovHumEl.innerHTML = `<i class="fa-solid fa-droplet"></i> ${humStr}`;
            
            // Hardware Status
            this.updateBadge('st-main-led', data.leds?.main?.state);
            this.updateBadge('st-ir-led', data.leds?.infrared?.state);
            this.updateBadge('st-ub-led', data.leds?.ultrablue?.state);
            this.updateBadge('st-vent', data.ventilation);
            this.updateBadge('st-tank', data.tank);
            this.updateBadge('st-irr', data.irrigation);

            // Manual Controls Synchronization
            this.syncManualControls(data);

            // Cycle Data
            const cycleEl = document.getElementById('val-cycle');
            if(data.cycle_info && data.cycle_info.status === 'active') {
                const c = data.cycle_info;
                const hoursTxt = c.current_light_hours ? ` (${c.current_light_hours}h)` : '';
                cycleEl.textContent = `${(c.current_cycle || 'active').toUpperCase()}${hoursTxt}`;
                
                if (document.getElementById('cyc-elapsed')) document.getElementById('cyc-elapsed').textContent = c.days_elapsed || 0;
                if (document.getElementById('cyc-rem')) document.getElementById('cyc-rem').textContent = c.days_remaining || 0;
                
                const total = (c.days_elapsed || 0) + (c.days_remaining || 0);
                const perc = total > 0 ? ((c.days_elapsed || 0) / total) * 100 : 0;
                if (document.getElementById('cyc-progress')) document.getElementById('cyc-progress').style.width = `${perc}%`;
                
                if (c.cycle_start_date && document.getElementById('cyc-start')) document.getElementById('cyc-start').textContent = c.cycle_start_date.split('T')[0];
                if (c.cycle_end_date && document.getElementById('cyc-end')) document.getElementById('cyc-end').textContent = c.cycle_end_date.split('T')[0];
                
                // NEW: Render the multi-segment journey timeline
                this.renderTimeline(c);
            } else {
                if (cycleEl) cycleEl.textContent = 'INACTIVE';
                if (document.getElementById('cyc-elapsed')) document.getElementById('cyc-elapsed').textContent = '0';
                if (document.getElementById('cyc-rem')) document.getElementById('cyc-rem').textContent = '0';
                if (document.getElementById('cyc-progress')) document.getElementById('cyc-progress').style.width = '0%';
            }

        } catch (e) {
            console.error(e);
        }
    },

    renderTimeline(c) {
        if (!c || !c.all_cycles) return;
        
        const totalJourneyDays = c.all_cycles.reduce((sum, cycle) => sum + cycle.duration, 0);
        const currentJourneyDay = c.total_days || 0;
        
        const daysInfoEl = document.getElementById('total-days-info');
        if (daysInfoEl) daysInfoEl.textContent = `Day ${currentJourneyDay} of ${totalJourneyDays}`;
        
        const bar = document.getElementById('timeline-bar');
        const marker = document.getElementById('timeline-marker');
        
        if (!bar || !marker) return;

        // Clear previous segments (except marker)
        Array.from(bar.children).forEach(child => { if(child !== marker) child.remove(); });
        
        let accumulatedDays = 0;
        c.all_cycles.forEach((cycle, index) => {
            const widthPerc = (cycle.duration / totalJourneyDays) * 100;
            
            // Segment
            const seg = document.createElement('div');
            seg.className = `timeline-segment seg-${index % 5}`;
            seg.style.width = `${widthPerc}%`;
            bar.insertBefore(seg, marker);
            
            accumulatedDays += cycle.duration;
        });
        
        // Position Needle
        const markerPos = Math.min((currentJourneyDay / totalJourneyDays) * 100, 100);
        marker.style.left = `${markerPos}%`;
    },

    updateBadge(id, state) {
        const el = document.getElementById(id);
        if(!el) return;
        if(state) {
            el.textContent = 'ON';
            el.className = 'badge on';
        } else {
            el.textContent = 'OFF';
            el.className = 'badge off';
        }
    },

    syncManualControls(data) {
        const states = {
            'led-main': data.leds?.main?.state,
            'led-infrared': data.leds?.infrared?.state,
            'led-ultrablue': data.leds?.ultrablue?.state,
            'vent': data.ventilation,
            'tank': data.tank,
            'irrigation': data.irrigation
        };

        for (const [key, isOn] of Object.entries(states)) {
            const btnOn = document.getElementById(`ctrl-${key}-on`);
            const btnOff = document.getElementById(`ctrl-${key}-off`);
            
            if (btnOn && btnOff) {
                if (isOn) {
                    btnOn.classList.add('active');
                    btnOff.classList.remove('active');
                } else {
                    btnOn.classList.remove('active');
                    btnOff.classList.add('active');
                }
            }
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

    async syncGallery() {
        this.showToast("Syncing gallery index...");
        await this.loadGallery(true);
    },

    async loadGallery(forceSync = false) {
        const container = document.getElementById('gallery-container');
        this.loadExports(); // Also load video history
        try {
            if (forceSync || this.galleryState.rawData.length === 0) {
                const res = await fetch('/api/timelapse/index');
                if(!res.ok) throw new Error(`Gallery Sync Error (${res.status})`);
                this.galleryState.rawData = await res.json();
            }
            
            this.renderGallery();
        } catch(e) {
            console.error("Gallery sync failed", e);
            this.showToast("Failed to sync gallery", true);
        }
    },

    renderGallery() {
        const container = document.getElementById('gallery-container');
        const { cosecha, date, rawData } = this.galleryState;
        
        this.renderBreadcrumbs();
        container.innerHTML = '';

        if (!rawData || rawData.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-images"></i>
                    <p>No images found yet. Captures happen every hour.</p>
                </div>
            `;
            return;
        }

        if (!cosecha) {
            this.renderHarvests(rawData);
        } else if (cosecha && !date) {
            const cosechaData = rawData.find(c => c.name === cosecha);
            this.renderDates(cosechaData);
        } else {
            const cosechaData = rawData.find(c => c.name === cosecha);
            const dateData = cosechaData?.dates.find(d => d.date === date);
            this.renderImages(cosechaData, dateData);
        }
    },

    renderHarvests(data) {
        const grid = document.createElement('div');
        grid.className = 'category-grid';
        data.forEach(cosecha => {
            const card = document.createElement('div');
            card.className = 'folder-card glass-panel sm';
            card.onclick = () => { this.galleryState.cosecha = cosecha.name; this.renderGallery(); };
            card.innerHTML = `
                <div class="card-top-actions">
                    <button class="btn-icon danger" onclick="event.stopPropagation(); app.deleteHarvest('${cosecha.name}')">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
                <i class="fa-solid fa-leaf"></i>
                <strong>${cosecha.name}</strong>
                <span>${cosecha.dates.length} Days tracked</span>
            `;
            grid.appendChild(card);
        });
        document.getElementById('gallery-container').appendChild(grid);
    },

    renderDates(cosechaData) {
        const grid = document.createElement('div');
        grid.className = 'category-grid';
        cosechaData.dates.forEach(entry => {
            const card = document.createElement('div');
            card.className = 'folder-card with-preview glass-panel sm';
            card.onclick = () => { this.galleryState.date = entry.date; this.renderGallery(); };
            
            const firstImg = entry.images[0]?.url || '';
            card.innerHTML = `
                <img src="${firstImg}" class="preview-img" loading="lazy">
                <div class="folder-overlay">
                    <div class="card-top-actions">
                        <button class="btn-icon danger" onclick="event.stopPropagation(); app.deleteFolder('${this.galleryState.cosecha}', '${entry.date}')">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                    <i class="fa-solid fa-calendar-day" style="font-size: 32px;"></i>
                    <strong>${entry.date}</strong>
                    <span>${entry.images.length} Captures</span>
                </div>
            `;
            grid.appendChild(card);
        });
        document.getElementById('gallery-container').appendChild(grid);
    },

    renderImages(cosecha, dateEntry) {
        const grid = document.createElement('div');
        grid.className = 'gallery-grid';
        dateEntry.images.forEach(img => {
            const card = document.createElement('div');
            card.className = 'image-card';
            card.onclick = () => this.openLightbox(img.url, `${cosecha.name} - ${dateEntry.date} ${img.timestamp}`);
            card.innerHTML = `
                <img src="${img.url}" alt="${img.name}" loading="lazy">
                <button class="btn-delete" onclick="event.stopPropagation(); app.deleteImage('${this.galleryState.cosecha}', '${this.galleryState.date}', '${img.name}')">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
                <div class="img-info">${img.timestamp.match(/.{1,2}/g).join(':')}</div>
            `;
            grid.appendChild(card);
        });
        document.getElementById('gallery-container').appendChild(grid);
    },

    renderBreadcrumbs() {
        const container = document.getElementById('gallery-breadcrumbs');
        const { cosecha, date } = this.galleryState;
        
        container.innerHTML = `<span class="breadcrumb-item ${!cosecha ? 'active' : ''}" onclick="app.resetGallery()">Gallery</span>`;
        if (cosecha) {
            container.innerHTML += `<span class="breadcrumb-sep">/</span><span class="breadcrumb-item ${!date ? 'active' : ''}" onclick="app.galleryState.date = null; app.renderGallery()">${cosecha}</span>`;
        }
        if (date) {
            container.innerHTML += `<span class="breadcrumb-sep">/</span><span class="breadcrumb-item active">${date}</span>`;
        }
    },

    async loadTimelapseQuickSettings() {
        if (!this.fullConfig) await this.fetchFullConfig();
        const cfg = this.fullConfig || {};
        document.getElementById('glr-timelapse-enabled').checked = cfg.timelapse_enabled === true;
        document.getElementById('glr-timelapse-interval').value = cfg.timelapse_interval_minutes || 60;
    },

    resetGallery() {
        this.galleryState.cosecha = null;
        this.galleryState.date = null;
        this.renderGallery();
    },

    async saveTimelapseQuickSettings() {
        const enabled = document.getElementById('glr-timelapse-enabled').checked;
        const interval = parseInt(document.getElementById('glr-timelapse-interval').value) || 60;
        
        try {
            // Ensure fullConfig is loaded using new safe magic
            if (!this.fullConfig) {
                await this.fetchFullConfig();
            }
            
            const newConfig = JSON.parse(JSON.stringify(this.fullConfig || {}));
            newConfig.timelapse_enabled = enabled;
            newConfig.timelapse_interval_minutes = interval;
            
            const res = await fetch('/api/configs', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(newConfig)
            });
            
            if (!res.ok) throw new Error(`Save Failed (${res.status})`);
            
            const data = await res.json();
            if (data.status === 'success') {
                this.showToast("Timelapse settings updated");
                this.fullConfig = newConfig;
            } else { throw new Error(data.message); }
        } catch(e) { this.showToast(e.message, true); }
    },

    async openExportModal() {
        if(!this.fullConfig) await this.fetchFullConfig();
        const sel = document.getElementById('exp-cosecha-selector');
        sel.innerHTML = '';
        if(this.fullConfig?.plants) {
            Object.keys(this.fullConfig.plants).forEach(name => {
                const opt = document.createElement('option');
                opt.value = name; opt.textContent = name;
                if(name === this.activeCosecha) opt.selected = true;
                sel.appendChild(opt);
            });
        }
        
        // Fetch harvest info for date helpers
        try {
            const res = await fetch('/api/harvests/info');
            this.harvestsInfo = await res.json();
        } catch(e) { console.error("Could not fetch harvest info", e); }
        
        document.getElementById('export-modal').classList.remove('hidden');
    },

    setExportRange(type) {
        const cosecha = document.getElementById('exp-cosecha-selector').value;
        if (!this.harvestsInfo || !this.harvestsInfo[cosecha]) {
            this.showToast("No data available for this harvest yet", true);
            return;
        }
        
        const info = this.harvestsInfo[cosecha];
        if (type === 'start') {
            const date = info.config_start || info.first_image;
            if (date) document.getElementById('exp-date-from').value = date;
        } else if (type === 'end') {
            const lastImg = info.last_image || new Date().toISOString().split('T')[0];
            document.getElementById('exp-date-to').value = lastImg;
        }
    },

    async deleteHarvestPlan() {
        const name = document.getElementById('cfg-load-selector').value;
        if (!name) return;
        
        if (!confirm(`Are you sure you want to delete the plan "${name}"? This ONLY deletes the configuration, not the images.`)) {
            return;
        }
        
        try {
            const res = await fetch(`/api/harvests/${name}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.status === 'success') {
                this.showToast(data.message);
                await this.fetchFullConfig();
                this.loadConfigToForm();
                this.fetchStats(); // Update UI if active harvest changed
            } else { throw new Error(data.message); }
        } catch(e) { this.showToast(e.message, true); }
    },

    closeExportModal() {
        document.getElementById('export-modal').classList.add('hidden');
    },

    async runExport() {
        const cosecha = document.getElementById('exp-cosecha-selector').value;
        const from = document.getElementById('exp-date-from').value;
        const to = document.getElementById('exp-date-to').value;
        const fps = document.getElementById('exp-fps').value;
        const resolution = document.getElementById('exp-resolution').value;

        this.closeExportModal();

        // Show progress overlay immediately
        const overlay = document.getElementById('export-progress-overlay');
        if (overlay) {
            overlay.classList.remove('hidden');
            document.getElementById('export-progress-bar').style.width = '0%';
            document.getElementById('export-progress-pct').textContent = '0%';
            document.getElementById('export-progress-status').textContent = 'Starting...';
            document.getElementById('export-job-name').textContent = `${cosecha} @ ${resolution}`;
            document.getElementById('export-dismiss-btn').style.display = 'none';
        }

        try {
            const res = await fetch('/api/timelapse/export', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ cosecha, fps, date_from: from, date_to: to, resolution })
            });
            const data = await res.json();
            if (data.status === 'success') {
                this._pollExportProgress();
            } else {
                throw new Error(data.message);
            }
        } catch(e) {
            this.showToast(e.message, true);
            if (overlay) overlay.classList.add('hidden');
        }
    },

    _exportPollTimer: null,

    _pollExportProgress() {
        if (this._exportPollTimer) clearInterval(this._exportPollTimer);
        this._exportPollTimer = setInterval(async () => {
            try {
                const res = await fetch('/api/timelapse/export/status');
                const s = await res.json();

                const bar = document.getElementById('export-progress-bar');
                const pct = document.getElementById('export-progress-pct');
                const statusEl = document.getElementById('export-progress-status');
                const dismissBtn = document.getElementById('export-dismiss-btn');

                if (bar) bar.style.width = `${s.progress}%`;
                if (pct) pct.textContent = `${s.progress}%`;
                if (statusEl) statusEl.textContent = s.status || 'Processing...';

                if (!s.is_exporting) {
                    clearInterval(this._exportPollTimer);
                    this._exportPollTimer = null;
                    if (dismissBtn) dismissBtn.style.display = 'block';
                    // Reload exports list
                    setTimeout(() => this.loadExports(), 500);
                }
            } catch(e) {
                clearInterval(this._exportPollTimer);
                this._exportPollTimer = null;
            }
        }, 1500);
    },

    dismissExportProgress() {
        const overlay = document.getElementById('export-progress-overlay');
        if (overlay) overlay.classList.add('hidden');
        if (this._exportPollTimer) {
            clearInterval(this._exportPollTimer);
            this._exportPollTimer = null;
        }
    },

    async deleteImage(cosecha, date, filename) {
        if(!confirm("Delete this image?")) return;
        try {
            const res = await fetch(`/api/timelapse/delete/image/${cosecha}/${date}/${filename}`, { method: 'DELETE' });
            if(res.ok) {
                this.showToast("Image deleted");
                await this.loadGallery(true);
            }
        } catch(e) { this.showToast("Delete failed", true); }
    },

    async deleteFolder(cosecha, date) {
        if(!confirm(`Delete EVERYTHING from ${date}?`)) return;
        try {
            const res = await fetch(`/api/timelapse/delete/folder/${cosecha}/${date}`, { method: 'DELETE' });
            if(res.ok) {
                this.showToast("Day deleted");
                await this.loadGallery(true);
            }
        } catch(e) { this.showToast("Delete failed", true); }
    },

    async deleteHarvest(cosecha) {
        if(!confirm(`PERMANENTLY DELETE all images for ${cosecha}?`)) return;
        try {
            const res = await fetch(`/api/timelapse/delete/cosecha/${cosecha}`, { method: 'DELETE' });
            if(res.ok) {
                this.showToast("Harvest deleted");
                await this.loadGallery(true);
            }
        } catch(e) { this.showToast("Delete failed", true); }
    },

    async deleteVideo(filename) {
        if(!confirm("Delete this video?")) return;
        try {
            const res = await fetch(`/api/timelapse/delete/video/${filename}`, { method: 'DELETE' });
            if(res.ok) {
                this.showToast("Video deleted");
                this.loadExports();
            }
        } catch(e) { this.showToast("Delete failed", true); }
    },

    async exportTimelapse() {
        this.openExportModal();
    },

    async loadExports() {
        const container = document.getElementById('exports-container');
        const list = document.getElementById('exports-list');
        try {
            const res = await fetch('/api/timelapse/exports');
            const data = await res.json();

            if (!data || data.length === 0) {
                container.classList.add('hidden');
                return;
            }

            container.classList.remove('hidden');
            list.innerHTML = '';

            data.forEach(video => {
                const card = document.createElement('div');
                card.className = 'video-card';

                const nameParts = video.name.split('_');
                const harvestName = nameParts[0] || 'Unknown';
                const dateRaw = nameParts[1] || '';
                const displayDate = dateRaw.length === 8
                    ? `${dateRaw.slice(0,4)}-${dateRaw.slice(4,6)}-${dateRaw.slice(6,8)}`
                    : video.date;

                const streamUrl = `/api/timelapse/stream/${video.name}`;
                const downloadUrl = `/api/timelapse/download/${video.name}`;

                card.innerHTML = `
                    <div class="card-header">
                        <h4>${harvestName}</h4>
                        <button class="btn-icon danger" onclick="app.deleteVideo('${video.name}')"><i class="fa-solid fa-trash-can"></i></button>
                    </div>
                    <video class="export-video-player" controls preload="metadata" src="${streamUrl}">
                        Your browser does not support HTML5 video.
                    </video>
                    <div class="video-meta">
                        <span><i class="fa-solid fa-calendar"></i> ${displayDate}</span>
                        <span><i class="fa-solid fa-clock"></i> ${video.date.split(' ')[1] || ''}</span>
                        <span><i class="fa-solid fa-weight-hanging"></i> ${video.size}</span>
                        <span><i class="fa-solid fa-file-invoice"></i> ${video.name}</span>
                    </div>
                    <div class="card-actions">
                        <a href="${downloadUrl}" class="btn primary sm"><i class="fa-solid fa-download"></i> Download MP4</a>
                    </div>
                `;
                list.appendChild(card);
            });
        } catch(e) { console.error('Failed to load exports', e); }
    },

    openLightbox(url, caption) {
        const lb = document.getElementById('lightbox');
        const img = document.getElementById('lightbox-img');
        const cap = document.getElementById('lightbox-caption');
        const downBtn = document.getElementById('lightbox-download');
        
        img.src = url;
        cap.textContent = caption;
        
        if (downBtn) {
            downBtn.href = url;
            downBtn.download = url.split('/').pop() || 'capture.jpg';
        }
        
        lb.classList.remove('hidden');
        document.body.style.overflow = 'hidden'; // Prevent scrolling
    },

    closeLightbox(e) {
        if (e && e.target.id !== 'lightbox') return; // Only close if clicking background
        this.forceCloseLightbox();
    },
    
    forceCloseLightbox() {
        const lb = document.getElementById('lightbox');
        lb.classList.add('hidden');
        document.body.style.overflow = 'auto'; // Restore scroll
    },

    async fetchCameraStatus() {
        try {
            const res = await fetch('/api/camera/status');
            if (!res.ok) return; // Silent fail for status polling
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

    async fetchFullConfig() {
        try {
            const res = await fetch('/api/configs');
            if (!res.ok) throw new Error(`Config Load Error (${res.status})`);
            const data = await res.json();
            this.fullConfig = data;
            return data;
        } catch(e) {
            console.error("fetchFullConfig failed", e);
            throw e;
        }
    },

    async loadConfigToForm() {
        try {
            const data = await this.fetchFullConfig();
            
            // Advanced raw editor update - Only if element exists in cave
            if (this.configEditor) {
                this.configEditor.value = JSON.stringify(data, null, 4);
            }

            // Populate Selector - Only if element exists in cave
            if (this.harvestSelector) {
                this.harvestSelector.innerHTML = '<option value="">-- Create New / Select --</option>';
                const plants = data.plants || {};
                Object.keys(plants).forEach(name => {
                    const opt = document.createElement('option');
                    opt.value = name;
                    opt.textContent = name;
                    this.harvestSelector.appendChild(opt);
                });
                
                // NEW: Auto-load the active harvest if present
                if (this.activeCosecha) {
                    this.harvestSelector.value = this.activeCosecha;
                    this.loadSelectedHarvest();
                }
            }
        } catch(e) { this.showToast(e.message, true); }
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
        document.getElementById('cfg-timelapse-res').value = plantData.timelapse_resolution || '320x240';

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
        try {
            const cosechaName = document.getElementById('cfg-cosecha-name').value;
            const startDate = document.getElementById('cfg-start-date').value;
            const logInterval = parseInt(document.getElementById('cfg-log-interval').value) || 1;
            
            // CORRECTED: Using 'glr-' prefix which matches index.html
            const timelapseInterval = parseInt(document.getElementById('glr-timelapse-interval').value) || 60;
            const timelapseEnabled = document.getElementById('glr-timelapse-enabled').checked;
            
            if(!cosechaName) {
                this.showToast("Please provide a name for the Cosecha", true);
                return;
            }

            // Create a deep copy to manipulate safely
            const updatedConfig = JSON.parse(JSON.stringify(this.fullConfig));
            
            // Global settings
            updatedConfig.active_cosecha = cosechaName;
            updatedConfig.timelapse_interval_minutes = timelapseInterval;
            updatedConfig.timelapse_enabled = timelapseEnabled;
            updatedConfig.sensor_log_interval_minutes = logInterval;
            
            const timelapseRes = document.getElementById('cfg-timelapse-res').value;

            // Harvest Plan Cycles
            const cycles = [];
            document.querySelectorAll('.cycle-item').forEach(item => {
                const name = item.querySelector('.cyc-name').value;
                if(!name) return;
                
                const selectedDays = [];
                item.querySelectorAll('.cyc-days:checked').forEach(cb => selectedDays.push(parseInt(cb.value)));

                cycles.push({
                    name: name,
                    duration_days: parseInt(item.querySelector('.cyc-duration').value) || 1,
                    initial_time: parseInt(item.querySelector('.cyc-light-start').value) || 8,
                    total_hours: parseInt(item.querySelector('.cyc-hours').value) || 12,
                    target_total_hours: parseInt(item.querySelector('.cyc-target-hours').value) || 12,
                    ultra_red_step_mins: parseInt(item.querySelector('.cyc-red-step').value) || 15,
                    infra_blue_step_mins: parseInt(item.querySelector('.cyc-blue-step').value) || 15,
                    ultra_red_sunrise: item.querySelector('.cyc-rs').checked,
                    ultra_red_full: item.querySelector('.cyc-rf').checked,
                    infra_blue_sunrise: item.querySelector('.cyc-bs').checked,
                    infra_blue_full: item.querySelector('.cyc-bf').checked,
                    irrigation_start_time: item.querySelector('.cyc-irr-start').value || "08:00",
                    irrigation_timer: parseInt(item.querySelector('.cyc-irr-timer').value) || 15,
                    target_volume_liters: parseFloat(item.querySelector('.cyc-volume').value) || 0,
                    watering_days: selectedDays,
                    multiplier: 1,
                    tank_time: 15
                });
            });

            if(!updatedConfig.plants) updatedConfig.plants = {};
            updatedConfig.plants[cosechaName] = { 
                name: cosechaName, 
                start_date: startDate, 
                timelapse_resolution: timelapseRes,
                cycles: cycles 
            };

            // Sync back to internal state and JSON editor
            this.fullConfig = updatedConfig;
            this.configEditor.value = JSON.stringify(this.fullConfig, null, 4);
            
            await this.saveConfig();
            this.showToast("Harvest Plan saved successfully!");
            
            // Refresh form to reflect changes (especially if we renamed cosecha)
            await this.loadConfigToForm();
            
        } catch(e) {
            console.error("Critical error in generateAndSaveConfig", e);
            this.showToast("Failed to save Harvest Plan: " + e.message, true);
        }
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
