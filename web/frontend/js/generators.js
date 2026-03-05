let currentGeneratorId = null;
let generatorsList = [];

async function loadGeneratorsForAdmin() {
    const container = document.getElementById('generators-list');
    if (!container) return;
    try {
        const data = await loadGeneratorsForAdminAPI();
        if (data.generators) {
            generatorsList = data.generators;
            renderGeneratorsList();
        } else {
            container.innerHTML = '<p style="color: var(--accent-red);">加载失败</p>';
        }
    } catch (e) {
        console.error('Failed to load generators:', e);
        container.innerHTML = '<p style="color: var(--accent-red);">加载失败: ' + e.message + '</p>';
    }
}

function renderGeneratorsList() {
    const container = document.getElementById('generators-list');
    if (!container) return;
    if (generatorsList.length === 0) {
        container.innerHTML = '<p style="color: #666;">暂无生成器</p>';
        return;
    }
    container.innerHTML = generatorsList.map(gen => `
        <div class="export-task-item" onclick="editGenerator('${gen.id}')" style="cursor: pointer; display: flex; align-items: center; justify-content: space-between;">
            <div>
                <div style="font-weight: 600; color: var(--accent-yellow);">${gen.name}</div>
                <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 4px;">${gen.description || '无描述'}</div>
                <div style="font-size: 0.75rem; color: #666; margin-top: 4px;">ID: ${gen.id} | 工具数: ${gen.tools_count}</div>
            </div>
            <div style="display: flex; align-items: center; gap: 10px;">
                <span class="task-status ${gen.enabled ? 'status-completed' : 'status-cancelled'}">${gen.enabled ? '启用' : '禁用'}</span>
                ${gen.default ? '<span style="color: var(--accent-yellow); font-size: 0.8rem;">默认</span>' : ''}
            </div>
        </div>
    `).join('');
}

async function editGenerator(generatorId) {
    currentGeneratorId = generatorId;
    const container = document.getElementById('generator-editor-container');
    container.innerHTML = '<p style="color: #666;">加载中...</p>';
    try {
        const gen = await getGeneratorAPI(generatorId);
        if (gen.id) {
            renderGeneratorEditor(gen);
        } else {
            container.innerHTML = '<p style="color: var(--accent-red);">加载失败</p>';
        }
    } catch (e) {
        console.error('Failed to load generator:', e);
        container.innerHTML = '<p style="color: var(--accent-red);">加载失败: ' + e.message + '</p>';
    }
}

