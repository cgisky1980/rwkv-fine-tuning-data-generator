// Topic management functionality - Tree structure

// Store topics data
window.topicCategories = [];

// Load topics from API
async function loadTopics() {
    try {
        const response = await fetch(`${API_BASE}/api/config/topics`);
        const data = await response.json();
        window.topicCategories = data.categories || [];
        renderTopicCheckboxes();
        updateParentCategorySelect();
    } catch (e) {
        console.error('Failed to load topics:', e);
    }
}

// Render tree structure topic checkboxes
function renderTopicCheckboxes() {
    const container = document.getElementById('topic-checkboxes');
    if (!container) return;
    
    if (window.topicCategories.length === 0) {
        container.innerHTML = '<p style="color: #666;">暂无话题配置</p>';
        return;
    }
    
    let html = '';
    window.topicCategories.forEach((category, catIndex) => {
        html += `
            <div class="topic-category" style="margin-bottom: 15px;">
                <div style="font-weight: 600; color: var(--accent-yellow); margin-bottom: 8px; 
                            display: flex; align-items: center; gap: 8px; cursor: pointer;"
                     onclick="toggleCategory('${category.key}')">
                    <span id="cat-arrow-${category.key}" style="transition: transform 0.3s;">▼</span>
                    <input type="checkbox" class="category-checkbox" 
                           data-category="${category.key}" 
                           onchange="toggleCategoryTopics('${category.key}')"
                           style="width: 16px; height: 16px; margin: 0;">
                    <span>${category.name}</span>
                </div>
                <div id="cat-topics-${category.key}" class="category-topics" 
                     style="margin-left: 24px; display: block;">
        `;
        
        if (category.topics && category.topics.length > 0) {
            category.topics.forEach(topic => {
                html += `
                    <div style="display: flex; align-items: center; gap: 8px; 
                                padding: 6px 8px; background: var(--bg-secondary); 
                                border-radius: 6px; margin-bottom: 6px;">
                        <label style="display: flex; align-items: center; gap: 8px; flex: 1; cursor: pointer;">
                            <input type="checkbox" class="topic-checkbox" 
                                   value="${topic.key}" 
                                   data-parent="${category.key}"
                                   checked
                                   style="width: 16px; height: 16px; accent-color: var(--accent-yellow);">
                            <span style="font-size: 0.9rem;">${topic.name}</span>
                            <span style="font-size: 0.75rem; color: #666; margin-left: auto;">${topic.description || ''}</span>
                        </label>
                        <button onclick="deleteTopic('${category.key}', '${topic.key}', '${topic.name}')" 
                                style="background: none; border: none; color: var(--accent-red); cursor: pointer; font-size: 1.1rem; padding: 2px 6px;"
                                title="删除话题">🗑️</button>
                    </div>
                `;
            });
        }
        
        html += '</div></div>';
    });
    
    container.innerHTML = html;
}

// Toggle category expansion
function toggleCategory(catKey) {
    const topicsDiv = document.getElementById(`cat-topics-${catKey}`);
    const arrow = document.getElementById(`cat-arrow-${catKey}`);
    if (topicsDiv && arrow) {
        if (topicsDiv.style.display === 'none') {
            topicsDiv.style.display = 'block';
            arrow.style.transform = 'rotate(0deg)';
        } else {
            topicsDiv.style.display = 'none';
            arrow.style.transform = 'rotate(-90deg)';
        }
    }
}

// Toggle all topics in category when category checkbox changes
function toggleCategoryTopics(catKey) {
    const catCheckbox = document.querySelector(`.category-checkbox[data-category="${catKey}"]`);
    const topicCheckboxes = document.querySelectorAll(`.topic-checkbox[data-parent="${catKey}"]`);
    topicCheckboxes.forEach(cb => {
        cb.checked = catCheckbox.checked;
    });
}

// Get selected topics
function getSelectedTopics() {
    const checkboxes = document.querySelectorAll('.topic-checkbox:checked');
    const selected = Array.from(checkboxes).map(cb => cb.value);
    return selected.length > 0 ? selected : null;
}

// Select all topics
function selectAllTopics() {
    document.querySelectorAll('.topic-checkbox').forEach(cb => cb.checked = true);
    document.querySelectorAll('.category-checkbox').forEach(cb => cb.checked = true);
}

// Deselect all topics
function deselectAllTopics() {
    document.querySelectorAll('.topic-checkbox').forEach(cb => cb.checked = false);
    document.querySelectorAll('.category-checkbox').forEach(cb => cb.checked = false);
}

// Update parent category select in add topic modal
function updateParentCategorySelect() {
    const select = document.getElementById('new-topic-parent-category');
    if (!select) return;
    
    let html = '<option value="">-- 选择已有分类 --</option>';
    window.topicCategories.forEach(cat => {
        html += `<option value="${cat.key}">${cat.name}</option>`;
    });
    html += '<option value="__new__">+ 创建新分类</option>';
    select.innerHTML = html;
}

// Handle parent category selection change
function onParentCategoryChange() {
    const select = document.getElementById('new-topic-parent-category');
    const newInput = document.getElementById('new-category-input');
    if (select && newInput) {
        newInput.style.display = select.value === '__new__' ? 'block' : 'none';
    }
}

// Open add topic modal
function openAddTopicModal() {
    const modal = document.getElementById('add-topic-modal');
    if (modal) {
        updateParentCategorySelect();
        modal.style.display = 'flex';
        // Reset form
        document.getElementById('new-topic-parent-category').value = '';
        document.getElementById('new-parent-category-name').value = '';
        document.getElementById('new-topic-name').value = '';
        document.getElementById('new-topic-description').value = '';
        onParentCategoryChange();
    }
}

// Close add topic modal
function closeAddTopicModal() {
    const modal = document.getElementById('add-topic-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Submit new topic
async function submitNewTopic() {
    const parentSelect = document.getElementById('new-topic-parent-category');
    const parentKey = parentSelect.value;
    const newParentName = document.getElementById('new-parent-category-name').value.trim();
    const topicName = document.getElementById('new-topic-name').value.trim();
    const topicDesc = document.getElementById('new-topic-description').value.trim();
    
    if (!parentKey) {
        showAlert('请选择所属分类', 'error');
        return;
    }
    
    if (parentKey === '__new__' && !newParentName) {
        showAlert('请输入新分类名称', 'error');
        return;
    }
    
    if (!topicName) {
        showAlert('请输入话题名称', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/config/topics`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                parent_key: parentKey === '__new__' ? null : parentKey,
                new_parent_name: parentKey === '__new__' ? newParentName : null,
                topic_name: topicName,
                topic_description: topicDesc
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert(data.message + '（需重启后端生效）', 'success');
            closeAddTopicModal();
            await loadTopics();
        } else {
            showAlert(data.detail || '添加失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

// Delete topic
async function deleteTopic(categoryKey, topicKey, topicName) {
    if (!confirm(`确定要删除话题"${topicName}"吗？\n\n注意：删除后需要重启后端才能生效。`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/config/topics/${encodeURIComponent(categoryKey)}/${encodeURIComponent(topicKey)}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert(data.message, 'success');
            await loadTopics();
        } else {
            showAlert(data.detail || '删除失败', 'error');
        }
    } catch (e) {
        showAlert('网络错误: ' + e.message, 'error');
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', function() {
    loadTopics();
});
