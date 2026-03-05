let currentPreviewIndex = 0;
let currentPreviews = [];
let isSourceView = false;

async function loadExportTasks() {
    const container = document.getElementById('export-task-list');
    if (!container) return;
    
    if (container.dataset.loaded === 'true') return;
    container.dataset.loaded = 'true';
    
    const tasks = window.tasks || [];
    const exportableTasks = tasks.filter(t => t.status === 'completed' || t.status === 'cancelled');
    
    if (exportableTasks.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary);">暂无已完成的任务</p>';
        return;
    }
    
    const tasksByType = {};
    exportableTasks.forEach(task => {
        const type = task.generator_type || 'other';
        if (!tasksByType[type]) {
            tasksByType[type] = [];
        }
        tasksByType[type].push(task);
    });
    
    const typeNames = {
        'single_skill': '单技能对话',
        'single_skill_error': '单技能错误对话',
        'complex_skill': '多技能对话',
        'mixed_dialog': '混合对话',
        'no_tool': '闲聊对话',
        'unknown': '未知类型',
        'other': '其他'
    };
    
    let html = '';
    for (const [type, typeTasks] of Object.entries(tasksByType)) {
        html += `
            <div style="margin-bottom: 16px;">
                <h4 style="margin-bottom: 8px; color: var(--text-primary);">${typeNames[type] || type} (${typeTasks.length})</h4>
                <div style="display: flex; flex-direction: column; gap: 6px;">
        `;
        
        typeTasks.forEach(task => {
            html += `
                <label style="display: flex; align-items: center; padding: 6px 8px; border: 1px solid var(--border-color); border-radius: 4px; cursor: pointer; background: var(--bg-secondary); transition: background 0.2s;" 
                       onmouseover="this.style.background='var(--bg-hover)'" 
                       onmouseout="this.style.background='var(--bg-secondary)'">
                    <input type="checkbox" class="export-task-checkbox" value="${task.id}" style="margin-right: 8px; width: 16px; height: 16px;">
                    <span style="flex: 1; font-size: 0.9rem;">${task.name}</span>
                    <span style="font-size: 0.8rem; color: var(--text-secondary); white-space: nowrap;">${task.progress || 0} 条</span>
                </label>
            `;
        });
        
        html += `
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

async function previewExport() {
    const checkboxes = document.querySelectorAll('.export-task-checkbox:checked');
    const taskIds = Array.from(checkboxes).map(cb => cb.value);
    if (taskIds.length === 0) {
        showAlert('请至少选择一个任务', 'error');
        return;
    }
    
    const previewBtn = document.getElementById('preview-export-btn');
    if (previewBtn) {
        previewBtn.disabled = true;
        previewBtn.textContent = '加载中...';
    }
    
    const config = {
        task_ids: taskIds,
        shuffle: false,
        output_name: 'preview'
    };
    
    try {
        const data = await previewExportAPI(config);
        console.log('Preview data:', data);
        if (data.previews && data.previews.length > 0) {
            currentPreviews = data.previews;
            currentPreviewIndex = 0;
            renderPreviewModal(currentPreviews);
        } else {
            console.log('No previews:', data);
            showAlert('预览数据为空', 'error');
        }
    } catch (e) {
        console.error('Preview error:', e);
        showAlert('预览错误: ' + e.message, 'error');
    } finally {
        if (previewBtn) {
            previewBtn.disabled = false;
            previewBtn.textContent = '预览';
        }
    }
}

function renderPreviewModal(previews) {
    let modal = document.getElementById('preview-modal');
    isSourceView = false;
    
    if (!modal) {
        const modalHtml = `
            <div id="preview-modal" class="modal" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 9999; display: flex; align-items: center; justify-content: center;">
                <div style="background: var(--bg-primary); border-radius: 8px; width: 90%; max-width: 1000px; height: 90vh; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border-color); background: var(--bg-secondary);">
                        <h3 style="margin: 0;">RWKV 导出预览</h3>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <button onclick="toggleSourceView()" id="source-toggle-btn" class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.85rem;">📄 源码</button>
                            <span onclick="closePreviewModal()" style="cursor: pointer; font-size: 24px; line-height: 1;">&times;</span>
                        </div>
                    </div>
                    <div id="preview-content" style="flex: 1; overflow-y: auto; padding: 16px;"></div>
                    <div style="padding: 12px 16px; border-top: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; background: var(--bg-secondary);">
                        <button onclick="changePreviewPage(-1)" class="btn btn-secondary" id="prev-page-btn">上一页</button>
                        <span id="page-indicator">1 / 1</span>
                        <button onclick="changePreviewPage(1)" class="btn btn-secondary" id="next-page-btn">下一页</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        modal = document.getElementById('preview-modal');
    }
    
    if (modal) {
        modal.style.display = 'flex';
    }
    updatePreviewDisplay();
}