function renderGeneratorEditor(gen) {
    const container = document.getElementById('generator-editor-container');
    const title = document.getElementById('generator-editor-title');
    title.textContent = `✏️ 编辑生成器 - ${gen.name}`;
    const showTools = gen.parameters?.require_tools || (gen.tools && gen.tools.length > 0);
    // 清理后端追加的 output_schema 部分
    const cleanTemplateContent = (gen.template_content || '').replace(/## 输出格式要求\s*```json\s*\{[\s\S]*?```\s*$/, '').trim();
    container.innerHTML = `
        <div class="grid" style="grid-template-columns: repeat(2, 1fr); gap: 20px;">
            <div class="form-group">
                <label>ID</label>
                <input type="text" id="gen-id" value="${gen.id}" disabled style="background: var(--bg-secondary); color: var(--text-secondary);">
            </div>
            <div class="form-group">
                <label>名称</label>
                <input type="text" id="gen-name" value="${gen.name || ''}">
            </div>
            <div class="form-group" style="grid-column: span 2;">
                <label>描述</label>
                <input type="text" id="gen-description" value="${gen.description || ''}">
            </div>
            <div class="form-group">
                <label><input type="checkbox" id="gen-enabled" ${gen.enabled ? 'checked' : ''} style="width: auto; margin-right: 8px;">启用</label>
            </div>
            <div class="form-group">
                <label><input type="checkbox" id="gen-tools-required" ${gen.parameters?.require_tools ? 'checked' : ''} style="width: auto; margin-right: 8px;" onchange="toggleToolsSection()">需要工具</label>
            </div>
        </div>
        <div class="form-group" style="margin-top: 20px;">
            <label>模板内容</label>
            <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 8px;">
                可用变量:
                <code style="color: var(--accent-green);">{topic}</code>
                <code style="color: var(--accent-green);">{persona_name}</code>
                <code style="color: var(--accent-green);">{persona_tone}</code>
                <code style="color: var(--accent-green);">{persona_json}</code>
                <code style="color: var(--accent-green);">{user_profile}</code>
                <code style="color: var(--accent-green);">{turn_count}</code>
                <code style="color: var(--accent-green);">{language}</code>
                <code style="color: var(--accent-green);">{id}</code>
                <code style="color: var(--accent-green);">{datetime}</code>
                <code style="color: var(--accent-green);">{weekday}</code>
            </div>
            <textarea id="gen-template-content" rows="20" style="width: 100%; padding: 12px; border: 2px solid var(--border-color); border-radius: 8px; background: var(--bg-secondary); color: var(--text-primary); font-family: 'Consolas', 'Monaco', monospace; font-size: 0.85rem;">${cleanTemplateContent}</textarea>
        </div>
        <div id="gen-tools-section" class="form-group" style="margin-top: 20px; ${showTools ? '' : 'display: none;'}">
            <label>工具定义 (JSON)</label>
            <textarea id="gen-tools" rows="10" style="width: 100%; padding: 12px; border: 2px solid var(--border-color); border-radius: 8px; background: var(--bg-secondary); color: var(--text-primary); font-family: 'Consolas', 'Monaco', monospace; font-size: 0.85rem;">${JSON.stringify(gen.tools || [], null, 2)}</textarea>
        </div>
        <div class="form-group" style="margin-top: 20px;">
            <label>输出格式 (output_schema JSON)</label>
            <textarea id="gen-output-schema" rows="8" style="width: 100%; padding: 12px; border: 2px solid var(--border-color); border-radius: 8px; background: var(--bg-secondary); color: var(--text-primary); font-family: 'Consolas', 'Monaco', monospace; font-size: 0.85rem;">${JSON.stringify(gen.output_schema || {}, null, 2)}</textarea>
        </div>
        <div style="display: flex; gap: 10px; margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-color);">
            <button class="btn" onclick="saveGenerator()">💾 保存</button>
            <button class="btn btn-secondary" onclick="saveGeneratorTemplate()">💾 仅保存模板</button>
            <button class="btn btn-secondary" onclick="previewTemplate()">👁️ 渲染预览</button>
            <button class="btn btn-secondary" onclick="testGeneratorAPI()">🤖 API 测试</button>
            ${!gen.default ? `<button class="btn btn-secondary" onclick="toggleGeneratorEnabled('${gen.id}', ${!gen.enabled})">${gen.enabled ? '禁用' : '启用'}</button>` : ''}
            ${!gen.default ? `<button class="btn btn-secondary" onclick="deleteGenerator('${gen.id}')">🗑️ 删除</button>` : ''}
        </div>
    `;
}

function toggleToolsSection() {
    const section = document.getElementById('gen-tools-section');
    const checkbox = document.getElementById('gen-tools-required');
    if (section && checkbox) section.style.display = checkbox.checked ? 'block' : 'none';
}

async function saveGenerator() {
    if (!currentGeneratorId) return;
    const name = document.getElementById('gen-name').value.trim();
    const description = document.getElementById('gen-description').value.trim();
    const enabled = document.getElementById('gen-enabled').checked;
    const requireTools = document.getElementById('gen-tools-required').checked;
    const toolsJson = document.getElementById('gen-tools').value;
    const templateContent = document.getElementById('gen-template-content').value;
    if (!name) { showAlert('请输入名称', 'error'); return; }
    try {
        let tools = [];
        if (requireTools) {
            try { tools = JSON.parse(toolsJson || '[]'); } catch (e) { showAlert('工具定义 JSON 格式错误', 'error'); return; }
        }
        const response = await saveGeneratorAPI(currentGeneratorId, { name, description, enabled, tools: requireTools ? tools : [] });
        if (response.id || response.status === 'ok') {
            await saveGeneratorTemplateAPI(currentGeneratorId, templateContent);
            showAlert('生成器保存成功', 'success');
            loadGeneratorsForAdmin();
        } else {
            showAlert(response.detail || '保存失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

async function saveGeneratorTemplate() {
    if (!currentGeneratorId) return;
    let templateContent = document.getElementById('gen-template-content').value;
    // 清理后端自动追加的 output_schema 部分
    templateContent = templateContent.replace(/## 输出格式要求\s*```json\s*\{[\s\S]*?```\s*$/, '').trim();
    try {
        const result = await saveGeneratorTemplateAPI(currentGeneratorId, templateContent);
        if (result.success || result.status === 'ok') showAlert('模板保存成功', 'success');
        else showAlert(result.detail || result.message || '保存失败', 'error');
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

async function saveGenerator() {
    if (!currentGeneratorId) return;
    const name = document.getElementById('gen-name').value.trim();
    const description = document.getElementById('gen-description').value.trim();
    const enabled = document.getElementById('gen-enabled').checked;
    const requireTools = document.getElementById('gen-tools-required').checked;
    const toolsJson = document.getElementById('gen-tools').value;
    const outputSchemaJson = document.getElementById('gen-output-schema').value;
    let templateContent = document.getElementById('gen-template-content').value;
    // 清理后端自动追加的 output_schema 部分
    templateContent = templateContent.replace(/## 输出格式要求\s*```json\s*\{[\s\S]*?```\s*$/, '').trim();
    if (!name) { showAlert('请输入名称', 'error'); return; }
    try {
        let tools = [];
        if (requireTools) {
            try { tools = JSON.parse(toolsJson || '[]'); } catch (e) { showAlert('工具定义 JSON 格式错误', 'error'); return; }
        }
        let outputSchema = {};
        try { outputSchema = JSON.parse(outputSchemaJson || '{}'); } catch (e) { showAlert('输出格式 JSON 格式错误', 'error'); return; }
        const response = await saveGeneratorAPI(currentGeneratorId, { name, description, enabled, tools: requireTools ? tools : [], output_schema: outputSchema });
        if (response.success || response.id || response.status === 'ok') {
            await saveGeneratorTemplateAPI(currentGeneratorId, templateContent);
            showAlert('生成器保存成功', 'success');
            loadGeneratorsForAdmin();
        } else {
            showAlert(response.detail || response.message || '保存失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

async function toggleGeneratorEnabled(generatorId, enabled) {
    try {
        const result = await toggleGeneratorAPI(generatorId, enabled);
        if (result.status === 'ok') {
            showAlert(enabled ? '生成器已启用' : '生成器已禁用', 'success');
            loadGeneratorsForAdmin();
            if (currentGeneratorId === generatorId) editGenerator(generatorId);
        } else {
            showAlert(result.detail || '操作失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

async function deleteGenerator(generatorId) {
    if (!confirm(`确定要删除生成器 "${generatorId}" 吗？此操作不可恢复！`)) return;
    try {
        const result = await deleteGeneratorAPI(generatorId);
        if (result.status === 'deleted' || result.id) {
            showAlert('生成器已删除', 'success');
            currentGeneratorId = null;
            document.getElementById('generator-editor-container').innerHTML = '<p style="color: #888; text-align: center; padding: 40px;">从左侧选择一个生成器进行编辑</p>';
            loadGeneratorsForAdmin();
        } else {
            showAlert(result.detail || '删除失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

function openCreateGeneratorModal() {
    document.getElementById('create-generator-modal').style.display = 'flex';
}

function closeCreateGeneratorModal() {
    document.getElementById('create-generator-modal').style.display = 'none';
}

async function createGenerator() {
    const id = document.getElementById('new-gen-id').value.trim().toLowerCase();
    const name = document.getElementById('new-gen-name').value.trim();
    const description = document.getElementById('new-gen-description').value.trim();
    const templateContent = document.getElementById('new-gen-template').value;
    if (!id || !name) { showAlert('请填写 ID 和名称', 'error'); return; }
    if (!/^[a-z][a-z0-9_]*$/.test(id)) { showAlert('ID 必须以小写字母开头，只能包含小写字母、数字和下划线', 'error'); return; }
    try {
        const result = await createGeneratorAPI({ id, name, description, content: templateContent, tools: [], persona_enabled: true, user_profile_enabled: true, tts_enabled: true, topic_enabled: true });
        if (result.id) {
            showAlert('生成器创建成功', 'success');
            closeCreateGeneratorModal();
            loadGeneratorsForAdmin();
            document.getElementById('new-gen-id').value = '';
            document.getElementById('new-gen-name').value = '';
            document.getElementById('new-gen-description').value = '';
            document.getElementById('new-gen-template').value = '';
        } else {
            showAlert(result.detail || '创建失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

async function previewTemplate() {
    if (!currentGeneratorId) {
        console.log('previewTemplate: no currentGeneratorId');
        return;
    }
    const templateContent = document.getElementById('gen-template-content').value;
    console.log('previewTemplate: calling API with template length', templateContent.length);
    const btn = document.querySelector('button[onclick="previewTemplate()"]');
    if (btn) { btn.textContent = '👁️ 预览中...'; btn.disabled = true; }
    try {
        const data = await testGeneratorTemplateAPI(templateContent);
        console.log('previewTemplate: received data', data);
        if (data.success) {
            const modal = document.createElement('div');
            modal.id = 'test-result-modal';
            modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 1001; display: flex; justify-content: center; align-items: center;';
            modal.innerHTML = `
                <div class="modal-content" style="background: var(--bg-card); border-radius: 16px; padding: 30px; max-width: 900px; width: 90%; max-height: 85vh; overflow-y: auto; border: 1px solid var(--border-color);">
                    <div class="card-title" style="margin-bottom: 20px;">
                        👁️ 模板渲染预览
                        <button onclick="document.getElementById('test-result-modal').remove()" style="float: right; background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 1.2rem;">✕</button>
                    </div>
                    <div style="margin-bottom: 20px;">
                        <div style="font-weight: 600; color: var(--accent-green); margin-bottom: 10px;">📋 渲染后的提示词:</div>
                        <pre style="font-size: 0.8rem; color: var(--text-primary); background: var(--bg-secondary); padding: 10px; border-radius: 8px; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">${data.rendered}</pre>
                    </div>
                    <div style="margin-bottom: 20px;">
                        <div style="font-weight: 600; color: var(--accent-yellow); margin-bottom: 10px;">🔧 使用的变量值:</div>
                        <pre style="font-size: 0.8rem; color: var(--text-secondary); background: var(--bg-secondary); padding: 10px; border-radius: 8px; overflow-x: auto;">${JSON.stringify(data.sample_variables, null, 2)}</pre>
                    </div>
                    <div style="margin-top: 20px; text-align: center;">
                        <button class="btn" onclick="document.getElementById('test-result-modal').remove()">关闭</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        } else {
            showAlert('错误: ' + (data.error_message || data.detail || '未知错误'), 'error');
        }
    } catch (e) {
        console.error('previewTemplate error:', e);
        showAlert('网络错误: ' + e.message, 'error');
    } finally {
        if (btn) { btn.textContent = '👁️ 渲染预览'; btn.disabled = false; }
    }
}

async function testGeneratorAPI() {
    if (!currentGeneratorId) return;
    const templateContent = document.getElementById('gen-template-content').value;
    const btn = document.querySelector('button[onclick="testGeneratorAPI()"]');
    if (btn) { btn.textContent = '🤖 调用中...'; btn.disabled = true; }
    try {
        const data = await testGeneratorTemplateAPI(templateContent, true);
        if (data.success) {
            const modal = document.createElement('div');
            modal.id = 'test-result-modal';
            modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 1001; display: flex; justify-content: center; align-items: center;';
            
            let apiResultHtml = '';
            if (data.generated_data) {
                apiResultHtml = `
                    <div style="margin-bottom: 20px;">
                        <div style="font-weight: 600; color: var(--accent-blue); margin-bottom: 10px;">✅ AI 生成的对话数据:</div>
                        <pre style="font-size: 0.8rem; color: var(--text-primary); background: var(--bg-secondary); padding: 10px; border-radius: 8px; white-space: pre-wrap; max-height: 400px; overflow-y: auto; border: 2px solid var(--accent-blue);">${JSON.stringify(data.generated_data, null, 2)}</pre>
                    </div>
                `;
            } else if (data.raw_response) {
                apiResultHtml = `
                    <div style="margin-bottom: 20px;">
                        <div style="font-weight: 600; color: var(--accent-orange); margin-bottom: 10px;">⚠️ 原始响应 (JSON 解析失败):</div>
                        <pre style="font-size: 0.8rem; color: var(--text-primary); background: var(--bg-secondary); padding: 10px; border-radius: 8px; white-space: pre-wrap; max-height: 300px; overflow-y: auto; border: 2px solid var(--accent-orange);">${data.raw_response}</pre>
                        ${data.parse_error ? `<div style="color: var(--accent-red); margin-top: 5px;">错误: ${data.parse_error}</div>` : ''}
                    </div>
                `;
            } else if (data.api_error) {
                apiResultHtml = `
                    <div style="margin-bottom: 20px;">
                        <div style="font-weight: 600; color: var(--accent-red); margin-bottom: 10px;">❌ API 调用失败:</div>
                        <div style="color: var(--accent-red);">${data.api_error}</div>
                    </div>
                `;
            } else if (data.api_skipped) {
                apiResultHtml = `
                    <div style="margin-bottom: 20px;">
                        <div style="font-weight: 600; color: var(--text-secondary); margin-bottom: 10px;">ℹ️ ${data.api_skipped}</div>
                    </div>
                `;
            }
            
            modal.innerHTML = `
                <div class="modal-content" style="background: var(--bg-card); border-radius: 16px; padding: 30px; max-width: 900px; width: 90%; max-height: 85vh; overflow-y: auto; border: 1px solid var(--border-color);">
                    <div class="card-title" style="margin-bottom: 20px;">
                        🤖 API 测试结果
                        <button onclick="document.getElementById('test-result-modal').remove()" style="float: right; background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 1.2rem;">✕</button>
                    </div>
                    ${apiResultHtml}
                    <div style="margin-bottom: 20px;">
                        <div style="font-weight: 600; color: var(--accent-green); margin-bottom: 10px;">📋 使用的提示词:</div>
                        <details>
                            <summary style="cursor: pointer; color: var(--text-secondary);">点击展开查看</summary>
                            <pre style="font-size: 0.8rem; color: var(--text-primary); background: var(--bg-secondary); padding: 10px; border-radius: 8px; white-space: pre-wrap; max-height: 300px; overflow-y: auto; margin-top: 10px;">${data.rendered}</pre>
                        </details>
                    </div>
                    <div style="margin-top: 20px; text-align: center;">
                        <button class="btn" onclick="document.getElementById('test-result-modal').remove()">关闭</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        } else {
            showAlert('错误: ' + (data.error_message || data.detail || '未知错误'), 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    } finally {
        if (btn) { btn.textContent = '🤖 API 测试'; btn.disabled = false; }
    }
}
