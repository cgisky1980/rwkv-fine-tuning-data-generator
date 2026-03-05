let currentDataModal = null;
let currentDataRecords = [];
let filteredDataRecords = [];
let currentRecordIndex = 0;
let currentTaskId = '';
let activeLangFilter = '';

function showDataModal(taskId, data, totalCount) {
    currentDataRecords = data;
    filteredDataRecords = [...data];
    currentRecordIndex = 0;
    currentTaskId = taskId;
    activeLangFilter = '';
    const existingModal = document.getElementById('data-modal');
    if (existingModal) existingModal.remove();
    const modal = document.createElement('div');
    modal.id = 'data-modal';
    currentDataModal = modal;
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.85); z-index: 1000;
        display: flex; align-items: center; justify-content: center; padding: 20px;
    `;
    modal.innerHTML = `
        <div style="background: linear-gradient(145deg, var(--bg-card), var(--bg-secondary)); border-radius: 20px; width: 95%; max-width: 1100px; max-height: 90vh; display: flex; flex-direction: column; border: 1px solid var(--border-color); box-shadow: 0 25px 50px rgba(0,0,0,0.5);">
            <div style="padding: 20px 25px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; background: rgba(255,215,0,0.05); flex-wrap: wrap; gap: 15px;">
                <div>
                    <h3 style="margin: 0; color: var(--accent-yellow); font-size: 1.3rem;">📊 数据浏览器</h3>
                    <p id="record-counter" style="margin: 5px 0 0 0; color: var(--text-secondary); font-size: 0.9rem;">记录 1 / ${data.length}${totalCount > data.length ? ` (共 ${totalCount} 条)` : ''}</p>
                </div>
                <button onclick="toggleFilterSidebar()" id="filter-toggle-btn" style="padding: 10px 15px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-primary); cursor: pointer; font-size: 0.9rem; display: flex; align-items: center; gap: 5px;">⚙️ 筛选</button>
                <button onclick="closeDataModal()" style="background: rgba(255,255,255,0.1); border: none; color: var(--text-secondary); font-size: 1.5rem; cursor: pointer; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center;">×</button>
            </div>
            <div style="padding: 0; overflow: hidden; flex: 1; display: flex;">
                <div id="filter-sidebar" style="width: 200px; min-width: 200px; background: var(--bg-secondary); border-right: 1px solid var(--border-color); overflow-y: auto; padding: 20px; display: none;">
                    <h4 style="margin: 0 0 15px 0; color: var(--accent-yellow); font-size: 1rem;">🌍 语言筛选</h4>
                    <div id="filter-controls">
                        <label style="display: flex; align-items: center; gap: 8px; padding: 8px; cursor: pointer; border-radius: 6px; margin-bottom: 5px; background: rgba(255,215,0,0.1);"><input type="radio" name="lang-filter" value="" checked onchange="applyLangFilter(this.value)"> <span>全部语言</span></label>
                        <label style="display: flex; align-items: center; gap: 8px; padding: 8px; cursor: pointer; border-radius: 6px; margin-bottom: 5px;"><input type="radio" name="lang-filter" value="zh" onchange="applyLangFilter(this.value)"> <span>🇨🇳 中文</span></label>
                        <label style="display: flex; align-items: center; gap: 8px; padding: 8px; cursor: pointer; border-radius: 6px; margin-bottom: 5px;"><input type="radio" name="lang-filter" value="en" onchange="applyLangFilter(this.value)"> <span>🇺🇸 英文</span></label>
                        <label style="display: flex; align-items: center; gap: 8px; padding: 8px; cursor: pointer; border-radius: 6px; margin-bottom: 5px;"><input type="radio" name="lang-filter" value="ja" onchange="applyLangFilter(this.value)"> <span>🇯🇵 日文</span></label>
                        <label style="display: flex; align-items: center; gap: 8px; padding: 8px; cursor: pointer; border-radius: 6px; margin-bottom: 5px;"><input type="radio" name="lang-filter" value="ko" onchange="applyLangFilter(this.value)"> <span>🇰🇷 韩文</span></label>
                        <label style="display: flex; align-items: center; gap: 8px; padding: 8px; cursor: pointer; border-radius: 6px; margin-bottom: 5px;"><input type="radio" name="lang-filter" value="de" onchange="applyLangFilter(this.value)"> <span>🇩🇪 德文</span></label>
                        <label style="display: flex; align-items: center; gap: 8px; padding: 8px; cursor: pointer; border-radius: 6px; margin-bottom: 5px;"><input type="radio" name="lang-filter" value="fr" onchange="applyLangFilter(this.value)"> <span>🇫🇷 法文</span></label>
                        <label style="display: flex; align-items: center; gap: 8px; padding: 8px; cursor: pointer; border-radius: 6px; margin-bottom: 5px;"><input type="radio" name="lang-filter" value="es" onchange="applyLangFilter(this.value)"> <span>🇪🇸 西班牙</span></label>
                        <label style="display: flex; align-items: center; gap: 8px; padding: 8px; cursor: pointer; border-radius: 6px; margin-bottom: 5px;"><input type="radio" name="lang-filter" value="ru" onchange="applyLangFilter(this.value)"> <span>🇷🇺 俄文</span></label>
                    </div>
                    <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid var(--border-color);">
                        <button onclick="clearLangFilter()" class="btn" style="width: 100%; background: var(--bg-card); color: var(--text-secondary); padding: 8px; font-size: 0.85rem;">🔄 显示全部</button>
                    </div>
                    <div id="filter-stats" style="margin-top: 10px; font-size: 0.85rem; color: var(--text-secondary);"></div>
                </div>
                <div style="flex: 1; display: flex; flex-direction: column; overflow: hidden;">
                    <div id="json-viewer" style="flex: 1; overflow: auto; padding: 25px; background: var(--bg-primary); font-family: 'Consolas', 'Monaco', monospace; font-size: 0.85rem; line-height: 1.6;"></div>
                </div>
            </div>
            <div style="padding: 20px 25px; border-top: 1px solid var(--border-color); display: flex; gap: 15px; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.2);">
                <div style="display: flex; gap: 10px;">
                    <button id="btn-prev" class="btn" onclick="navigateRecord(-1)" style="padding: 10px 20px; background: var(--bg-secondary); border: 1px solid var(--border-color); color: var(--text-primary);" disabled>← 上一条</button>
                    <button id="btn-next" class="btn" onclick="navigateRecord(1)" style="padding: 10px 20px; background: var(--bg-secondary); border: 1px solid var(--border-color); color: var(--text-primary);">下一条 →</button>
                </div>
                <div style="display: flex; gap: 10px;">
                    <button class="btn" onclick="expandAllNodes()" style="padding: 10px 15px; background: var(--bg-secondary); border: 1px solid var(--border-color); color: var(--text-secondary);">📂 展开全部</button>
                    <button class="btn" onclick="collapseAllNodes()" style="padding: 10px 15px; background: var(--bg-secondary); border: 1px solid var(--border-color); color: var(--text-secondary);">📁 折叠全部</button>
                </div>
                <div style="display: flex; gap: 10px;">
                    <button class="btn btn-secondary" onclick="copyCurrentRecord()" style="padding: 10px 20px;">📋 复制当前</button>
                    <button class="btn btn-primary" onclick="downloadTaskData('${taskId}');" style="padding: 10px 20px;">💾 下载全部</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    renderCurrentRecord();
    updateNavigationButtons();
    modal.addEventListener('click', (e) => { if (e.target === modal) closeDataModal(); });
    modal.focus();
}

