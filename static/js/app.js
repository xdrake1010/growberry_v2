const app = {
    init() {
        this.cacheDOM();
        this.bindEvents();
        this.startClock();
        this.fetchStats();
        
        // Refresh stats every 10 seconds
        setInterval(() => this.fetchStats(), 10000);
    },

    cacheDOM() {
        this.tabs = document.querySelectorAll('.nav-links li');
        this.contents = document.querySelectorAll('.tab-content');
        this.timeEl = document.getElementById('current-time');
        this.toastEl = document.getElementById('toast');
        this.configEditor = document.getElementById('config-editor');
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
                    this.loadConfig();
                }
            });
        });
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
            if(data.cycle_info && data.cycle_info.status === 'active') {
                const c = data.cycle_info;
                document.getElementById('val-cycle').textContent = c.current_cycle.toUpperCase();
                
                document.getElementById('cyc-elapsed').textContent = c.days_elapsed;
                document.getElementById('cyc-rem').textContent = c.days_remaining;
                
                const total = c.days_elapsed + c.days_remaining;
                const perc = (c.days_elapsed / total) * 100;
                document.getElementById('cyc-progress').style.width = `${perc}%`;
                
                document.getElementById('cyc-start').textContent = c.cycle_start_date.split('T')[0];
                document.getElementById('cyc-end').textContent = c.cycle_end_date.split('T')[0];
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

    async loadConfig() {
        try {
            const res = await fetch('/api/configs');
            const data = await res.json();
            this.configEditor.value = JSON.stringify(data, null, 4);
        } catch(e) {
            console.error("Failed loading config", e);
        }
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
                this.showToast("Configuration saved and reloaded!");
                this.fetchStats();
            } else {
                throw new Error(data.message);
            }
        } catch(e) {
            this.showToast(`Invalid JSON or Save Failed: ${e.message}`, true);
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    app.init();
});
