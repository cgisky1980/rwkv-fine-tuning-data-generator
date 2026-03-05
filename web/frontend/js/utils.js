function showAlert(message, type = 'info') {
    const container = document.getElementById('alert-container');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    container.appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}

function addLog(message) {
    const container = document.getElementById('log-container');
    if (!container) return;
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    const time = new Date().toLocaleTimeString();
    entry.textContent = `[${time}] ${message}`;
    container.insertBefore(entry, container.firstChild);
    if (container.children.length > 50) {
        container.removeChild(container.lastChild);
    }
}

function formatTime(seconds) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds/60)}m ${seconds%60}s`;
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${mins}m`;
}

function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function getType(value) {
    if (value === null) return 'null';
    if (Array.isArray(value)) return 'array';
    return typeof value;
}

function renderPrimitiveValue(value) {
    const type = getType(value);
    switch (type) {
        case 'string':
            const str = escapeHtml(value);
            return `<span style="color: #ce9178;">"${str}"</span>`;
        case 'number':
            return `<span style="color: #b5cea8;">${value}</span>`;
        case 'boolean':
            return `<span style="color: #569cd6;">${value}</span>`;
        case 'null':
            return `<span style="color: #569cd6;">null</span>`;
        default:
            return `<span style="color: #d4d4d4;">${escapeHtml(String(value))}</span>`;
    }
}

function generatePreview(data, type) {
    if (type === 'object') {
        const keys = Object.keys(data).slice(0, 3);
        const preview = keys.map(k => `${k}: ${getValuePreview(data[k])}`).join(', ');
        return keys.length < Object.keys(data).length ? `{${preview}, ...}` : `{${preview}}`;
    } else {
        const items = data.slice(0, 3);
        const preview = items.map(item => getValuePreview(item)).join(', ');
        return items.length < data.length ? `[${preview}, ...]` : `[${preview}]`;
    }
}

function getValuePreview(value) {
    const type = getType(value);
    if (type === 'string') {
        const str = value.length > 20 ? value.substring(0, 20) + '...' : value;
        return `"${str}"`;
    } else if (type === 'number' || type === 'boolean') {
        return String(value);
    } else if (type === 'null') {
        return 'null';
    } else if (type === 'object') {
        return `{${Object.keys(value).length}}`;
    } else if (type === 'array') {
        return `[${value.length}]`;
    }
    return '...';
}