function closeDataModal() {
    const modal = document.getElementById('data-modal');
    if (modal) modal.remove();
    currentDataModal = null;
    currentDataRecords = [];
    currentRecordIndex = 0;
}

function navigateRecord(direction) {
    const dataToUse = activeLangFilter ? filteredDataRecords : currentDataRecords;
    const newIndex = currentRecordIndex + direction;
    if (newIndex >= 0 && newIndex < dataToUse.length) {
        currentRecordIndex = newIndex;
        renderFilteredRecord();
        updateNavigationButtons();
        updateRecordCounter();
    }
}

function updateNavigationButtons() {
    const dataToUse = activeLangFilter ? filteredDataRecords : currentDataRecords;
    const prevBtn = document.getElementById('btn-prev');
    const nextBtn = document.getElementById('btn-next');
    if (prevBtn) prevBtn.disabled = currentRecordIndex === 0;
    if (nextBtn) nextBtn.disabled = currentRecordIndex === dataToUse.length - 1;
}

function updateRecordCounter() {
    const dataToUse = activeLangFilter ? filteredDataRecords : currentDataRecords;
    const totalCount = currentDataRecords.length;
    const counter = document.getElementById('record-counter');
    if (counter) {
        if (activeLangFilter) {
            counter.innerHTML = `筛选显示: ${currentRecordIndex + 1}/${dataToUse.length} 条 <small style="color: var(--text-secondary);">(共 ${totalCount} 条)</small>`;
        } else {
            counter.textContent = `记录 ${currentRecordIndex + 1} / ${totalCount}`;
        }
    }
}

