let isCreatingTask = false;
let apiErrorCount = 0;
let lastTasksHash = '';

function validateLangRatios() {
    const langs = ['zh', 'en', 'ja', 'ko', 'de', 'fr', 'es', 'ru'];
    let total = 0;
    langs.forEach(lang => {
        total += parseInt(document.getElementById(`lang-${lang}`).value) || 0;
    });
    const el = document.getElementById('lang-ratio-total');
    el.textContent = `总计: ${total}%`;
    el.style.color = total === 100 ? 'var(--accent-green)' : 'var(--accent-red)';
    el.style.background = total === 100 ? 'rgba(0,255,136,0.1)' : 'rgba(255,68,68,0.1)';
    el.style.border = `1px solid ${total === 100 ? 'var(--accent-green)' : 'var(--accent-red)'}`;
    return total === 100;
}

async function checkTaskNameUnique() {
    const nameInput = document.getElementById('task-name');
    const errorDiv = document.getElementById('task-name-error');
    const name = nameInput.value.trim();
    if (!name) {
        errorDiv.style.display = 'none';
        nameInput.style.borderColor = '';
        return true;
    }
    const existingTask = window.tasks.find(t => t.name === name);
    if (existingTask) {
        errorDiv.textContent = `⚠️ 任务名称 "${name}" 已存在，请使用其他名称`;
        errorDiv.style.display = 'block';
        nameInput.style.borderColor = 'var(--accent-red)';
        return false;
    }
    errorDiv.style.display = 'none';
    nameInput.style.borderColor = '';
    return true;
}

function updateExistingTasksHint() {
    const hintDiv = document.getElementById('existing-tasks-hint');
    if (window.tasks.length > 0) {
        const names = window.tasks.slice(0, 5).map(t => t.name).join(', ');
        const more = window.tasks.length > 5 ? ` 等${window.tasks.length}个任务` : '';
        hintDiv.innerHTML = `<small>现有任务: ${names}${more}</small>`;
    } else {
        hintDiv.innerHTML = '';
    }
}

function getSelectedTopics() {
    const checkboxes = document.querySelectorAll('.topic-checkbox:checked');
    const selected = Array.from(checkboxes).map(cb => cb.value);
    return selected.length > 0 ? selected : null;
}

function renderTopicCheckboxes() {
    const container = document.getElementById('topic-checkboxes');
    if (!container) return;
    if (window.availableTopics.length === 0) {
        container.innerHTML = '<p style="color: #666;">暂无话题配置</p>';
        return;
    }
    container.innerHTML = window.availableTopics.map(topic => `
        <label style="display: flex; align-items: center; gap: 8px; padding: 8px; background: var(--bg-secondary); border-radius: 6px; cursor: pointer;">
            <input type="checkbox" class="topic-checkbox" value="${topic.key || topic.category}" checked
                style="width: 18px; height: 18px; accent-color: var(--accent-yellow);">
            <span style="font-size: 0.9rem;">${topic.category}</span>
        </label>
    `).join('');
}

function selectAllTopics() {
    document.querySelectorAll('.topic-checkbox').forEach(cb => cb.checked = true);
}

function deselectAllTopics() {
    document.querySelectorAll('.topic-checkbox').forEach(cb => cb.checked = false);
}

