window.providersList = [];
window.providerTemplates = {};
window.selectedProvider = null;

async function loadProviders() {
    try {
        const data = await loadProvidersAPI();
        window.providersList = data.providers || [];
        window.providerTemplates = data.templates || {};
        renderProvidersList();
        updateProviderSelect();
    } catch (e) {
        console.error('Failed to load providers:', e);
        document.getElementById('providers-list').innerHTML = '<p style="color: var(--accent-red);">加载失败</p>';
    }
}

function renderProvidersList() {
    const container = document.getElementById('providers-list');
    if (!container) return;

    if (window.providersList.length === 0) {
        container.innerHTML = `
            <p style="color: #888; text-align: center; padding: 20px;">暂无配置的服务商</p>
            <p style="color: #666; font-size: 0.85rem; text-align: center; margin-top: 10px;">
                点击下方「新增服务商」添加配置<br>
                支持 OpenRouter、DeepSeek、OpenAI、Azure、Anthropic、Ollama 等
            </p>
        `;
        return;
    }

    container.innerHTML = window.providersList.map(p => `
        <div class="provider-item" onclick="selectProvider('${p.id}')"
             style="padding: 15px; background: var(--bg-secondary); border-radius: 8px; margin-bottom: 10px;
                    cursor: pointer; border: 2px solid ${window.selectedProvider === p.id ? 'var(--accent-yellow)' : 'transparent'};
                    transition: all 0.3s;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-weight: 600; color: ${p.is_default ? 'var(--accent-yellow)' : 'var(--text-primary)'};">
                        ${p.name} ${p.is_default ? '⭐ 默认' : ''}
                    </div>
                    <div style="font-size: 0.85rem; color: #888; margin-top: 4px;">
                        ${p.provider_type} · ${p.model}
                    </div>
                </div>
                <div style="display: flex; gap: 8px;">
                    ${p.has_api_key ? '<span style="color: var(--accent-green);">✓ 已配置</span>' : '<span style="color: var(--accent-red);">✗ 未配置</span>'}
                    ${p.is_active ? '<span style="color: var(--accent-green);">启用</span>' : '<span style="color: #666;">禁用</span>'}
                </div>
            </div>
        </div>
    `).join('');
}

function selectProvider(providerId) {
    window.selectedProvider = providerId;
    const provider = window.providersList.find(p => p.id === providerId);
    if (provider) {
        renderProviderEditor(provider);
    }
    renderProvidersList();
}

async function renderProviderEditor(provider) {
    const container = document.getElementById('provider-editor-container');
    if (!container) return;

    container.innerHTML = `
        <div class="form-group">
            <label>服务商名称</label>
            <input type="text" id="provider-name" value="${provider.name || ''}" placeholder="例如：OpenRouter">
        </div>
        <div class="form-group">
            <label>服务商类型</label>
            <select id="provider-type" onchange="onProviderTypeChange()">
                ${Object.entries(window.providerTemplates).map(([key, tpl]) =>
                    `<option value="${key}" ${provider.provider_type === key || provider.provider_type === tpl.provider_type ? 'selected' : ''}>${tpl.name}</option>`
                ).join('')}
                <option value="custom" ${!window.providerTemplates[provider.provider_type] ? 'selected' : ''}>自定义</option>
            </select>
        </div>
        <div class="form-group">
            <label>API Base URL</label>
            <input type="text" id="provider-base-url" value="${provider.base_url || ''}" placeholder="https://api.example.com/v1">
        </div>
        <div class="form-group">
            <label>API Key</label>
            <input type="password" id="provider-api-key" value="" placeholder="${provider.has_api_key ? '已配置，点击重新填写' : '输入 API Key'}">
        </div>
        <div class="form-group">
            <label>模型</label>
            <input type="text" id="provider-model" value="${provider.model || ''}" placeholder="例如：gpt-4o">
        </div>
        <div class="form-group">
            <label>可用模型列表 (可选, 逗号分隔)</label>
            <input type="text" id="provider-models" value="${(provider.models || []).join(', ')}" placeholder="gpt-4o, gpt-4o-mini, claude-3-5-sonnet">
        </div>
        <div class="form-group">
            <label>最大 Token 数</label>
            <input type="number" id="provider-max-tokens" value="${provider.max_tokens || 4096}" min="1" max="100000">
        </div>
        <div style="display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap;">
            <button class="btn btn-primary" onclick="saveProvider()">💾 保存配置</button>
            ${provider.is_default ?
                '<button class="btn btn-secondary" onclick="setAsDefault(\'' + provider.id + '\')" disabled>⭐ 默认服务商</button>' :
                '<button class="btn btn-secondary" onclick="setAsDefault(\'' + provider.id + '\')">⭐ 设为默认</button>'
            }
            <button class="btn btn-secondary" onclick="testProvider('${provider.id}')">🧪 测试连接</button>
            <button class="btn btn-secondary" style="background: var(--accent-red); color: white;"
                    onclick="deleteProvider('${provider.id}')">🗑️ 删除</button>
        </div>
        <div id="provider-test-result" style="margin-top: 15px;"></div>
    `;
}

function onProviderTypeChange() {
    const type = document.getElementById('provider-type').value;
    if (window.providerTemplates[type]) {
        const tpl = window.providerTemplates[type];
        document.getElementById('provider-base-url').value = tpl.base_url || '';
        document.getElementById('provider-model').value = tpl.models && tpl.models.length > 0 ? tpl.models[0] : '';
        document.getElementById('provider-models').value = (tpl.models || []).join(', ');
        document.getElementById('provider-max-tokens').value = tpl.max_tokens || 4096;
    }
}