function toggleFilterSidebar() {
    const sidebar = document.getElementById('filter-sidebar');
    if (sidebar) sidebar.style.display = sidebar.style.display !== 'none' ? 'none' : 'block';
}

function applyLangFilter(lang) {
    activeLangFilter = lang;
    if (!lang) {
        filteredDataRecords = [...currentDataRecords];
    } else {
        filteredDataRecords = currentDataRecords.filter(record => {
            const recordLang = record.language || record.lang || (record.system && record.system.language) || (record.config && record.config.language);
            return recordLang === lang;
        });
    }
    currentRecordIndex = 0;
    updateFilterStats();
    renderFilteredRecord();
    document.querySelectorAll('input[name="lang-filter"]').forEach(radio => {
        const label = radio.parentElement;
        label.style.background = radio.checked ? 'rgba(255,215,0,0.1)' : 'transparent';
    });
}

function updateFilterStats() {
    const statsEl = document.getElementById('filter-stats');
    if (statsEl) {
        const total = currentDataRecords.length;
        const filtered = filteredDataRecords.length;
        statsEl.innerHTML = !activeLangFilter ? `显示全部 <strong>${total}</strong> 条记录` : `<strong style="color: var(--accent-green);">${filtered}</strong> / ${total} 条`;
    }
}

function clearLangFilter() {
    activeLangFilter = '';
    filteredDataRecords = [...currentDataRecords];
    currentRecordIndex = 0;
    const allRadio = document.querySelector('input[name="lang-filter"][value=""]');
    if (allRadio) allRadio.checked = true;
    updateFilterStats();
    renderFilteredRecord();
    updateNavigationButtons();
    updateRecordCounter();
}