function updatePreviewDisplay() {
    const content = document.getElementById('preview-content');
    const pageIndicator = document.getElementById('page-indicator');
    const prevBtn = document.getElementById('prev-page-btn');
    const nextBtn = document.getElementById('next-page-btn');
    
    if (!content) return;
    
    const currentText = currentPreviews[currentPreviewIndex];
    console.log('Rendering preview', currentPreviewIndex, 'length:', currentText.length);
    
    let displayContent;
    if (isSourceView) {
        displayContent = `<pre style="background: #2d2d2d; color: #ccc; padding: 12px; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; word-break: break-all;">${escapeHtml(currentText)}</pre>`;
    } else {
        displayContent = renderMarkdown(currentText);
    }
    
    content.innerHTML = `
        <div style="border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; height: 100%;">
            <div style="background: var(--bg-secondary); padding: 8px 12px; font-weight: 600; border-bottom: 1px solid var(--border-color);">
                样本 ${currentPreviewIndex + 1} / ${currentPreviews.length}
            </div>
            <div style="padding: 16px; background: var(--bg-primary); height: calc(100% - 40px); overflow-y: auto;">${displayContent}</div>
        </div>
    `;
    
    if (pageIndicator) {
        pageIndicator.textContent = `${currentPreviewIndex + 1} / ${currentPreviews.length}`;
    }
    
    if (prevBtn) {
        prevBtn.disabled = currentPreviewIndex === 0;
    }
    if (nextBtn) {
        nextBtn.disabled = currentPreviewIndex === currentPreviews.length - 1;
    }
}

function changePreviewPage(delta) {
    const newIndex = currentPreviewIndex + delta;
    if (newIndex >= 0 && newIndex < currentPreviews.length) {
        currentPreviewIndex = newIndex;
        updatePreviewDisplay();
    }
}

function renderMarkdown(text) {
    let html = escapeHtml(text);
    
    html = html.replace(/^### (.+)$/gm, '<h3 style="color: #e06c75; margin: 16px 0 8px 0; font-size: 1.1rem;">$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2 style="color: #61afef; margin: 20px 0 10px 0; font-size: 1.3rem;">$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1 style="color: #98c379; margin: 24px 0 12px 0; font-size: 1.5rem;">$1</h1>');
    
    html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        return `<pre style="background: #2d2d2d; color: #ccc; padding: 12px; border-radius: 6px; overflow-x: auto;"><code>${code.trim()}</code></pre>`;
    });
    
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';
    html = html.replace(/<p><\/p>/g, '');
    html = html.replace(/<p>(<h[123]>)/g, '$1');
    html = html.replace(/(<\/h[123]>)<\/p>/g, '$1');
    html = html.replace(/<p>(<pre>)/g, '$1');
    html = html.replace(/(<\/pre>)<\/p>/g, '$1');
    html = html.replace(/<p>(<ul>)/g, '$1');
    html = html.replace(/(<\/ul>)<\/p>/g, '$1');
    
    return html;
}

function closePreviewModal() {
    const modal = document.getElementById('preview-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function toggleSourceView() {
    isSourceView = !isSourceView;
    const btn = document.getElementById('source-toggle-btn');
    if (btn) {
        btn.textContent = isSourceView ? '🎨 渲染' : '📄 源码';
        btn.style.background = isSourceView ? 'var(--accent-yellow)' : '';
        btn.style.color = isSourceView ? '#000' : '';
    }
    updatePreviewDisplay();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function exportRWKV() {
    const checkboxes = document.querySelectorAll('.export-task-checkbox:checked');
    const taskIds = Array.from(checkboxes).map(cb => cb.value);
    if (taskIds.length === 0) {
        showAlert('请至少选择一个任务', 'error');
        return;
    }
    const config = {
        task_ids: taskIds,
        shuffle: document.getElementById('export-shuffle')?.checked ?? true,
        merge_by_type: document.getElementById('export-merge-by-type')?.checked ?? false
    };
    try {
        const data = await exportRWKVAPI(config);
        if (data.success) {
            if (data.types_exported) {
                showAlert(`按类型导出成功: ${data.records_exported} 条记录 (${data.types_exported.join(', ')})`, 'success');
                addLog(`RWKV按类型导出完成: ${data.records_exported} 条记录`);
            } else {
                showAlert(`导出成功: ${data.records_exported} 条记录`, 'success');
                addLog(`RWKV导出完成: ${data.records_exported} 条记录`);
            }
        } else {
            showAlert('导出失败', 'error');
        }
    } catch (e) {
        showAlert('导出错误: ' + e.message, 'error');
    }
}
