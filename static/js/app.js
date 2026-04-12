const app = {
    init() {
        this.cacheDOM();
        this.bindEvents();
        this.startClock();
        this.fetchStats();
        this.initCharts();
        
        this.initCharts();
        
        // Refresh stats and charts every 30 seconds (matches sensor cache)
        setInterval(() => {
            this.fetchStats();
            this.updateCharts();
        }, 30000);
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
    },

    async updateCharts() {
        try {
            const [tempRes, humRes] = await Promise.all([
                fetch('/api/history?sensor=temperature&limit=50'),
                fetch('/api/history?sensor=humidity&limit=50')
            ]);
            
            if (tempRes.ok) {
                const temps = await tempRes.json();
                this.tempChart.data.labels = temps.map(d => new Date(d.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
                this.tempChart.data.datasets[0].data = temps.map(d => d.value);
                this.tempChart.update('none');
            }

            if (humRes.ok) {
                const hums = await humRes.json();
                this.humChart.data.labels = hums.map(d => new Date(d.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
                this.humChart.data.datasets[0].data = hums.map(d => d.value);
                this.humChart.update('none');
            }
        } catch(e) { console.error("Chart update failed", e); }
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
                cycleEl.textContent = c.current_cycle.toUpperCase();
                
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
            } else {
                 throw new Error(data.message);
            }
        } catch(e) {
            this.showToast(e.message, true);
        }
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
        const cycles = plantData.cycles || {};
        Object.keys(cycles).forEach(name => {
            this.addCycleField(name, cycles[name]);
        });
    },

    addCycleField(name = '', config = {}) {
        const id = 'cycle_' + Date.now();
        const html = `
            <div class="cycle-item" id="${id}">
                <div class="input-group" style="margin-bottom:12px;">
                    <label>Cycle Name</label>
                    <input type="text" class="cyc-name" value="${name}" placeholder="e.g. vegetation">
                </div>
                <div class="cycle-grid">
                    <div class="input-group"><label>Duration (days)</label><input type="number" class="cyc-duration" value="${config.duration_days || 7}"></div>
                    <div class="input-group"><label>Start Hour (0-23)</label><input type="number" class="cyc-light-start" value="${config.initial_time || 8}"></div>
                    <div class="input-group"><label>Total Light Hours</label><input type="number" class="cyc-hours" value="${config.total_hours || 18}"></div>
                    <div class="input-group"><label>Logic Profile</label>
                        <select class="cyc-profile">
                            <option value="vegetation" ${config.logic_profile === 'vegetation' ? 'selected' : ''}>Vegetation (With Blue)</option>
                            <option value="blooming" ${config.logic_profile === 'blooming' ? 'selected' : ''}>Blooming (Red+Main)</option>
                        </select>
                    </div>
                    <div class="input-group"><label>Step Duration (mins)</label><input type="number" class="cyc-step" value="${config.sunrise_step_mins || 15}"></div>
                    <div class="input-group"><label>Irrigation Time</label><input type="time" class="cyc-irr-start" value="${config.irrigation_start_time || '08:00'}"></div>
                    <div class="input-group"><label>Irrigation Secs</label><input type="number" class="cyc-irr-timer" value="${config.irrigation_timer || 15}"></div>
                    <div class="input-group"><label>Target Volume (L)</label><input type="number" step="0.1" class="cyc-volume" value="${config.target_volume_liters || 0}"></div>
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
        
        if(!cosechaName) {
            this.showToast("Please provide a name for the Cosecha", true);
            return;
        }

        const cycles = {};
        document.querySelectorAll('.cycle-item').forEach(item => {
            const name = item.querySelector('.cyc-name').value;
            if(!name) return;
            
            const selectedDays = [];
            item.querySelectorAll('.cyc-days:checked').forEach(cb => selectedDays.push(parseInt(cb.value)));

            cycles[name] = {
                duration_days: parseInt(item.querySelector('.cyc-duration').value),
                initial_time: parseInt(item.querySelector('.cyc-light-start').value),
                total_hours: parseInt(item.querySelector('.cyc-hours').value),
                logic_profile: item.querySelector('.cyc-profile').value,
                sunrise_step_mins: parseInt(item.querySelector('.cyc-step').value),
                irrigation_start_time: item.querySelector('.cyc-irr-start').value,
                irrigation_timer: parseInt(item.querySelector('.cyc-irr-timer').value),
                target_volume_liters: parseFloat(item.querySelector('.cyc-volume').value),
                watering_days: selectedDays,
                multiplier: 1,
                tank_time: 15
            };
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
