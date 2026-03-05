window.ws = null;
window.tasks = [];
window.progressChart = null;
window.workerChart = null;
window.distributionCharts = {};
window.wsConnected = false;
window.availableTopics = [];
window.generatorsList = [];

// Placeholder functions to prevent errors
function initProgressChart() {
    console.log('initProgressChart called');
}

function initWorkerChart() {
    console.log('initWorkerChart called');
}

async function loadStats() {
    const completedTasks = window.tasks.filter(t => t.status === 'completed');
    const runningTasks = window.tasks.filter(t => t.status === 'running');
    const totalRecords = completedTasks.reduce((sum, t) => sum + (t.progress || 0), 0);
    const statTotalTasks = document.getElementById('stat-total-tasks');
    const statTotalRecords = document.getElementById('stat-total-records');
    const statRunning = document.getElementById('stat-running');
    const statCompleted = document.getElementById('stat-completed');
    if (statTotalTasks) statTotalTasks.textContent = window.tasks.length;
    if (statTotalRecords) statTotalRecords.textContent = totalRecords.toLocaleString();
    if (statRunning) statRunning.textContent = runningTasks.length;
    if (statCompleted) statCompleted.textContent = completedTasks.length;
}

// Load distribution data from API
async function loadDistributionData() {
    const container = document.getElementById('distribution-charts');
    if (!container) return;
    
    container.innerHTML = '<div style="padding: 20px; text-align: center;">加载中...</div>';
    
    try {
        const response = await fetch('/api/stats/aggregate');
        const data = await response.json();
        
        if (!data.charts || Object.keys(data.charts).length === 0) {
            container.innerHTML = '<div style="padding: 20px; text-align: center;">暂无数据，请先完成一些生成任务</div>';
            return;
        }
        
        const charts = data.charts;
        
        let html = '';
        
        if (charts.languages) {
            html += `<div class="dimension-card"><div class="dimension-title">语言分布 (${data.analysis?.total_records || 0} 条)</div><canvas id="langChart"></canvas></div>`;
        }
        if (charts.races) {
            html += `<div class="dimension-card"><div class="dimension-title">种族分布</div><canvas id="raceChart"></canvas></div>`;
        }
        if (charts.personas) {
            html += `<div class="dimension-card"><div class="dimension-title">人格分布</div><canvas id="personaChart"></canvas></div>`;
        }
        if (charts.topics) {
            html += `<div class="dimension-card"><div class="dimension-title">话题分布</div><canvas id="topicChart"></canvas></div>`;
        }
        
        const statusCounts = {
            completed: window.tasks.filter(t => t.status === 'completed').length, 
            running: window.tasks.filter(t => t.status === 'running').length, 
            pending: window.tasks.filter(t => t.status === 'pending').length, 
            failed: window.tasks.filter(t => t.status === 'failed').length 
        };
        html += `<div class="dimension-card"><div class="dimension-title">任务状态</div><canvas id="statusChart"></canvas></div>`;
        
        container.innerHTML = html;
        
        setTimeout(() => {
            if (typeof Chart === 'undefined') {
                console.error('Chart.js not loaded');
                container.innerHTML = '<div style="padding: 20px; text-align: center;">图表库加载失败，请刷新页面</div>';
                return;
            }
            if (charts.languages) {
                new Chart(document.getElementById('langChart'), {
                    type: 'bar',
                    data: { labels: charts.languages.labels, datasets: [{ label: '数量', data: charts.languages.values, backgroundColor: ['#ffd700', '#00ff88', '#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#ffeaa7', '#dfe6e9'] }] },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
                });
            }
            if (charts.races) {
                new Chart(document.getElementById('raceChart'), {
                    type: 'pie',
                    data: { labels: charts.races.labels, datasets: [{ label: '数量', data: charts.races.values, backgroundColor: generateColors(charts.races.labels.length) }] },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' } } }
                });
            }
            if (charts.personas) {
                new Chart(document.getElementById('personaChart'), {
                    type: 'pie',
                    data: { labels: charts.personas.labels, datasets: [{ label: '数量', data: charts.personas.values, backgroundColor: generateColors(charts.personas.labels.length) }] },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' } } }
                });
            }
            if (charts.topics) {
                new Chart(document.getElementById('topicChart'), {
                    type: 'bar',
                    data: { labels: charts.topics.labels, datasets: [{ label: '数量', data: charts.topics.values, backgroundColor: generateColors(charts.topics.labels.length) }] },
                    options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } } }
                });
            }
            new Chart(document.getElementById('statusChart'), {
                type: 'pie',
                data: { labels: ['已完成', '运行中', '等待中', '失败'], datasets: [{ data: [statusCounts.completed, statusCounts.running, statusCounts.pending, statusCounts.failed], backgroundColor: ['#00ff88', '#ffd700', '#888', '#ff4444'] }] },
                options: { responsive: true, maintainAspectRatio: false }
            });
        }, 100);
        
    } catch (error) {
        console.error('Failed to load distribution data:', error);
        container.innerHTML = '<div style="padding: 20px; text-align: center;">加载失败</div>';
    }
}

function generateColors(count) {
    const colors = ['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#ffeaa7', '#dfe6e9', '#fd79a8', '#a29bfe', '#55efc4', '#81ecec'];
    return Array(count).fill(0).map((_, i) => colors[i % colors.length]);
}

function switchTab(tabName, clickedTab = null) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    if (clickedTab) {
        clickedTab.classList.add('active');
    } else {
        const tabs = document.querySelectorAll('.tab');
        tabs.forEach(tab => {
            if (tab.getAttribute('data-tab') === tabName) tab.classList.add('active');
        });
    }
    document.getElementById(`tab-${tabName}`).classList.add('active');
    if (tabName === 'tasks') loadTasks();
    if (tabName === 'stats') { 
        loadStats(); 
        setTimeout(loadDistributionData, 100);
    }
    if (tabName === 'export') loadExportTasks();
    if (tabName === 'monitor') { initProgressChart(); initWorkerChart(); }
    if (tabName === 'generators') loadGeneratorsForAdmin();
    if (tabName === 'providers') loadProviders();
}

document.addEventListener('DOMContentLoaded', async () => {
    console.log('Initializing Ai00 RWKV Data Generator...');

    if (typeof Chart !== 'undefined') {
        Chart.defaults.color = '#a0a0a0';
        Chart.defaults.borderColor = '#333';
        Chart.defaults.responsive = true;
        Chart.defaults.maintainAspectRatio = false;
        Chart.defaults.resizeDelay = 500;
    }

    await Promise.all([loadTopics(), loadGenerators()]);
    loadTasks();
    // connectWebSocket(); // Not implemented yet
    setInterval(loadTasks, 5000);
});
