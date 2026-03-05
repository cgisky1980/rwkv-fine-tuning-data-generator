async function loadTopics() {
    const container = document.getElementById('topic-checkboxes');
    if (!container) {
        console.log('topic-checkboxes element not found');
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/api/config/topics`);
        if (!response.ok) {
            container.innerHTML = `<p style="color: var(--accent-red);">加载失败: HTTP ${response.status}</p>`;
            return;
        }
        const data = await response.json();
        window.availableTopics = data.topics || [];
        console.log('Loaded topics:', window.availableTopics.length);
        renderTopicCheckboxes();
    } catch (e) {
        console.error('Failed to load topics:', e);
        container.innerHTML = `<p style="color: var(--accent-red);">加载失败: ${e.message}</p>`;
    }
}

async function loadGenerators() {
    try {
        const response = await fetch(`${API_BASE}/api/config/generators`);
        if (response.ok) {
            const data = await response.json();
            window.availableGenerators = data.generators || [];
            renderGeneratorOptions();
        }
    } catch (e) {
        console.error('Failed to load generators:', e);
        window.availableGenerators = [
            { id: 'no_tool', name: '无工具对话', description: '生成纯对话数据，无需工具调用' },
        ];
        renderGeneratorOptions();
    }
}

async function loadGeneratorTemplate(generatorId) {
    try {
        const response = await fetch(`${API_BASE}/api/config/generators/${generatorId}/template`);
        if (response.ok) {
            const data = await response.json();
            const input = document.getElementById('custom-prompt-content');
            if (input) input.value = data.content || '';
            const label = document.getElementById('current-generator-label');
            if (label && data.name) label.textContent = `- ${data.name}`;
        }
    } catch (e) {
        console.error('Failed to load generator template:', e);
    }
}

async function createTaskAPI(config) {
    const response = await fetch(`${API_BASE}/api/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    });
    return response.json();
}

async function loadTasksAPI() {
    const response = await fetch(`${API_BASE}/api/tasks`, {
        signal: AbortSignal.timeout(5000)
    });
    const data = await response.json();
    console.log('API Response tasks:', JSON.stringify(data[0]));
    return data;
}

async function cancelTaskAPI(taskId) {
    const response = await fetch(`${API_BASE}/api/tasks/${taskId}/cancel`, { method: 'POST' });
    return response.json();
}

async function deleteTaskAPI(taskId) {
    const response = await fetch(`${API_BASE}/api/tasks/${taskId}`, { method: 'DELETE' });
    return response.json();
}

async function getTaskDataAPI(taskId, limit = 50) {
    const response = await fetch(`${API_BASE}/api/tasks/${taskId}/data?limit=${limit}`);
    return response.json();
}

async function exportRWKVAPI(config) {
    const response = await fetch(`${API_BASE}/api/export/rwkv`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    });
    return response.json();
}

async function previewExportAPI(config) {
    config._t = Date.now();
    const response = await fetch(`${API_BASE}/api/export/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    });
    return response.json();
}

async function loadGeneratorsForAdminAPI() {
    const response = await fetch(`${API_BASE}/api/admin/generators`);
    return response.json();
}

async function getGeneratorAPI(generatorId) {
    const response = await fetch(`${API_BASE}/api/admin/generators/${generatorId}`);
    return response.json();
}

async function saveGeneratorAPI(generatorId, data) {
    const response = await fetch(`${API_BASE}/api/admin/generators/${generatorId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    return response.json();
}

async function saveGeneratorTemplateAPI(generatorId, content) {
    const response = await fetch(`${API_BASE}/api/admin/generators/${generatorId}/template`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
    });
    return response.json();
}

async function toggleGeneratorAPI(generatorId, enabled) {
    const response = await fetch(`${API_BASE}/api/admin/generators/${generatorId}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled })
    });
    return response.json();
}

async function deleteGeneratorAPI(generatorId) {
    const response = await fetch(`${API_BASE}/api/admin/generators/${generatorId}`, { method: 'DELETE' });
    return response.json();
}

async function createGeneratorAPI(data) {
    const response = await fetch(`${API_BASE}/api/admin/generators`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    return response.json();
}

async function testGeneratorTemplateAPI(templateContent, callApi = false) {
    const body = { template_content: templateContent };
    if (callApi) body.call_api = true;
    
    const response = await fetch(`${API_BASE}/api/admin/generators/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    return response.json();
}

async function submitNewTopicAPI(category, description) {
    const response = await fetch(`${API_BASE}/api/config/topics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, description, levels: {} })
    });
    return response.json();
}

// LLM Provider API functions
async function loadProvidersAPI() {
    const response = await fetch(`${API_BASE}/api/config/providers`);
    return response.json();
}

async function loadProviderTemplatesAPI() {
    const response = await fetch(`${API_BASE}/api/config/providers/templates`);
    return response.json();
}

async function saveProviderAPI(data) {
    const response = await fetch(`${API_BASE}/api/config/providers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    return response.json();
}

async function deleteProviderAPI(providerId) {
    const response = await fetch(`${API_BASE}/api/config/providers/${providerId}`, {
        method: 'DELETE'
    });
    return response.json();
}

async function setDefaultProviderAPI(providerId) {
    const response = await fetch(`${API_BASE}/api/config/providers/${providerId}/set-default`, {
        method: 'POST'
    });
    return response.json();
}

async function testProviderAPI(providerId) {
    const response = await fetch(`${API_BASE}/api/config/providers/${providerId}/test`, {
        method: 'POST'
    });
    return response.json();
}