async function createTask() {
    if (isCreatingTask) return;
    const name = document.getElementById('task-name').value.trim();
    if (!name) {
        showAlert('请输入任务名称', 'error');
        return;
    }
    if (!await checkTaskNameUnique()) {
        showAlert('任务名称已存在，请使用其他名称', 'error');
        return;
    }
    if (!validateLangRatios()) {
        showAlert('语言比例总和必须等于100%', 'error');
        return;
    }
    isCreatingTask = true;
    try {
        const config = {
            name: document.getElementById('task-name').value || `Task_${Date.now()}`,
            generator_type: document.getElementById('generator-type').value,
            count: parseInt(document.getElementById('count').value),
            temperature: parseFloat(document.getElementById('temperature').value),
            concurrency: parseInt(document.getElementById('concurrency').value),
            api_key: document.getElementById('api-key').value || null,
            provider_id: document.getElementById('provider-id').value || null,
            lang_ratio_zh: parseInt(document.getElementById('lang-zh').value),
            lang_ratio_en: parseInt(document.getElementById('lang-en').value),
            lang_ratio_ja: parseInt(document.getElementById('lang-ja').value),
            lang_ratio_ko: parseInt(document.getElementById('lang-ko').value),
            lang_ratio_de: parseInt(document.getElementById('lang-de').value),
            lang_ratio_fr: parseInt(document.getElementById('lang-fr').value),
            lang_ratio_es: parseInt(document.getElementById('lang-es').value),
            lang_ratio_ru: parseInt(document.getElementById('lang-ru').value),
            selected_topics: getSelectedTopics(),
            custom_prompts: getCustomPrompts(),
        };
        console.log('Creating task...', config.name, 'Provider:', config.provider_id);
        const response = await createTaskAPI(config);
        if (response.id) {
            showAlert(`任务创建成功: ${response.id}`, 'success');
            addLog(`任务创建成功: ${response.name}`);
            switchTab('tasks');
        } else if (response.detail && response.detail.includes('already exists')) {
            showAlert('❌ 任务名称已存在', 'error');
            document.getElementById('task-name').style.borderColor = 'var(--accent-red)';
        } else {
            showAlert(response.detail || '创建失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    } finally {
        isCreatingTask = false;
    }
}

async function loadTasks() {
    try {
        window.tasks = await loadTasksAPI();
        apiErrorCount = 0;
        renderTasks();
        updateExistingTasksHint();
    } catch (e) {
        apiErrorCount++;
        if (apiErrorCount <= MAX_API_ERROR_DISPLAY) {
            const container = document.getElementById('task-list');
            if (container && window.tasks.length === 0) {
                container.innerHTML = '<p style="color: #ff4444; text-align: center;">无法连接到服务器，请检查后端是否运行</p>';
            }
        }
        console.error('Failed to load tasks:', e);
    }
}

function renderTasks() {
    const container = document.getElementById('task-list');
    if (!container) return;
    console.log('Rendering tasks:', window.tasks.length, 'tasks');
    console.log('Sample task:', JSON.stringify(window.tasks[0]));
    window.tasks.forEach(t => console.log('  -', t.id, t.name, t.status, t.generator_type));
    if (window.tasks.length === 0) {
        if (lastTasksHash !== 'empty') {
            container.innerHTML = '<p style="color: #888; text-align: center; padding: 40px;">暂无任务</p>';
            lastTasksHash = 'empty';
        }
        return;
    }
    const currentHash = window.tasks.map(t => `${t.id}:${t.status}:${t.progress}`).join('|');
    if (currentHash === lastTasksHash) return;
    lastTasksHash = currentHash;
    
    const typeNames = {
        'single_skill': '单技能对话',
        'single_skill_error': '单技能错误对话',
        'complex_skill': '多技能对话',
        'mixed_dialog': '混合对话',
        'no_tool': '闲聊对话',
    };
    
    const tasksByType = {};
    window.tasks.forEach(task => {
        const type = task.generator_type || 'other';
        if (!tasksByType[type]) tasksByType[type] = [];
        tasksByType[type].push(task);
    });
    
    const typeOrder = ['single_skill', 'single_skill_error', 'complex_skill', 'mixed_dialog', 'no_tool', 'other'];
    const sortedTypes = Object.keys(tasksByType).sort((a, b) => {
        const ai = typeOrder.indexOf(a);
        const bi = typeOrder.indexOf(b);
        return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });
    
    let html = '';
    for (const type of sortedTypes) {
        const tasks = tasksByType[type];
        html += `
            <div style="margin-bottom: 20px;">
                <h3 style="color: var(--text-primary); margin-bottom: 10px; padding-bottom: 5px; border-bottom: 1px solid var(--border-color);">
                    ${typeNames[type] || type} (${tasks.length})
                </h3>
        `;
        for (const task of tasks) {
            const progress = (task.progress / task.total * 100) || 0;
            const isRunning = task.status === 'running';
            const hasData = task.progress > 0;
            html += `
        <div class="task-item" id="task-${task.id}">
            <div class="task-header">
                <span class="task-name">${task.name}</span>
                <span class="task-status status-${task.status}">${task.status}</span>
            </div>
            <div class="progress-section">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progress}%"></div>
                </div>
                <div class="progress-text">${progress.toFixed(1)}% (${task.progress}/${task.total})</div>
            </div>
            <div class="task-actions">
                ${hasData ? `<button class="btn btn-small" onclick="viewTaskData('${task.id}')">查看数据</button>` : ''}
                ${task.status === 'completed' ? `<button class="btn btn-small" onclick="downloadTaskData('${task.id}')">下载</button>` : ''}
                ${isRunning ? `<button class="btn btn-small btn-danger" onclick="cancelTask('${task.id}')">停止</button>` : ''}
                ${task.status !== 'running' ? `<button class="btn btn-small btn-danger" onclick="deleteTask('${task.id}')">删除</button>` : ''}
            </div>
        </div>`;
        }
        html += '</div>';
    }
    container.innerHTML = html;
}

async function cancelTask(taskId) {
    if (!confirm('确定要停止这个任务吗？')) return;
    try {
        const result = await cancelTaskAPI(taskId);
        if (result.status === 'cancelled') {
            addLog(`任务已停止: ${taskId}`);
            showAlert('任务已停止', 'success');
            loadTasks();
        } else {
            showAlert('停止失败', 'error');
        }
    } catch (e) {
        showAlert('停止失败: ' + e.message, 'error');
    }
}

async function deleteTask(taskId) {
    if (!confirm('确定要删除这个任务吗？此操作不可恢复！')) return;
    try {
        const result = await deleteTaskAPI(taskId);
        if (result.status === 'deleted' || result.id) {
            addLog(`任务已删除: ${result.name || taskId}`);
            showAlert(`任务 "${result.name || taskId}" 已删除`, 'success');
            await new Promise(r => setTimeout(r, 500));
            await loadTasks();
        } else {
            showAlert('删除失败: ' + (result.detail || '未知错误'), 'error');
        }
    } catch (e) {
        showAlert('删除失败: ' + e.message, 'error');
    }
}

async function viewTaskData(taskId) {
    try {
        const result = await getTaskDataAPI(taskId, 50);
        if (!result.records) {
            showAlert('该任务暂无数据', 'info');
            return;
        }
        showDataModal(taskId, result.records, result.total);
    } catch (e) {
        console.error('View task data error:', e);
        showAlert('获取数据失败: ' + e.message, 'error');
    }
}

function downloadTaskData(taskId) {
    window.open(`${API_BASE}/api/tasks/${taskId}/download`, '_blank');
    addLog(`下载任务数据: ${taskId}`);
}

function getCustomPrompts() {
    const selectedId = document.getElementById('generator-type').value;
    const content = document.getElementById('custom-prompt-content').value.trim();
    if (content) return { [selectedId]: content };
    return null;
}

function toggleCustomPrompts() {
    const section = document.getElementById('custom-prompts-section');
    const toggle = document.getElementById('custom-prompts-toggle');
    if (section.style.display === 'none') {
        section.style.display = 'block';
        toggle.textContent = '📋 生成器模板 ▼';
    } else {
        section.style.display = 'none';
        toggle.textContent = '📋 生成器模板 ▶';
    }
}

async function applyDefaultPrompts() {
    const selectedId = document.getElementById('generator-type').value;
    await loadGeneratorTemplate(selectedId);
    showAlert('已加载生成器默认模板', 'success');
}

function clearCustomPrompts() {
    const input = document.getElementById('custom-prompt-content');
    if (input) input.value = '';
    showAlert('已清空自定义模板', 'success');
}

function resetForm() {
    document.getElementById('task-name').value = '';
    document.getElementById('count').value = '100';
    document.getElementById('temperature').value = '0.7';
    document.getElementById('temp-value').textContent = '0.7';
    document.getElementById('generator-type').value = 'no_tool';
    onGeneratorTypeChange();
    validateLangRatios();
}

function renderGeneratorOptions() {
    const selector = document.getElementById('generator-type');
    if (!selector) return;
    selector.innerHTML = window.availableGenerators.map(gen =>
        `<option value="${gen.id}">${gen.name}</option>`
    ).join('');
    onGeneratorTypeChange();
}

async function onGeneratorTypeChange() {
    const selector = document.getElementById('generator-type');
    const descEl = document.getElementById('generator-description');
    const labelEl = document.getElementById('current-generator-label');
    if (!selector || !descEl || !labelEl) return;
    const selectedId = selector.value;
    const generator = window.availableGenerators.find(g => g.id === selectedId);
    if (generator) {
        descEl.textContent = generator.description || '';
        labelEl.textContent = `- ${generator.name}`;
    }
    const input = document.getElementById('custom-prompt-content');
    if (input && !input.value.trim()) {
        await loadGeneratorTemplate(selectedId);
    }
}