async function saveProvider() {
    const id = window.selectedProvider;
    const name = document.getElementById('provider-name').value.trim();
    const providerType = document.getElementById('provider-type').value;
    const baseUrl = document.getElementById('provider-base-url').value.trim();
    const apiKey = document.getElementById('provider-api-key').value.trim();
    const model = document.getElementById('provider-model').value.trim();
    const modelsStr = document.getElementById('provider-models').value.trim();
    const maxTokens = parseInt(document.getElementById('provider-max-tokens').value) || 4096;

    if (!name) {
        showAlert('请输入服务商名称', 'error');
        return;
    }
    if (!baseUrl) {
        showAlert('请输入 API Base URL', 'error');
        return;
    }
    if (!apiKey) {
        showAlert('请输入 API Key', 'error');
        return;
    }
    if (!model) {
        showAlert('请输入模型名称', 'error');
        return;
    }

    const models = modelsStr ? modelsStr.split(',').map(m => m.trim()).filter(m => m) : null;

    const data = {
        id: id || `provider_${Date.now()}`,
        name: name,
        provider_type: providerType,
        base_url: baseUrl,
        api_key: apiKey,
        model: model,
        models: models,
        max_tokens: maxTokens,
        is_default: window.providersList.find(p => p.id === id)?.is_default || false,
        is_active: true,
    };

    try {
        const result = await saveProviderAPI(data);
        if (result.success) {
            showAlert(result.message, 'success');
            window.selectedProvider = null;
            await loadProviders();
        } else {
            showAlert(result.detail || '保存失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

async function deleteProvider(providerId) {
    if (!confirm(`确定要删除这个服务商配置吗？`)) return;

    try {
        const result = await deleteProviderAPI(providerId);
        if (result.success) {
            showAlert(result.message, 'success');
            window.selectedProvider = null;
            await loadProviders();
            document.getElementById('provider-editor-container').innerHTML =
                '<p style="color: #888; text-align: center; padding: 40px;">从左侧选择一个服务商进行配置</p>';
        } else {
            showAlert(result.detail || '删除失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

async function setAsDefault(providerId) {
    try {
        const result = await setDefaultProviderAPI(providerId);
        if (result.success) {
            showAlert(result.message, 'success');
            await loadProviders();
            if (window.selectedProvider) {
                selectProvider(window.selectedProvider);
            }
        } else {
            showAlert(result.detail || '设置失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

async function testProvider(providerId) {
    const resultDiv = document.getElementById('provider-test-result');
    resultDiv.innerHTML = '<p style="color: var(--accent-yellow);">测试中...</p>';

    try {
        const result = await testProviderAPI(providerId);
        if (result.success) {
            resultDiv.innerHTML = `<div class="alert alert-success">✅ ${result.message}<br><small>${result.test_result}</small></div>`;
        } else {
            resultDiv.innerHTML = `<div class="alert alert-error">❌ ${result.message}</div>`;
        }
    } catch (e) {
        resultDiv.innerHTML = `<div class="alert alert-error">网络错误: ${e.message}</div>`;
    }
}

function openAddProviderModal() {
    window.selectedProvider = null;
    const container = document.getElementById('provider-editor-container');
    container.innerHTML = `
        <div class="form-group">
            <label>服务商名称</label>
            <input type="text" id="provider-name" placeholder="例如：OpenRouter">
        </div>
        <div class="form-group">
            <label>服务商类型</label>
            <select id="provider-type" onchange="onProviderTypeChange()">
                <option value="">-- 选择类型 --</option>
                ${Object.entries(window.providerTemplates).map(([key, tpl]) =>
                    `<option value="${key}">${tpl.name}</option>`
                ).join('')}
                <option value="custom">自定义</option>
            </select>
        </div>
        <div class="form-group">
            <label>API Base URL</label>
            <input type="text" id="provider-base-url" placeholder="https://api.example.com/v1">
        </div>
        <div class="form-group">
            <label>API Key</label>
            <input type="password" id="provider-api-key" placeholder="输入 API Key">
        </div>
        <div class="form-group">
            <label>模型</label>
            <input type="text" id="provider-model" placeholder="例如：gpt-4o">
        </div>
        <div class="form-group">
            <label>可用模型列表 (可选, 逗号分隔)</label>
            <input type="text" id="provider-models" placeholder="gpt-4o, gpt-4o-mini, claude-3-5-sonnet">
        </div>
        <div class="form-group">
            <label>最大 Token 数</label>
            <input type="number" id="provider-max-tokens" value="4096" min="1" max="100000">
        </div>
        <div style="display: flex; gap: 10px; margin-top: 20px;">
            <button class="btn btn-primary" onclick="saveProvider()">💾 保存配置</button>
        </div>
        <div id="provider-test-result" style="margin-top: 15px;"></div>
    `;
}

function updateProviderSelect() {
    const select = document.getElementById('provider-id');
    if (!select) return;

    const defaultProvider = window.providersList.find(p => p.is_default);
    let html = '<option value="">-- 使用API Key 或默认 --</option>';
    window.providersList.filter(p => p.is_active).forEach(p => {
        html += `<option value="${p.id}">${p.name} ${p.is_default ? '(默认)' : ''}</option>`;
    });
    select.innerHTML = html;
}

function onProviderChange() {
    const providerId = document.getElementById('provider-id').value;
    const apiKeyInput = document.getElementById('api-key');

    if (providerId) {
        apiKeyInput.placeholder = '使用服务商配置，无需输入 API Key';
        apiKeyInput.value = '';
    } else {
        apiKeyInput.placeholder = '默认使用 sk-test';
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadProviders();
});