function renderJSONTree(data, key = null, level = 0, path = '') {
    const type = getType(data);
    const indent = level * 20;
    const currentPath = path || 'root';
    if (type === 'object' || type === 'array') {
        const isEmpty = type === 'object' ? Object.keys(data).length === 0 : data.length === 0;
        const count = type === 'object' ? Object.keys(data).length : data.length;
        const bracketOpen = type === 'object' ? '{' : '[';
        const bracketClose = type === 'object' ? '}' : ']';
        let html = `<div class="json-tree-node" style="margin-left: ${indent}px;">`;
        html += `<div class="json-tree-header" style="cursor: pointer; user-select: none;" onclick="toggleTreeNode('${currentPath}')">`;
        html += `<span class="json-toggle-icon" id="icon-${currentPath}" style="display: inline-block; width: 16px; text-align: center; color: var(--accent-yellow);">▼</span> `;
        if (key !== null && key !== undefined) html += `<span class="json-key" style="color: #9cdcfe;">${escapeHtml(JSON.stringify(key))}</span>: `;
        if (isEmpty) {
            html += `<span style="color: #d4d4d4;">${bracketOpen}${bracketClose}</span>`;
        } else {
            html += `<span style="color: #d4d4d4;">${bracketOpen}</span> `;
            const previewText = generatePreview(data, type);
            html += `<span id="preview-${currentPath}" class="json-preview" style="display: none; color: #6e6e6e; font-size: 0.85em;">${previewText}</span> `;
            html += `<span class="json-count" id="count-${currentPath}">${count} ${type === 'object' ? 'keys' : 'items'}</span> `;
            html += `<span style="color: #d4d4d4;">${bracketClose}</span>`;
        }
        html += `</div>`;
        if (!isEmpty) {
            html += `<div class="json-tree-children" id="children-${currentPath}" style="display: block;">`;
            if (type === 'object') {
                Object.keys(data).forEach((k, idx) => {
                    const childPath = `${currentPath}.${k}`;
                    html += renderJSONTree(data[k], k, level + 1, childPath);
                });
            } else {
                data.forEach((item, idx) => {
                    const childPath = `${currentPath}[${idx}]`;
                    html += renderJSONTree(item, idx, level + 1, childPath);
                });
            }
            html += `<div style="margin-left: ${indent}px; color: #d4d4d4;">${bracketClose}</div>`;
            html += `</div>`;
        }
        html += `</div>`;
        return html;
    } else {
        let html = `<div class="json-tree-leaf" style="margin-left: ${indent + 20}px;">`;
        if (key !== null && key !== undefined) html += `<span class="json-key" style="color: #9cdcfe;">${escapeHtml(JSON.stringify(key))}</span>: `;
        html += renderPrimitiveValue(data);
        html += `</div>`;
        return html;
    }
}

function toggleTreeNode(path) {
    const children = document.getElementById(`children-${path}`);
    const icon = document.getElementById(`icon-${path}`);
    const preview = document.getElementById(`preview-${path}`);
    if (children && icon) {
        const isHidden = children.style.display === 'none';
        children.style.display = isHidden ? 'block' : 'none';
        icon.textContent = isHidden ? '▼' : '▶';
        if (preview) preview.style.display = isHidden ? 'none' : 'inline';
    }
}

function expandAllNodes() {
    document.querySelectorAll('.json-tree-children').forEach(el => el.style.display = 'block');
    document.querySelectorAll('.json-toggle-icon').forEach(el => el.textContent = '▼');
    document.querySelectorAll('.json-preview').forEach(el => el.style.display = 'none');
}

function collapseAllNodes() {
    document.querySelectorAll('.json-tree-children').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.json-toggle-icon').forEach(el => el.textContent = '▶');
    document.querySelectorAll('.json-preview').forEach(el => el.style.display = 'inline');
}

function renderCurrentRecord() {
    if (activeLangFilter && filteredDataRecords.length > 0) {
        renderFilteredRecord();
        return;
    }
    const viewer = document.getElementById('json-viewer');
    if (!viewer || !currentDataRecords[currentRecordIndex]) return;
    const record = currentDataRecords[currentRecordIndex];
    viewer.innerHTML = renderJSONTree(record);
    updateRecordCounter();
    updateNavigationButtons();
}

function renderFilteredRecord() {
    const viewer = document.getElementById('json-viewer');
    if (!viewer) return;
    if (filteredDataRecords.length === 0) {
        viewer.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 40px;">该语言暂无数据</p>';
        return;
    }
    const record = filteredDataRecords[currentRecordIndex] || filteredDataRecords[0];
    viewer.innerHTML = renderJSONTree(record);
    updateRecordCounter();
    updateNavigationButtons();
}

function copyCurrentRecord() {
    const dataToUse = activeLangFilter ? filteredDataRecords : currentDataRecords;
    const record = dataToUse[currentRecordIndex];
    if (record) {
        navigator.clipboard.writeText(JSON.stringify(record, null, 2));
        showAlert('已复制到剪贴板', 'success');
    }
}
