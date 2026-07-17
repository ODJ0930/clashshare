// 全局变量
let currentUserId = null;
let currentEditUserId = null;
let currentSubscriptionId = null;
let currentEditTemplateId = null;
let currentEditNodeId = null;
let currentEditNodeProtocol = null;
let allNodes = [];
let allSubscriptions = [];
let allTemplates = [];
let selectedRelayNodes = [];
let currentUserNodeUsername = '';
let userNodeCreateMode = 'existing';
let userQuickAdvancedOpen = false;
let userQuickAutoPort = 0;
let expandedUserNodeRows = new Set();
let xuiSettings = null;
let xuiBackends = [];
let currentXuiBackendId = null;
let xuiBackendStatuses = {};
let xuiBackendModalMode = 'create';
let xuiEditingBackendId = null;
let xuiBackendDraftTested = false;
let xuiInbounds = [];
let xuiInboundGroups = {};
let xuiExpandedInboundBackends = new Set();
let xuiClients = [];
let xuiClientGroups = {};
let currentUserXuiState = { clients: [], backends: [], inbounds: [], selectedBackendId: null };
let currentXuiEditInboundId = null;
let currentXuiEditInboundBackendId = null;
let currentXuiEditClientEmail = null;
let currentXuiEditClientBackendId = null;
const XUI_STATUS_REFRESH_MS = 2000;
let xuiStatusRefreshTimer = null;
let xuiStatusRefreshInFlight = false;
let xuiLastStatusRefreshAt = null;
let xuiInboundEditorStates = {};

const XUI_INBOUND_PROTOCOL_OPTIONS = [
    { value: 'vless', label: 'VLESS' },
    { value: 'vmess', label: 'VMess' },
    { value: 'trojan', label: 'Trojan' },
    { value: 'shadowsocks', label: 'Shadowsocks' },
    { value: 'wireguard', label: 'WireGuard' },
    { value: 'hysteria2', label: 'Hysteria2' },
    { value: 'http', label: 'HTTP' },
    { value: 'socks', label: 'SOCKS / Mixed' },
    { value: 'dokodemo-door', label: 'Dokodemo-door / Tunnel' },
    { value: 'tun', label: 'TUN' }
];

const XUI_INBOUND_NETWORK_OPTIONS = [
    { value: 'tcp', label: 'RAW' },
    { value: 'kcp', label: 'mKCP' },
    { value: 'ws', label: 'WebSocket' },
    { value: 'grpc', label: 'gRPC' },
    { value: 'httpupgrade', label: 'HTTPUpgrade' },
    { value: 'xhttp', label: 'XHTTP' }
];

const XUI_INBOUND_SECURITY_OPTIONS = [
    { value: 'none', label: '无' },
    { value: 'tls', label: 'TLS' },
    { value: 'xtls', label: 'XTLS' },
    { value: 'reality', label: 'Reality' }
];

const XUI_VMESS_SECURITY_VALUES = new Set(['none', 'tls']);
const XUI_VLESS_SECURITY_VALUES = new Set(['none', 'tls', 'reality']);

const XUI_TLS_FINGERPRINT_OPTIONS = [
    { value: 'chrome', label: 'chrome' },
    { value: 'firefox', label: 'firefox' },
    { value: 'safari', label: 'safari' },
    { value: 'ios', label: 'ios' },
    { value: 'android', label: 'android' },
    { value: 'edge', label: 'edge' },
    { value: '360', label: '360' },
    { value: 'qq', label: 'qq' },
    { value: 'random', label: 'random' },
    { value: 'randomized', label: 'randomized' }
];

const XUI_REALITY_TARGET_PRESETS = [
    'www.amd.com:443',
    'www.intel.com:443',
    'www.microsoft.com:443',
    'www.apple.com:443',
    'www.cloudflare.com:443'
];

const XUI_INBOUND_TABS = [
    { value: 'base', label: '基础配置' },
    { value: 'protocol', label: '协议' },
    { value: 'transport', label: '传输' },
    { value: 'security', label: '安全' },
    { value: 'sniffing', label: '嗅探' },
    { value: 'advanced', label: '高级配置' }
];

const USER_QUICK_INBOUND_PREFIX = 'userQuick';
const USER_XUI_SUBSCRIPTION_PROTOCOLS = new Set(['vless', 'vmess', 'trojan', 'shadowsocks', 'hysteria2']);
const USER_XUI_SUBSCRIPTION_NETWORKS = new Set(['tcp', 'ws', 'grpc', 'httpupgrade', 'xhttp']);

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', () => {
    removeXuiBackendToolbar();
    initTabNavigation();
    loadStats();
    loadSubscriptions();
    loadNodes();
    loadUsers();
    loadTemplates();
    loadAdminProfile();
    loadRelayNodes();
    bindXuiBackendDraftDirtyHandlers();
    loadXuiDashboard();
    syncXuiStatusAutoRefresh();
    document.addEventListener('visibilitychange', syncXuiStatusAutoRefresh);
});

function initTabNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            
            // 更新导航高亮
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            // 显示对应内容
            const tabName = item.dataset.tab;
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.getElementById(`${tabName}-tab`).classList.add('active');

            if (tabName === 'xui') {
                loadXuiDashboard();
            }
            syncXuiStatusAutoRefresh();
        });
    });
}

// ============ 统计信息 ============

async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        document.getElementById('stat-subscriptions').textContent = stats.subscriptions;
        document.getElementById('stat-nodes').textContent = stats.nodes;
        document.getElementById('stat-users').textContent = stats.users;
        document.getElementById('stat-templates').textContent = stats.templates || 0;
    } catch (error) {
        console.error('加载统计信息失败:', error);
    }
}

// ============ 订阅管理 ============

async function loadSubscriptions() {
    try {
        const response = await fetch('/api/subscriptions');
        allSubscriptions = await response.json();
        
        const tbody = document.querySelector('#subscriptions-table tbody');
        tbody.innerHTML = '';
        
        allSubscriptions.forEach(sub => {
            // 显示所有关联的用户
            const userBadges = sub.user_names && sub.user_names.length > 0
                ? sub.user_names.map(name => `<span class="badge badge-success" style="margin-right: 4px;">${name}</span>`).join('')
                : '<span class="badge badge-secondary">未分配</span>';
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${sub.name}</strong></td>
                <td>${userBadges}</td>
                <td><span class="badge badge-info">${sub.node_count} 个</span></td>
                <td>${sub.created_at}</td>
                <td class="action-buttons">
                    <button class="btn btn-primary btn-small" onclick="showManageSubscriptionNodesModal(${sub.id}, '${sub.name.replace(/'/g, "\\'")}')">📌 管理节点</button>
                    <button class="btn btn-danger btn-small" onclick="deleteSubscription(${sub.id})">删除</button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('加载订阅失败:', error);
    }
}

function showAddSubscriptionModal() {
    document.getElementById('addSubscriptionModal').style.display = 'block';
    document.getElementById('subName').value = '';
}

async function addSubscription() {
    const name = document.getElementById('subName').value.trim();
    
    if (!name) {
        alert('请填写分组名称');
        return;
    }
    
    try {
        const response = await fetch('/api/subscriptions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('addSubscriptionModal');
            loadSubscriptions();
            loadStats();
        } else {
            alert('创建失败: ' + data.message);
        }
    } catch (error) {
        alert('创建失败: ' + error.message);
    }
}


async function deleteSubscription(id) {
    if (!confirm('确定要删除此订阅及其所有节点吗？此操作不可恢复。')) return;
    
    try {
        const response = await fetch(`/api/subscriptions/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadSubscriptions();
            loadNodes();
            loadUsers(); // 刷新用户列表以更新节点数
            loadStats();
        } else {
            alert('删除失败');
        }
    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}

async function showManageSubscriptionNodesModal(subscriptionId, subscriptionName) {
    currentSubscriptionId = subscriptionId;
    document.getElementById('manageSubscriptionName').textContent = subscriptionName;
    
    // 获取分组当前节点
    const response = await fetch(`/api/subscriptions/${subscriptionId}/nodes`);
    const subscriptionNodes = await response.json();
    const subscriptionNodeIds = subscriptionNodes.map(n => n.id);
    
    // 渲染节点列表
    const container = document.getElementById('subscriptionNodeSelection');
    container.innerHTML = '';
    
    allNodes.forEach(node => {
        const div = document.createElement('div');
        div.className = 'node-item';
        div.innerHTML = `
            <input type="checkbox" id="sub-node-${node.id}" value="${node.id}" 
                   ${subscriptionNodeIds.includes(node.id) ? 'checked' : ''}>
            <div class="node-item-info">
                <div class="node-item-name">${node.name}</div>
                <div class="node-item-meta">${node.protocol.toUpperCase()}  • ${node.subscription_name}</div>
            </div>
        `;
        
        div.addEventListener('click', (e) => {
            if (e.target.tagName !== 'INPUT') {
                const checkbox = div.querySelector('input');
                checkbox.checked = !checkbox.checked;
            }
        });
        
        container.appendChild(div);
    });
    
    document.getElementById('manageSubscriptionNodesModal').style.display = 'block';
}

async function saveSubscriptionNodes() {
    const checkboxes = document.querySelectorAll('#subscriptionNodeSelection input[type="checkbox"]:checked');
    const nodeIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    try {
        const response = await fetch(`/api/subscriptions/${currentSubscriptionId}/nodes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ node_ids: nodeIds })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('manageSubscriptionNodesModal');
            // 刷新所有相关数据
            loadSubscriptions();
            loadNodes();
            loadUsers();
        } else {
            alert('保存失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        alert('保存失败: ' + error.message);
    }
}

// ============ 节点管理 ============

async function loadNodes() {
    try {
        const response = await fetch('/api/nodes');
        allNodes = await response.json();
        
        const tbody = document.querySelector('#nodes-table tbody');
        tbody.innerHTML = '';
        
        allNodes.forEach(node => {
            // 显示所有关联的用户
            const userBadges = node.user_names && node.user_names.length > 0
                ? node.user_names.map(name => `<span class="badge badge-success" style="margin-right: 4px;">${name}</span>`).join('')
                : '<span class="badge badge-secondary">未分配</span>';
            
            // 订阅名称显示为badge
            const subscriptionBadge = node.subscription_name === '手动添加'
                ? '<span class="badge badge-secondary">手动添加</span>'
                : `<span class="badge badge-primary">${node.subscription_name}</span>`;
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td style="text-align: center;">
                    <input type="checkbox" class="node-checkbox" value="${node.id}" onchange="updateBatchDeleteButton()">
                </td>
                <td>
                    <strong>${node.name}</strong>
                    ${node.name !== node.original_name ? `<br><small style="color: #999;">原:  ${node.original_name}</small>` : ''}
                </td>
                <td><span class="badge badge-info">${node.protocol.toUpperCase()}</span></td>
                <td>${subscriptionBadge}</td>
                <td>${userBadges}</td>
                <td>
                    <span class="order-badge" onclick="editNodeOrder(${node.id}, ${node.order || 0})" style="cursor: pointer;" title="点击修改排序">${node.order || 0}</span>
                </td>
                <td class="action-buttons">
                    <button class="btn btn-info btn-small" onclick="showEditNodeModal(${node.id})">✏️ 编辑</button>
                    <button class="btn btn-primary btn-small" onclick="renameNode(${node.id}, '${node.name.replace(/'/g, "\\'")}')">📝 重命名</button>
                    <button class="btn btn-success btn-small" onclick="exportNode(${node.id})">📤 导出</button>
                    <button class="btn btn-danger btn-small" onclick="deleteNode(${node.id})">删除</button>
                </td>
            `;
            tbody.appendChild(row);
        });
        
        // 重置全选框和批量删除按钮
        document.getElementById('selectAllNodes').checked = false;
        updateBatchDeleteButton();
    } catch (error) {
        console.error('加载节点失败:', error);
    }
}

function showAddNodeModal() {
    // 填充订阅选择下拉框
    const select = document.getElementById('nodeSubscription');
    select.innerHTML = '<option value="">不归属任何分组</option>';
    allSubscriptions.forEach(sub => {
        const option = document.createElement('option');
        option.value = sub.id;
        option.textContent = sub.name;
        select.appendChild(option);
    });
    
    document.getElementById('addNodeModal').style.display = 'block';
    document.getElementById('nodeName').value = '';
    document.getElementById('nodeUrl').value = '';
}

function showBatchImportModal() {
    // 填充订阅选择下拉框
    const select = document.getElementById('importSubscription');
    select.innerHTML = '<option value="">不归属任何分组</option>';
    allSubscriptions.forEach(sub => {
        const option = document.createElement('option');
        option.value = sub.id;
        option.textContent = sub.name;
        select.appendChild(option);
    });
    
    document.getElementById('batchImportModal').style.display = 'block';
    document.getElementById('importUrl').value = '';
}

async function addNode() {
    const name = document.getElementById('nodeName').value.trim();
    const url = document.getElementById('nodeUrl').value.trim();
    const subscription_id = document.getElementById('nodeSubscription').value || null;
    
    if (!url) {
        alert('请输入节点配置');
        return;
    }
    
    try {
        const response = await fetch('/api/nodes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, url, subscription_id })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('✅ 节点添加成功');
            closeModal('addNodeModal');
            loadNodes();
            loadSubscriptions(); // 刷新订阅列表以更新节点数
            loadUsers(); // 刷新用户列表以更新节点数
            loadStats();
        } else {
            alert('❌ 添加失败: ' + data.message);
        }
    } catch (error) {
        alert('❌ 添加失败: ' + error.message);
    }
}

async function batchImportNodes() {
    const url = document.getElementById('importUrl').value.trim();
    const subscription_id = document.getElementById('importSubscription').value || null;
    
    if (!url) {
        alert('请输入订阅链接');
        return;
    }
    
    if (!confirm('确定要从此链接导入节点吗？')) return;
    
    try {
        const response = await fetch('/api/nodes/batch-import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, subscription_id })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('batchImportModal');
            loadNodes();
            loadSubscriptions(); // 刷新订阅列表以更新节点数
            loadUsers(); // 刷新用户列表以更新节点数
            loadStats();
        } else {
            alert('导入失败: ' + data.message);
        }
    } catch (error) {
        alert('导入失败: ' + error.message);
    }
}

async function exportNode(id) {
    try {
        const response = await fetch(`/api/nodes/${id}/export`);
        const data = await response.json();

        if (!response.ok || !data.success) {
            alert(data.message || '导出失败');
            return;
        }

        const shareUrl = data.url;
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(shareUrl);
            alert('✅ 节点分享链接已复制，可直接粘贴到 v2rayN / v2rayNG 等客户端导入');
        } else {
            window.prompt('复制以下节点分享链接:', shareUrl);
        }
    } catch (error) {
        alert('导出失败: ' + error.message);
    }
}

async function renameNode(id, currentName) {
    const newName = prompt('输入新名称', currentName);
    if (!newName || newName === currentName) return;
    
    try {
        const response = await fetch(`/api/nodes/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newName })
        });
        
        if (response.ok) {
            // 刷新所有相关数据
            loadNodes();
            loadRelayNodes();
        } else {
            alert('重命名失败');
        }
    } catch (error) {
        alert('重命名失败: ' + error.message);
    }
}

async function deleteNode(id) {
    if (!confirm('确定要删除此节点吗？')) return;
    
    try {
        const response = await fetch(`/api/nodes/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadNodes();
            loadSubscriptions(); // 刷新订阅列表以更新节点数
            loadUsers(); // 刷新用户列表以更新节点数
            loadStats();
        } else {
            alert('删除失败');
        }
    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}

// ============ 批量删除节点功能 ============

function toggleAllNodeSelection() {
    const selectAllCheckbox = document.getElementById('selectAllNodes');
    const checkboxes = document.querySelectorAll('.node-checkbox');
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = selectAllCheckbox.checked;
    });
    
    updateBatchDeleteButton();
}

function updateBatchDeleteButton() {
    const checkboxes = document.querySelectorAll('.node-checkbox:checked');
    const batchDeleteBtn = document.getElementById('batchDeleteBtn');
    
    if (checkboxes.length > 0) {
        batchDeleteBtn.style.display = 'inline-block';
        batchDeleteBtn.textContent = `🗑️ 批量删除 (${checkboxes.length})`;
    } else {
        batchDeleteBtn.style.display = 'none';
    }
    
    // 更新全选框的状态
    const allCheckboxes = document.querySelectorAll('.node-checkbox');
    const selectAllCheckbox = document.getElementById('selectAllNodes');
    
    if (allCheckboxes.length > 0) {
        selectAllCheckbox.checked = checkboxes.length === allCheckboxes.length;
        // 使用不确定状态表示部分选中
        selectAllCheckbox.indeterminate = checkboxes.length > 0 && checkboxes.length < allCheckboxes.length;
    }
}

async function batchDeleteNodes() {
    const checkboxes = document.querySelectorAll('.node-checkbox:checked');
    const nodeIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    if (nodeIds.length === 0) {
        alert('请先选择要删除的节点');
        return;
    }
    
    if (!confirm(`确定要删除选中的 ${nodeIds.length} 个节点吗？此操作不可恢复。`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/nodes/batch-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ node_ids: nodeIds })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ ${data.message}`);
            loadNodes();
            loadSubscriptions(); // 刷新订阅列表以更新节点数
            loadUsers(); // 刷新用户列表以更新节点数
            loadStats();
        } else {
            alert('❌ 删除失败: ' + data.message);
        }
    } catch (error) {
        alert('❌ 删除失败: ' + error.message);
    }
}

// ============ 用户管理 ============

function formatTrafficGb(bytes, decimals = 3) {
    const gb = Number(bytes || 0) / 1024 / 1024 / 1024;
    const fixed = gb.toFixed(decimals);
    return `${fixed.replace(/\.?0+$/, '') || '0'} GB`;
}

async function loadUsers() {
    try {
        const response = await fetch('/api/users');
        const users = await response.json();

        const tbody = document.querySelector('#users-table tbody');
        tbody.innerHTML = '';

        users.forEach(user => {
            const token = user.custom_slug || user.subscription_token;
            const subUrl = `${window.location.origin}/sub/user/${token}`;
            const shadowrocketSubUrl = `${subUrl}/shadowrocket`;
            const isCustom = user.custom_slug ? '🔗' : '';
            const templateName = user.template_name || '默认';
            const directNodeText = user.direct_node_count
                ? `<br><small style="color: #7f8c8d;">直分 ${user.direct_node_count} 个</small>`
                : '';
            const trafficLimit = Number(user.traffic_limit || 0);
            const trafficUsed = Number(user.traffic_used || 0);
            const trafficText = `${formatTrafficGb(trafficUsed)} / ${trafficLimit ? formatTrafficGb(trafficLimit) : '不限'}`;
            const expanded = expandedUserNodeRows.has(Number(user.id));
            const row = document.createElement('tr');
            row.className = 'user-summary-row';
            row.dataset.userId = user.id;
            row.innerHTML = `
                <td class="user-expand-cell">
                    <button class="user-row-toggle ${expanded ? 'expanded' : ''}" type="button" data-user-node-toggle="${user.id}" aria-label="${expanded ? '收起节点' : '展开节点'}" onclick="toggleUserOwnedNodes(${user.id})">${expanded ? '▾' : '▸'}</button>
                </td>
                <td><strong>${escapeHtml(user.username)}</strong></td>
                <td>${user.remark ? escapeHtml(user.remark) : '-'}</td>
                <td><span class="badge badge-info">${escapeHtml(templateName)}</span></td>
                <td><span class="badge badge-primary">${user.subscription_count} 个</span></td>
                <td><span class="badge badge-info">${user.node_count} 个</span>${directNodeText}</td>
                <td>${trafficText}</td>
                <td>
                    <span class="badge ${user.enabled ? 'badge-success' : 'badge-danger'}">
                        ${user.enabled ? '启用' : '禁用'}
                    </span>
                </td>
                <td>
                    <div class="subscription-link-stack">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <code class="url-display" style="flex: 1;" title="${user.custom_slug ? '自定义链接' : '系统生成链接'}">${isCustom}${escapeHtml(truncateUrl(subUrl, 40))}</code>
                            <button class="copy-btn" onclick="copyToClipboard('${escapeJs(subUrl)}')">📋 复制</button>
                        </div>
                        <div class="subscription-link-row">
                            <span class="subscription-link-label">Shadowrocket</span>
                            <code class="url-display" title="Shadowrocket 订阅链接">${escapeHtml(truncateUrl(shadowrocketSubUrl, 40))}</code>
                            <button class="copy-btn" onclick="copyToClipboard('${escapeJs(shadowrocketSubUrl)}')">📋 复制</button>
                        </div>
                    </div>
                </td>
                <td class="action-buttons">
                    <button class="btn btn-primary btn-small" onclick="showAssignSubscriptionsModal(${user.id}, '${escapeJs(user.username)}')">📌 管理订阅</button>
                    <button class="btn btn-info btn-small" onclick="showAssignUserNodesModal(${user.id}, '${escapeJs(user.username)}')">🌐 管理节点</button>
                    <button class="btn btn-secondary btn-small" onclick="showEditUserModal(${user.id})">✏️ 编辑</button>
                    <button class="btn btn-secondary btn-small" onclick="toggleUserStatus(${user.id}, ${!user.enabled})">${user.enabled ? '禁用' : '启用'}</button>
                    <button class="btn btn-danger btn-small" onclick="deleteUser(${user.id})">删除</button>
                </td>
            `;
            tbody.appendChild(row);

            const detailRow = document.createElement('tr');
            detailRow.className = 'user-node-detail-row';
            detailRow.id = `user-node-detail-${user.id}`;
            detailRow.style.display = expanded ? 'table-row' : 'none';
            detailRow.innerHTML = `
                <td colspan="10">
                    <div class="user-node-detail-panel" id="user-node-detail-panel-${user.id}">
                        <div class="user-node-detail-loading">加载节点中...</div>
                    </div>
                </td>
            `;
            tbody.appendChild(detailRow);
            if (expanded) {
                loadUserOwnedNodes(user.id);
            }
        });
    } catch (error) {
        console.error('加载用户失败:', error);
    }
}

function setUserNodeToggleState(userId, expanded) {
    const button = document.querySelector(`[data-user-node-toggle="${userId}"]`);
    if (!button) return;
    button.classList.toggle('expanded', expanded);
    button.textContent = expanded ? '▾' : '▸';
    button.setAttribute('aria-label', expanded ? '收起节点' : '展开节点');
}

async function toggleUserOwnedNodes(userId) {
    const numericUserId = Number(userId);
    const detailRow = document.getElementById(`user-node-detail-${numericUserId}`);
    if (!detailRow) return;

    const expanded = !expandedUserNodeRows.has(numericUserId);
    if (!expanded) {
        expandedUserNodeRows.delete(numericUserId);
        detailRow.style.display = 'none';
        setUserNodeToggleState(numericUserId, false);
        return;
    }

    expandedUserNodeRows.add(numericUserId);
    detailRow.style.display = 'table-row';
    setUserNodeToggleState(numericUserId, true);
    await loadUserOwnedNodes(numericUserId);
}

function renderUserOwnedNodes(userId, clients) {
    const panel = document.getElementById(`user-node-detail-panel-${userId}`);
    if (!panel) return;
    if (!clients.length) {
        panel.innerHTML = '<div class="user-node-detail-empty">当前用户还没有 3x-ui 节点</div>';
        return;
    }

    panel.innerHTML = `
        <div class="user-node-detail-list">
            ${clients.map(client => {
                const originalHost = client.backend_public_host || '';
                const originalPort = Number(client.inbound_port || 0);
                const effectiveHost = client.subscription_effective_host || originalHost || '-';
                const effectivePort = Number(client.subscription_effective_port || originalPort || 0);
                const overrideHost = client.subscription_host || '';
                const overridePort = Number(client.subscription_port || 0);
                const inboundTotal = Number(client.inbound_total ?? client.traffic_limit ?? 0);
                const inboundUsed = Number(client.inbound_used ?? client.traffic_used ?? 0);
                const usage = `${formatBytes(inboundUsed)} / ${inboundTotal ? formatBytes(inboundTotal) : '不限'}`;
                const expiryText = userNodeExpiryLabel(client.inbound_expiry_time ?? client.expiry_time);
                const resetText = userNodeResetLabel(Number(client.inbound_reset || 0));
                const statusText = client.enabled ? '启用' : '禁用';
                const originalEndpoint = `${originalHost || '-'}:${originalPort || '-'}`;
                const effectiveEndpoint = `${effectiveHost || '-'}:${effectivePort || '-'}`;
                return `
                    <div class="user-owned-node-card" data-user-owned-node-id="${client.id}">
                        <div class="user-owned-node-main">
                            <div>
                                <strong>${escapeHtml(client.display_name || client.inbound_name || client.client_email)}</strong>
                                <span class="badge ${client.enabled ? 'badge-success' : 'badge-secondary'}">${statusText}</span>
                            </div>
                            <small>${escapeHtml(client.backend_name)} · ${escapeHtml(client.inbound_name)} · ${escapeHtml(String(client.inbound_protocol || '').toUpperCase())}</small>
                            <small>原始节点：${escapeHtml(originalEndpoint)} · 订阅输出：${escapeHtml(effectiveEndpoint)}</small>
                            <small>统计：${escapeHtml(usage)} · ${escapeHtml(expiryText)} · ${escapeHtml(resetText)}</small>
                        </div>
                        <div class="user-owned-node-endpoint">
                            <label>
                                <span>订阅 IP / 域名</span>
                                <input type="text" class="user-owned-node-host" value="${escapeHtml(overrideHost)}" placeholder="${escapeHtml(originalHost || '原始地址')}">
                            </label>
                            <label>
                                <span>订阅端口</span>
                                <input type="number" min="1" max="65535" class="user-owned-node-port" value="${overridePort || ''}" placeholder="${escapeHtml(originalPort || '原始端口')}">
                            </label>
                            <button class="btn btn-secondary btn-small" type="button" data-user-owned-node-save="${client.id}" onclick="saveUserOwnedNodeEndpoint(${userId}, ${client.id})">保存覆盖</button>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

async function loadUserOwnedNodes(userId) {
    const panel = document.getElementById(`user-node-detail-panel-${userId}`);
    if (!panel) return;
    panel.innerHTML = '<div class="user-node-detail-loading">加载节点中...</div>';
    try {
        const params = new URLSearchParams({ sync: '0', include_inbounds: '0' });
        const response = await fetch(`/api/users/${userId}/xui-clients?${params.toString()}`);
        const data = await response.json();
        if (!data.success) {
            panel.innerHTML = `<div class="user-node-detail-empty">${escapeHtml(data.message || '加载节点失败')}</div>`;
            return;
        }
        renderUserOwnedNodes(userId, data.clients || []);
    } catch (error) {
        panel.innerHTML = `<div class="user-node-detail-empty">${escapeHtml(error.message || '加载节点失败')}</div>`;
    }
}

async function saveUserOwnedNodeEndpoint(userId, clientId) {
    const card = document.querySelector(`[data-user-owned-node-id="${clientId}"]`);
    if (!card) return;
    const host = card.querySelector('.user-owned-node-host')?.value.trim() || '';
    const portValue = card.querySelector('.user-owned-node-port')?.value || '';
    const port = portValue === '' ? '' : Number(portValue);
    if (port !== '' && port !== 0 && (!Number.isInteger(port) || port < 1 || port > 65535)) {
        alert('订阅端口必须在 1-65535 之间，留空则使用原始端口');
        return;
    }

    const button = card.querySelector(`[data-user-owned-node-save="${clientId}"]`);
    const originalText = button?.textContent || '保存覆盖';
    try {
        if (button) {
            button.disabled = true;
            button.textContent = '保存中...';
        }
        const response = await fetch(`/api/users/${userId}/xui-clients/${clientId}/subscription-endpoint`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                subscription_host: host,
                subscription_port: port
            })
        });
        let data;
        try {
            data = await response.json();
        } catch (parseError) {
            throw new Error(`HTTP ${response.status}: ${response.statusText || '响应不是 JSON'}`);
        }
        if (!response.ok || !data.success) {
            alert('保存失败: ' + (data.message || '未知错误'));
            return;
        }
        await loadUserOwnedNodes(userId);
        alert('保存成功');
    } catch (error) {
        alert('保存失败: ' + error.message);
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = originalText;
        }
    }
}

function showAddUserModal() {
    document.getElementById('addUserModal').style.display = 'block';
    document.getElementById('userName').value = '';
    document.getElementById('userRemark').value = '';
    document.getElementById('userTrafficLimitGb').value = '0';
}

async function addUser() {
    const username = document.getElementById('userName').value.trim();
    const remark = document.getElementById('userRemark').value.trim();
    const traffic_limit_gb = Number(document.getElementById('userTrafficLimitGb').value || 0);
    
    if (!username) {
        alert('请填写名称');
        return;
    }
    
    try {
        const response = await fetch('/api/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, remark, traffic_limit_gb })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('addUserModal');
            loadUsers();
            loadStats();
        } else {
            alert('创建失败: ' + data.message);
        }
    } catch (error) {
        alert('创建失败: ' + error.message);
    }
}

async function showEditUserModal(userId) {
    currentEditUserId = userId;
    
    // 获取用户信息
    try {
        const response = await fetch(`/api/users`);
        const users = await response.json();
        const user = users.find(u => u.id === userId);
        
        if (!user) {
            alert('用户不存在');
            return;
        }
        
        // 填充用户信息
        document.getElementById('editUserName').value = user.username;
        document.getElementById('editUserRemark').value = user.remark || '';
        document.getElementById('editUserCustomSlug').value = user.custom_slug || '';
        document.getElementById('editUserTrafficLimitGb').value = user.traffic_limit_gb || 0;
        
        // 填充模板下拉框
        const templateSelect = document.getElementById('editUserTemplate');
        templateSelect.innerHTML = '<option value="">使用默认模板</option>';
        
        allTemplates.forEach(template => {
            const option = document.createElement('option');
            option.value = template.id;
            option.textContent = template.name;
            if (user.template_id === template.id) {
                option.selected = true;
            }
            templateSelect.appendChild(option);
        });
        
        document.getElementById('editUserModal').style.display = 'block';
    } catch (error) {
        alert('加载用户信息失败: ' + error.message);
    }
}

async function saveUserEdit() {
    const username = document.getElementById('editUserName').value.trim();
    const remark = document.getElementById('editUserRemark').value.trim();
    const customSlug = document.getElementById('editUserCustomSlug').value.trim();
    const templateId = document.getElementById('editUserTemplate').value;
    const traffic_limit_gb = Number(document.getElementById('editUserTrafficLimitGb').value || 0);
    
    if (!username) {
        alert('名称不能为空');
        return;
    }
    
    // 验证自定义后缀格式
    if (customSlug && !/^[a-zA-Z0-9_-]+$/.test(customSlug)) {
        alert('自定义后缀只能包含字母、数字、下划线和中划线');
        return;
    }
    
    try {
        const updateData = { username, remark, custom_slug: customSlug || null, traffic_limit_gb };
        if (templateId) {
            updateData.template_id = parseInt(templateId);
        }
        
        const response = await fetch(`/api/users/${currentEditUserId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateData)
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('editUserModal');
            loadUsers();
        } else {
            alert('❌ ' + data.message);
        }
    } catch (error) {
        alert('修改失败: ' + error.message);
    }
}

async function toggleUserStatus(id, enabled) {
    try {
        const response = await fetch(`/api/users/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
        
        if (response.ok) {
            loadUsers();
        } else {
            alert('操作失败');
        }
    } catch (error) {
        alert('操作失败: ' + error.message);
    }
}

async function deleteUser(id) {
    if (!confirm('确定要删除此用户吗？')) return;
    
    try {
        const response = await fetch(`/api/users/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadUsers();
            loadStats();
        } else {
            alert('删除失败');
        }
    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}

// ============ 节点分配 ============

async function showAssignSubscriptionsModal(userId, username) {
    currentUserId = userId;
    document.getElementById('assignUserName').textContent = username;
    
    // 获取用户当前订阅
    const response = await fetch(`/api/users/${userId}/subscriptions`);
    const userSubscriptions = await response.json();
    const userSubIds = userSubscriptions.map(s => s.id);
    
    // 渲染订阅列表
    const container = document.getElementById('subscriptionSelection');
    container.innerHTML = '';
    
    allSubscriptions.forEach(sub => {
        const div = document.createElement('div');
        div.className = 'node-item';
        div.innerHTML = `
            <input type="checkbox" id="sub-${sub.id}" value="${sub.id}" 
                   ${userSubIds.includes(sub.id) ? 'checked' : ''}>
            <div class="node-item-info">
                <div class="node-item-name">${sub.name}</div>
                <div class="node-item-meta">${sub.node_count} 个节点 • 创建于 ${sub.created_at}</div>
            </div>
        `;
        
        div.addEventListener('click', (e) => {
            if (e.target.tagName !== 'INPUT') {
                const checkbox = div.querySelector('input');
                checkbox.checked = !checkbox.checked;
            }
        });
        
        container.appendChild(div);
    });
    
    document.getElementById('assignSubscriptionsModal').style.display = 'block';
}

async function saveUserSubscriptions() {
    const checkboxes = document.querySelectorAll('#subscriptionSelection input[type="checkbox"]:checked');
    const subscriptionIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    try {
        const response = await fetch(`/api/users/${currentUserId}/subscriptions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subscription_ids: subscriptionIds })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('assignSubscriptionsModal');
            // 刷新所有相关数据
            loadUsers();
            loadSubscriptions();
            loadNodes();
        } else {
            alert('保存失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        alert('保存失败: ' + error.message);
    }
}

// ============ 工具函数 ============

function userNodeDateTimeLocalFromMs(value) {
    const timestamp = Number(value || 0);
    if (!timestamp) return '';
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return '';
    const pad = number => String(number).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function userNodeMsFromDateTimeLocal(value) {
    if (!value) return 0;
    const timestamp = new Date(value).getTime();
    return Number.isNaN(timestamp) ? 0 : timestamp;
}

function resetUserNodeCreateForm() {
    const form = document.getElementById('userNodeCreateForm');
    if (form) form.style.display = 'none';
    userNodeCreateMode = 'existing';
    userQuickAdvancedOpen = false;
    userQuickAutoPort = 0;
    delete xuiInboundEditorStates[USER_QUICK_INBOUND_PREFIX];
    [
        'userNodeCreateExpiry',
        'userXuiComment',
        'userQuickInboundName',
        'userQuickInboundPort',
        'userQuickInboundExpiry',
        'userQuickClientComment'
    ].forEach(id => {
        const field = document.getElementById(id);
        if (field) field.value = '';
    });
    const limit = document.getElementById('userNodeCreateLimitGb');
    if (limit) limit.value = '';
    const reset = document.getElementById('userNodeCreateReset');
    if (reset) reset.value = '';
    const limitIp = document.getElementById('userXuiLimitIp');
    if (limitIp) limitIp.value = '0';
    const enable = document.getElementById('userXuiEnable');
    if (enable) enable.checked = true;
    const inboundContainer = document.getElementById('userXuiInboundSelection');
    if (inboundContainer) inboundContainer.innerHTML = '';
    const quickLimit = document.getElementById('userQuickInboundTotalGb');
    if (quickLimit) quickLimit.value = '0';
    const quickReset = document.getElementById('userQuickInboundReset');
    if (quickReset) quickReset.value = '0';
    const quickLimitIp = document.getElementById('userQuickClientLimitIp');
    if (quickLimitIp) quickLimitIp.value = '0';
    const quickProtocol = document.getElementById('userQuickInboundProtocol');
    if (quickProtocol) quickProtocol.value = 'vless';
    const quickNetwork = document.getElementById('userQuickInboundNetwork');
    if (quickNetwork) quickNetwork.value = 'tcp';
    const quickSecurity = document.getElementById('userQuickInboundSecurity');
    if (quickSecurity) quickSecurity.value = 'none';
    const quickEnable = document.getElementById('userQuickClientEnable');
    if (quickEnable) quickEnable.checked = true;
    const quickAdvanced = document.getElementById('userQuickAdvancedConfig');
    if (quickAdvanced) quickAdvanced.style.display = 'none';
    const quickMount = document.getElementById(xuiInboundMountId(USER_QUICK_INBOUND_PREFIX));
    if (quickMount) quickMount.innerHTML = '';
    const quickAdvancedButton = document.getElementById('userQuickAdvancedToggle');
    if (quickAdvancedButton) quickAdvancedButton.textContent = '展开完整配置';
}

function toggleUserNodeCreateForm(forceOpen, mode = userNodeCreateMode || 'existing') {
    const form = document.getElementById('userNodeCreateForm');
    if (!form) return;
    const shouldOpen = typeof forceOpen === 'boolean' ? forceOpen : form.style.display === 'none';
    form.style.display = shouldOpen ? 'block' : 'none';
    if (shouldOpen) showUserNodeCreateMode(mode);
}

function showUserNodeCreateMode(mode) {
    userNodeCreateMode = mode === 'quick' ? 'quick' : 'existing';
    const existingSection = document.getElementById('userNodeExistingCreateSection');
    const quickSection = document.getElementById('userNodeQuickCreateSection');
    if (existingSection) existingSection.style.display = userNodeCreateMode === 'existing' ? 'block' : 'none';
    if (quickSection) quickSection.style.display = userNodeCreateMode === 'quick' ? 'block' : 'none';
    document.querySelectorAll('[data-user-node-create-mode]').forEach(button => {
        button.classList.toggle('active', button.dataset.userNodeCreateMode === userNodeCreateMode);
    });
    if (userNodeCreateMode === 'existing') {
        loadUserXuiBackendInbounds();
    } else {
        initUserQuickInboundForm();
    }
}

function userNodeExpiryLabel(value) {
    const timestamp = Number(value || 0);
    if (!timestamp) return '永不过期';
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? '未知' : date.toLocaleString();
}

function userNodeResetLabel(value) {
    const labels = {
        0: '从不',
        1: '每日',
        2: '每周',
        3: '每月'
    };
    const reset = Number(value || 0);
    return labels[reset] || `策略 ${reset}`;
}

function renderUserXuiBackendOptions(backends, selectedBackendId) {
    const options = !backends.length
        ? '<option value="">暂无 3x-ui 后端</option>'
        : backends.map(backend => `
        <option value="${backend.id}" ${Number(backend.id) === Number(selectedBackendId) ? 'selected' : ''}>
            ${escapeHtml(backend.name || `后端 ${backend.id}`)}
        </option>
    `).join('');
    ['userXuiBackendSelect', 'userQuickXuiBackendSelect'].forEach(id => {
        const select = document.getElementById(id);
        if (select) select.innerHTML = options;
    });
}

function renderUserXuiInbounds(inbounds, inboundError = '') {
    const container = document.getElementById('userXuiInboundSelection');
    if (!container) return;
    if (inboundError) {
        container.innerHTML = `<div class="empty-state">${escapeHtml(inboundError)}</div>`;
        return;
    }
    if (!inbounds.length) {
        container.innerHTML = '<div class="empty-state">暂无可用入站，请先在 3x-ui 后端创建入站节点。</div>';
        return;
    }
    container.innerHTML = inbounds.map(inbound => {
        const supported = inbound.subscription_supported !== false && inbound.enable !== false;
        const reason = inbound.enable === false ? '入站未启用' : (inbound.unsupported_reason || '');
        return `
            <label class="user-node-card user-xui-inbound-card ${supported ? '' : 'disabled'}">
                <input type="checkbox" class="user-xui-inbound-checkbox" value="${inbound.id}" ${supported ? '' : 'disabled'}>
                <span class="user-xui-inbound-main">
                    <strong>${escapeHtml(inbound.remark || `Inbound ${inbound.id}`)}</strong>
                    <small>${escapeHtml(String(inbound.protocol || '').toUpperCase())} · ${escapeHtml(inbound.network || 'tcp')} · ${escapeHtml(String(inbound.port || '-'))}</small>
                    ${reason ? `<em>${escapeHtml(reason)}</em>` : ''}
                </span>
            </label>
        `;
    }).join('');
}

function renderUserXuiClients(clients) {
    const container = document.getElementById('userNodeSelection');
    if (!container) return;
    if (!clients.length) {
        container.innerHTML = '<div class="empty-state">该用户还没有 3x-ui 客户端。点击上方新增 3x-ui 客户端。</div>';
        return;
    }
    container.innerHTML = clients.map(client => {
        const inboundTotal = Number(client.inbound_total ?? client.traffic_limit ?? 0);
        const inboundUsed = Number(client.inbound_used ?? client.traffic_used ?? 0);
        const usage = `${formatBytes(inboundUsed)} / ${inboundTotal ? formatBytes(inboundTotal) : '不限'}`;
        const expiryValue = userNodeDateTimeLocalFromMs(client.inbound_expiry_time ?? client.expiry_time);
        const expiryText = userNodeExpiryLabel(client.inbound_expiry_time ?? client.expiry_time);
        const resetValue = Number(client.inbound_reset || 0);
        const resetText = userNodeResetLabel(resetValue);
        const statusBadge = client.last_error
            ? `<span class="badge badge-danger">${escapeHtml(client.last_error)}</span>`
            : `<span class="badge ${client.enabled ? 'badge-success' : 'badge-secondary'}">${client.enabled ? '启用' : '禁用'}</span>`;
        const onlineBadge = client.online ? '<span class="badge badge-info">在线</span>' : '';
        const inboundBadge = client.inbound_enable === false
            ? '<span class="badge badge-secondary">入站禁用</span>'
            : ((client.inbound_expired || client.inbound_exhausted)
                ? `<span class="badge badge-danger">${client.inbound_expired ? '入站过期' : '流量耗尽'}</span>`
                : '');
        return `
            <div class="user-node-card selected" data-user-xui-client-id="${client.id}">
                <div class="user-node-checkline">
                    <span>
                        <strong>${escapeHtml(client.display_name || client.inbound_name || client.client_email)}</strong>
                        ${statusBadge}
                        ${onlineBadge}
                        ${inboundBadge}
                        <small>${escapeHtml(client.backend_name)} · ${escapeHtml(client.inbound_name)} · ${escapeHtml(String(client.inbound_protocol || '').toUpperCase())}</small>
                        <small>${escapeHtml(client.client_email)} · 入站 ${escapeHtml(usage)} · ${escapeHtml(expiryText)} · ${escapeHtml(resetText)}</small>
                    </span>
                </div>
                <div class="user-node-fields">
                    <label>
                        <span>显示名称</span>
                        <input type="text" class="user-xui-display-name" value="${escapeHtml(client.display_name || '')}">
                    </label>
                    <label>
                        <span>入站总流量 GB</span>
                        <input type="number" min="0" step="0.1" class="user-node-limit" value="${client.inbound_total_gb ?? client.traffic_limit_gb ?? 0}">
                    </label>
                    <label>
                        <span>入站到期</span>
                        <input type="datetime-local" class="user-node-expiry" value="${expiryValue}">
                    </label>
                    <label>
                        <span>流量重置</span>
                        <select class="user-node-reset">
                            <option value="0" ${resetValue === 0 ? 'selected' : ''}>从不</option>
                            <option value="1" ${resetValue === 1 ? 'selected' : ''}>每日</option>
                            <option value="2" ${resetValue === 2 ? 'selected' : ''}>每周</option>
                            <option value="3" ${resetValue === 3 ? 'selected' : ''}>每月</option>
                        </select>
                    </label>
                    <label>
                        <span>IP 限制</span>
                        <input type="number" min="0" class="user-xui-limit-ip" value="${client.limit_ip || 0}">
                    </label>
                    <label>
                        <span>备注</span>
                        <input type="text" class="user-xui-comment" value="${escapeHtml(client.comment || '')}">
                    </label>
                    <label class="user-xui-enable-line">
                        <span>启用</span>
                        <input type="checkbox" class="user-xui-enable" ${client.enabled ? 'checked' : ''}>
                    </label>
                </div>
                <div class="user-node-create-footer">
                    <button class="btn btn-secondary btn-small" type="button" data-user-xui-save-button="${client.id}" onclick="updateUserXuiClient(${client.id})">保存到 3x-ui</button>
                    <button class="btn btn-danger btn-small" type="button" onclick="deleteUserXuiClient(${client.id})">删除远端</button>
                </div>
            </div>
        `;
    }).join('');
}

async function loadUserXuiClientData(userId = currentUserId, options = {}) {
    if (!userId) return;
    const sync = options.sync === false ? 0 : 1;
    const includeInbounds = options.includeInbounds === true ? 1 : 0;
    const backendId = options.backendId || document.getElementById('userXuiBackendSelect')?.value || '';
    const params = new URLSearchParams({
        sync: String(sync),
        include_inbounds: String(includeInbounds)
    });
    if (backendId) params.set('backend_id', backendId);
    const response = await fetch(`/api/users/${userId}/xui-clients?${params.toString()}`);
    const data = await response.json();
    if (!data.success) {
        alert(data.message || '加载 3x-ui 客户端失败');
        return;
    }
    const responseIncludesInbounds = data.include_inbounds !== false;
    currentUserXuiState = {
        clients: data.clients || [],
        backends: data.backends || [],
        inbounds: responseIncludesInbounds ? (data.inbounds || []) : (currentUserXuiState.inbounds || []),
        selectedBackendId: data.selected_backend_id || null
    };
    renderUserXuiBackendOptions(currentUserXuiState.backends, currentUserXuiState.selectedBackendId);
    if (responseIncludesInbounds) {
        renderUserXuiInbounds(currentUserXuiState.inbounds, data.inbound_error || '');
    }
    renderUserXuiClients(currentUserXuiState.clients);
}

async function loadUserXuiBackendInbounds() {
    if (!currentUserId) return;
    const backendId = document.getElementById('userXuiBackendSelect')?.value || '';
    await loadUserXuiClientData(currentUserId, { sync: false, backendId, includeInbounds: true });
}

function userQuickTimestamp() {
    const date = new Date();
    const pad = number => String(number).padStart(2, '0');
    return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}`;
}

function userQuickDefaultInboundName() {
    const username = currentUserNodeUsername || 'user';
    return `${username}-${userQuickTimestamp()}`;
}

function selectedUserQuickBackendId() {
    return Number(
        document.getElementById('userQuickXuiBackendSelect')?.value
        || currentUserXuiState.selectedBackendId
        || xuiDefaultInboundBackendId()
        || 0
    );
}

function initUserQuickInboundForm(forceRender = false) {
    const backendId = selectedUserQuickBackendId();
    if (!backendId) return;

    const nameInput = document.getElementById('userQuickInboundName');
    if (nameInput && !nameInput.value.trim()) nameInput.value = userQuickDefaultInboundName();

    const portInput = document.getElementById('userQuickInboundPort');
    if (portInput && !portInput.value) {
        userQuickAutoPort = randomXuiInboundPort(backendId);
        portInput.value = String(userQuickAutoPort);
    }

    const protocol = document.getElementById('userQuickInboundProtocol');
    if (protocol && !protocol.value) protocol.value = 'vless';
    const network = document.getElementById('userQuickInboundNetwork');
    if (network && !network.value) network.value = 'tcp';
    const security = document.getElementById('userQuickInboundSecurity');
    if (security && !security.value) security.value = 'none';

    const mount = document.getElementById(xuiInboundMountId(USER_QUICK_INBOUND_PREFIX));
    if (mount && (forceRender || !mount.innerHTML.trim())) {
        xuiInboundEditorStates[USER_QUICK_INBOUND_PREFIX] = {
            activeTab: 'base',
            mode: 'add',
            inbound: null,
            backendId
        };
        renderXuiInboundEditor(USER_QUICK_INBOUND_PREFIX);
    } else {
        xuiInboundEditorStates[USER_QUICK_INBOUND_PREFIX] = {
            ...(xuiInboundEditorStates[USER_QUICK_INBOUND_PREFIX] || {}),
            backendId
        };
    }

    syncUserQuickFieldsToEditor();
    const advanced = document.getElementById('userQuickAdvancedConfig');
    if (advanced) advanced.style.display = userQuickAdvancedOpen ? 'block' : 'none';
}

function handleUserQuickBackendChange() {
    const backendId = selectedUserQuickBackendId();
    const portInput = document.getElementById('userQuickInboundPort');
    if (portInput && (!portInput.value || Number(portInput.value) === Number(userQuickAutoPort || 0))) {
        userQuickAutoPort = randomXuiInboundPort(backendId);
        portInput.value = String(userQuickAutoPort);
    }
    initUserQuickInboundForm(true);
}

function randomizeUserQuickInboundPort() {
    const backendId = selectedUserQuickBackendId();
    if (!backendId) {
        alert('请先选择 3x-ui 后端');
        return;
    }
    userQuickAutoPort = randomXuiInboundPort(backendId);
    const portInput = document.getElementById('userQuickInboundPort');
    if (portInput) portInput.value = String(userQuickAutoPort);
    syncUserQuickFieldsToEditor();
}

function toggleUserQuickFullConfig(forceOpen) {
    userQuickAdvancedOpen = typeof forceOpen === 'boolean' ? forceOpen : !userQuickAdvancedOpen;
    initUserQuickInboundForm();
    const advanced = document.getElementById('userQuickAdvancedConfig');
    if (advanced) advanced.style.display = userQuickAdvancedOpen ? 'block' : 'none';
    const button = document.getElementById('userQuickAdvancedToggle');
    if (button) button.textContent = userQuickAdvancedOpen ? '收起完整配置' : '展开完整配置';
}

function syncUserQuickFieldsToEditor() {
    const prefix = USER_QUICK_INBOUND_PREFIX;
    const mount = document.getElementById(xuiInboundMountId(prefix));
    if (!mount || !mount.innerHTML.trim()) return;

    const backendId = selectedUserQuickBackendId();
    const fieldValues = {
        BackendId: backendId,
        Remark: document.getElementById('userQuickInboundName')?.value.trim() || '',
        Port: document.getElementById('userQuickInboundPort')?.value || '',
        Protocol: document.getElementById('userQuickInboundProtocol')?.value || 'vless',
        Network: document.getElementById('userQuickInboundNetwork')?.value || 'tcp',
        Security: document.getElementById('userQuickInboundSecurity')?.value || 'none',
        TotalGb: document.getElementById('userQuickInboundTotalGb')?.value || '0',
        ExpiryTime: document.getElementById('userQuickInboundExpiry')?.value || '',
        Reset: document.getElementById('userQuickInboundReset')?.value || '0'
    };

    Object.entries(fieldValues).forEach(([field, value]) => {
        const input = xuiInboundField(prefix, field);
        if (input) input.value = value;
    });
    const enableInput = xuiInboundField(prefix, 'Enable');
    if (enableInput) enableInput.checked = true;

    xuiInboundEditorStates[prefix] = {
        ...(xuiInboundEditorStates[prefix] || {}),
        backendId
    };
    refreshXuiInboundEditor(prefix);
    const actualSecurity = xuiInboundField(prefix, 'Security')?.value || 'none';
    const quickSecurity = document.getElementById('userQuickInboundSecurity');
    if (quickSecurity && quickSecurity.value !== actualSecurity) {
        quickSecurity.value = actualSecurity;
    }
    updateXuiInboundAdvancedPreview(prefix, false);
}

function validateUserQuickInboundPayload(payload) {
    const protocol = String(payload.protocol || '').toLowerCase();
    const network = String(payload.streamSettings?.network || 'tcp').toLowerCase();
    if (!USER_XUI_SUBSCRIPTION_PROTOCOLS.has(protocol)) {
        alert(`协议 ${protocol || 'unknown'} 暂不支持生成用户订阅`);
        return false;
    }
    if (!USER_XUI_SUBSCRIPTION_NETWORKS.has(network)) {
        alert(`传输 ${network || 'unknown'} 暂不支持生成用户订阅`);
        return false;
    }
    return true;
}

async function createInboundForCurrentUser() {
    if (!currentUserId) return;
    const backendId = selectedUserQuickBackendId();
    const inboundTotalGb = Number(document.getElementById('userQuickInboundTotalGb')?.value || 0);
    const limitIp = Number(document.getElementById('userQuickClientLimitIp')?.value || 0);
    const submitButton = document.getElementById('userQuickCreateBtn');

    if (!backendId) {
        alert('请选择 3x-ui 后端');
        return;
    }
    if (inboundTotalGb < 0 || limitIp < 0) {
        alert('数值不能小于 0');
        return;
    }

    initUserQuickInboundForm();
    syncUserQuickFieldsToEditor();
    const payload = collectXuiInboundPayload(USER_QUICK_INBOUND_PREFIX);
    if (!payload || !payload.inbound_payload) return;
    if (!validateUserQuickInboundPayload(payload.inbound_payload)) return;

    try {
        if (submitButton) submitButton.disabled = true;
        const response = await fetch(`/api/users/${currentUserId}/xui-clients/create-inbound`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                backend_id: backendId,
                inbound_payload: payload.inbound_payload,
                client: {
                    limit_ip: limitIp,
                    comment: document.getElementById('userQuickClientComment')?.value.trim() || '',
                    enable: document.getElementById('userQuickClientEnable')?.checked !== false
                }
            })
        });
        const data = await response.json();
        if (!data.success) {
            alert('创建失败: ' + (data.message || '未知错误'));
            return;
        }

        resetUserNodeCreateForm();
        await loadUserXuiClientData(currentUserId, { sync: false, backendId });
        loadUsers();

        delete xuiInboundGroups[String(backendId)];
        delete xuiClientGroups[String(backendId)];
        setCurrentXuiBackendId(backendId);
        xuiExpandedInboundBackends.add(Number(backendId));
        await loadXuiInbounds(backendId, { expand: true, withClients: false });
        await loadXuiClients(backendId);
    } catch (error) {
        alert('创建失败: ' + error.message);
    } finally {
        if (submitButton) submitButton.disabled = false;
    }
}

async function refreshUserXuiClients() {
    if (!currentUserId) return;
    try {
        const response = await fetch(`/api/users/${currentUserId}/xui-clients/sync`, { method: 'POST' });
        const data = await response.json();
        if (!data.success) {
            alert(data.message || '同步失败');
            return;
        }
        await loadUserXuiClientData(currentUserId, { sync: false, includeInbounds: userNodeCreateMode === 'existing' });
        loadUsers();
    } catch (error) {
        alert('同步失败: ' + error.message);
    }
}

async function createNodeForCurrentUser() {
    if (!currentUserId) return;

    const backendId = Number(document.getElementById('userXuiBackendSelect')?.value || 0);
    const inboundIds = Array.from(document.querySelectorAll('#userXuiInboundSelection .user-xui-inbound-checkbox:checked'))
        .map(item => Number(item.value))
        .filter(Boolean);
    const trafficLimitValue = document.getElementById('userNodeCreateLimitGb').value;
    const trafficLimitGb = trafficLimitValue === '' ? null : Number(trafficLimitValue || 0);
    const expiryTime = userNodeMsFromDateTimeLocal(document.getElementById('userNodeCreateExpiry').value || '');
    const resetValue = document.getElementById('userNodeCreateReset')?.value ?? '';
    const limitIp = Number(document.getElementById('userXuiLimitIp').value || 0);
    const comment = document.getElementById('userXuiComment').value.trim();

    if (!backendId) {
        alert('请选择 3x-ui 后端');
        return;
    }
    if (!inboundIds.length) {
        alert('请选择至少一个入站');
        return;
    }
    if ((trafficLimitGb !== null && trafficLimitGb < 0) || limitIp < 0) {
        alert('数值不能小于 0');
        return;
    }

    try {
        const requestBody = {
            backend_id: backendId,
            inbound_ids: inboundIds,
            limit_ip: limitIp,
            comment,
            enable: document.getElementById('userXuiEnable')?.checked !== false
        };
        if (trafficLimitGb !== null) requestBody.total_gb = trafficLimitGb;
        if (expiryTime) requestBody.expiry_time = expiryTime;
        if (resetValue !== '') requestBody.reset = Number(resetValue);

        const response = await fetch(`/api/users/${currentUserId}/xui-clients`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        const data = await response.json();
        if (!data.success) {
            alert('创建失败: ' + (data.message || '未知错误'));
            return;
        }

        resetUserNodeCreateForm();
        await loadUserXuiClientData(currentUserId, { sync: false, backendId });
        loadUsers();
    } catch (error) {
        alert('创建失败: ' + error.message);
    }
}

async function showAssignUserNodesModal(userId, username) {
    currentUserId = userId;
    currentUserNodeUsername = username || '';
    document.getElementById('assignNodeUserName').textContent = username;
    resetUserNodeCreateForm();
    document.getElementById('assignUserNodesModal').style.display = 'block';
    await loadUserXuiClientData(userId, { sync: false, includeInbounds: false });
}

function toggleUserNodeRow(nodeId) {
    return nodeId;
}

function clearUserNodeSelection() {
    document.querySelectorAll('#userXuiInboundSelection .user-xui-inbound-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });
}

async function updateUserXuiClient(clientId) {
    if (!currentUserId) {
        alert('当前用户状态已失效，请重新打开管理节点窗口');
        return;
    }
    const card = document.querySelector(`[data-user-xui-client-id="${clientId}"]`);
    if (!card) {
        alert('没有找到这个客户端卡片，请刷新后重试');
        return;
    }
    const actionButton = card.querySelector(`[data-user-xui-save-button="${clientId}"]`);
    const originalButtonText = actionButton?.textContent || '保存到 3x-ui';
    const trafficLimitGb = Number(card.querySelector('.user-node-limit')?.value || 0);
    const limitIp = Number(card.querySelector('.user-xui-limit-ip')?.value || 0);
    if (trafficLimitGb < 0 || limitIp < 0) {
        alert('数值不能小于 0');
        return;
    }
    try {
        if (actionButton) {
            actionButton.disabled = true;
            actionButton.textContent = '保存中...';
        }
        const response = await fetch(`/api/users/${currentUserId}/xui-clients/${clientId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                total_gb: trafficLimitGb,
                expiry_time: userNodeMsFromDateTimeLocal(card.querySelector('.user-node-expiry')?.value || ''),
                reset: Number(card.querySelector('.user-node-reset')?.value || 0),
                limit_ip: limitIp,
                comment: card.querySelector('.user-xui-comment')?.value.trim() || '',
                display_name: card.querySelector('.user-xui-display-name')?.value.trim() || '',
                enable: card.querySelector('.user-xui-enable')?.checked === true
            })
        });
        let data;
        try {
            data = await response.json();
        } catch (parseError) {
            throw new Error(`HTTP ${response.status}: ${response.statusText || '响应不是 JSON'}`);
        }
        if (!response.ok || !data.success) {
            alert('保存失败: ' + (data.message || '未知错误'));
            return;
        }
        const backendId = currentUserXuiState.clients.find(client => Number(client.id) === Number(clientId))?.backend_id || '';
        await loadUserXuiClientData(currentUserId, { sync: false, backendId });
        loadUsers();
        alert('保存成功');
    } catch (error) {
        alert('保存失败: ' + error.message);
    } finally {
        if (actionButton) {
            actionButton.disabled = false;
            actionButton.textContent = originalButtonText;
        }
    }
}

async function deleteUserXuiClient(clientId) {
    if (!currentUserId) return;
    if (!confirm('确认删除这个 3x-ui 入站节点及其客户端吗？')) return;
    try {
        const response = await fetch(`/api/users/${currentUserId}/xui-clients/${clientId}`, { method: 'DELETE' });
        const data = await response.json();
        if (!data.success) {
            alert('删除失败: ' + (data.message || '未知错误'));
            return;
        }
        await loadUserXuiClientData(currentUserId, { sync: false });
        loadUsers();
    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}

async function saveUserNodes() {
    closeModal('assignUserNodesModal');
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

function truncateUrl(url, maxLength = 50) {
    if (url.length <= maxLength) return url;
    return url.substring(0, maxLength) + '...';
}

async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
    } catch (error) {
        // 降级方案
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
    }
}

// ============ 3x-ui 后端对接 ============

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeJs(value) {
    return String(value ?? '')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '');
}

function formatBytes(bytes) {
    const value = Number(bytes || 0);
    if (!value) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    let size = Math.abs(value);
    let index = 0;
    while (size >= 1024 && index < units.length - 1) {
        size /= 1024;
        index += 1;
    }
    const formatted = size >= 100 || index === 0 ? size.toFixed(0) : size.toFixed(1);
    return `${value < 0 ? '-' : ''}${formatted} ${units[index]}`;
}

function normalizeXuiTimestamp(value) {
    const timestamp = Number(value || 0);
    if (!timestamp) return 0;
    return timestamp < 1000000000000 ? timestamp * 1000 : timestamp;
}

function formatXuiExpiry(value) {
    const timestamp = normalizeXuiTimestamp(value);
    if (!timestamp) return '不限期';
    const diff = timestamp - Date.now();
    const dateText = new Date(timestamp).toLocaleString();
    if (diff <= 0) return `${dateText}（已过期）`;
    const days = Math.ceil(diff / 86400000);
    return `${dateText}（剩余 ${days} 天）`;
}

function xuiDaysFromExpiry(value) {
    const timestamp = normalizeXuiTimestamp(value);
    if (!timestamp) return 0;
    return Math.max(0, Math.ceil((timestamp - Date.now()) / 86400000));
}

function xuiBytesToGb(bytes) {
    const value = Number(bytes || 0);
    if (!value) return 0;
    return Number((value / 1024 / 1024 / 1024).toFixed(2));
}

function getSelectedNumberValues(selectId) {
    const select = document.getElementById(selectId);
    return Array.from(select.selectedOptions).map(option => Number(option.value)).filter(Boolean);
}

function setXuiTableMessage(tableId, colspan, message) {
    const tbody = document.querySelector(`#${tableId} tbody`);
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="${colspan}" style="text-align: center; color: #999;">${escapeHtml(message)}</td></tr>`;
    } else if (tableId === 'xui-inbounds-table') {
        setXuiInboundGroupsMessage(message);
    }
}

function toggleXuiAuthFields() {
    const authMode = document.getElementById('xuiAuthMode').value;
    document.getElementById('xuiTokenFields').style.display = authMode === 'token' ? 'block' : 'none';
    document.getElementById('xuiPasswordFields').style.display = authMode === 'password' ? 'block' : 'none';
}

function getStoredXuiBackendId() {
    const stored = localStorage.getItem('xuiBackendId');
    return stored ? Number(stored) : null;
}

function setCurrentXuiBackendId(backendId) {
    currentXuiBackendId = backendId ? Number(backendId) : null;
    if (currentXuiBackendId) {
        localStorage.setItem('xuiBackendId', String(currentXuiBackendId));
    } else {
        localStorage.removeItem('xuiBackendId');
    }
}

function getCurrentXuiBackend() {
    return xuiBackends.find(backend => Number(backend.id) === Number(currentXuiBackendId)) || null;
}

function removeXuiBackendToolbar() {
    document.querySelectorAll('.xui-backend-toolbar').forEach(toolbar => toolbar.remove());
}

function renderXuiBackendCards() {
    const container = document.getElementById('xui-backend-cards');
    if (!container) return;
    container.innerHTML = '';

    if (!xuiBackends.length) {
        container.innerHTML = '<div class="xui-empty-state">暂无后端，点击右上角新增后端</div>';
        return;
    }

    xuiBackends.forEach(backend => {
        const status = xuiBackendStatuses[backend.id] || {};
        const statusData = status.status || {};
        const cpu = getXuiCpuPercent(statusData);
        const mem = getXuiUsagePercent(statusData.mem);
        const disk = getXuiUsagePercent(statusData.disk);
        const net = statusData.netIO || statusData.netIo || {};
        const isCurrent = Number(backend.id) === Number(currentXuiBackendId);
        const stateClass = !backend.configured ? 'badge-secondary' : status.online ? 'badge-success' : status.loaded ? 'badge-danger' : 'badge-info';
        const stateText = !backend.configured ? '未配置' : status.online ? '在线' : status.loaded ? '离线' : '检测中';

        const card = document.createElement('div');
        card.className = `xui-backend-card${isCurrent ? ' active' : ''}`;
        card.onclick = () => selectXuiBackend(backend.id);
        card.innerHTML = `
            <div class="xui-card-header">
                <div class="xui-card-icon">🔌</div>
                <div class="xui-card-title">
                    <strong>${escapeHtml(backend.name || ('后端 ' + backend.id))}</strong>
                    <span>${escapeHtml(backend.base_url || '未填写地址')}</span>
                    <span>订阅地址：${escapeHtml(backend.public_host || '自动提取')}</span>
                </div>
                <span class="badge ${stateClass}">${stateText}</span>
            </div>
            <div class="xui-card-metrics">
                ${renderXuiRing('CPU', cpu, `${cpu.toFixed(1)}%`)}
                ${renderXuiRing('RAM', mem, formatMemoryText(statusData.mem))}
                ${renderXuiRing('Disk', disk, formatMemoryText(statusData.disk))}
            </div>
            <div class="xui-card-lines">
                <div><span>网络</span><strong><span class="xui-up">↑ ${formatBytes(net.up || 0)}/s</span> <span class="xui-down">↓ ${formatBytes(net.down || 0)}/s</span></strong></div>
                <div><span>Xray</span><strong>${escapeHtml(statusData.xray?.state || '-')}</strong></div>
                <div><span>认证</span><strong>${backend.auth_mode === 'password' ? '用户名密码' : 'API Token'}</strong></div>
            </div>
            <div class="xui-card-actions" onclick="event.stopPropagation()">
                <button class="btn btn-secondary btn-small" onclick="showXuiBackendModal(${backend.id})">编辑</button>
                <button class="btn btn-info btn-small" onclick="testXuiBackendCard(${backend.id})">测试</button>
                <button class="btn btn-danger btn-small" onclick="deleteXuiBackend(${backend.id})">删除</button>
            </div>
        `;
        container.appendChild(card);
    });

}

function renderXuiRing(label, percent, subText) {
    const value = Math.max(0, Math.min(100, Number(percent || 0)));
    return `
        <div class="xui-ring" style="--value:${value};">
            <div class="xui-ring-circle"><span>${Math.round(value)}%</span></div>
            <strong>${label}</strong>
            <small>${escapeHtml(subText || '')}</small>
        </div>
    `;
}

function getXuiCpuPercent(status) {
    return Math.max(0, Math.min(100, Number(status?.cpu || 0)));
}

function getXuiUsagePercent(metric) {
    if (!metric || !metric.total) return 0;
    return Math.max(0, Math.min(100, Number(metric.current || 0) / Number(metric.total) * 100));
}

function formatMemoryText(metric) {
    if (!metric || !metric.total) return '-';
    return `${formatBytes(metric.current || 0)} / ${formatBytes(metric.total || 0)}`;
}

function fillXuiSettingsForm(settings) {
    xuiSettings = settings || {};
    document.getElementById('xuiBackendName').value = xuiSettings.name || '';
    document.getElementById('xuiBaseUrl').value = xuiSettings.base_url || '';
    document.getElementById('xuiPublicHost').value = xuiSettings.public_host || '';
    document.getElementById('xuiAuthMode').value = xuiSettings.auth_mode || 'token';
    document.getElementById('xuiUsername').value = xuiSettings.username || '';
    document.getElementById('xuiApiToken').value = '';
    document.getElementById('xuiPassword').value = '';
    document.getElementById('xuiVerifySsl').checked = xuiSettings.verify_ssl !== false;
    document.getElementById('xuiTimeout').value = xuiSettings.timeout || 15;
    toggleXuiAuthFields();

    const hint = document.getElementById('xuiConfigHint');
    if (!xuiSettings.id) {
        if (hint) hint.textContent = '请先新增一个 3x-ui 后端。';
        return;
    }

    const secretText = xuiSettings.auth_mode === 'password'
        ? (xuiSettings.has_password ? '已保存密码' : '未保存密码')
        : (xuiSettings.has_api_token ? '已保存 API Token' : '未保存 API Token');
    if (hint) {
        hint.textContent = xuiSettings.updated_at
            ? `${secretText}，最后更新：${xuiSettings.updated_at}`
            : secretText;
    }
}

function isXuiTabActive() {
    const tab = document.getElementById('xui-tab');
    return !!tab && tab.classList.contains('active');
}

function updateXuiAutoRefreshLabel() {
}

function startXuiStatusAutoRefresh() {
    if (xuiStatusRefreshTimer) return;
    xuiStatusRefreshTimer = window.setInterval(refreshXuiBackendStatusesAuto, XUI_STATUS_REFRESH_MS);
    updateXuiAutoRefreshLabel();
}

function stopXuiStatusAutoRefresh() {
    if (xuiStatusRefreshTimer) {
        window.clearInterval(xuiStatusRefreshTimer);
        xuiStatusRefreshTimer = null;
    }
    updateXuiAutoRefreshLabel();
}

function syncXuiStatusAutoRefresh() {
    if (isXuiTabActive() && !document.hidden) {
        startXuiStatusAutoRefresh();
        refreshXuiBackendStatusesAuto();
    } else {
        stopXuiStatusAutoRefresh();
    }
}

async function refreshXuiBackendStatusesAuto() {
    if (!isXuiTabActive() || document.hidden || xuiStatusRefreshInFlight) return;
    if (!xuiBackends.length) {
        updateXuiAutoRefreshLabel();
        return;
    }

    xuiStatusRefreshInFlight = true;
    try {
        await loadXuiBackendStatuses();
        xuiLastStatusRefreshAt = new Date();
    } finally {
        xuiStatusRefreshInFlight = false;
        updateXuiAutoRefreshLabel();
    }
}

async function loadXuiDashboard() {
    try {
        const response = await fetch('/api/xui/backends');
        const data = await response.json();
        xuiBackends = data.backends || [];

        const storedId = getStoredXuiBackendId();
        const selectedBackend = xuiBackends.find(backend => Number(backend.id) === Number(currentXuiBackendId))
            || xuiBackends.find(backend => Number(backend.id) === Number(storedId))
            || xuiBackends[0]
            || null;
        setCurrentXuiBackendId(selectedBackend ? selectedBackend.id : null);
        syncCurrentXuiInboundsFromGroup();
        syncCurrentXuiClientsFromGroup();
        renderXuiBackendCards();
        renderXuiInboundGroups();

        await loadXuiBackendStatuses();
        xuiLastStatusRefreshAt = new Date();
        updateXuiAutoRefreshLabel();

        if (!selectedBackend) {
            updateXuiStatusOffline('请先新增一个 3x-ui 后端');
            setXuiTableMessage('xui-inbounds-table', 8, '请先新增一个 3x-ui 后端');
            renderXuiBackendCards();
            return;
        }

        if (!selectedBackend.configured) {
            updateXuiStatusOffline('当前后端还未配置完整');
            renderXuiInboundGroups();
            renderXuiBackendCards();
            return;
        }

        await Promise.all([
            loadXuiServerStatus(),
            loadXuiInbounds(currentXuiBackendId, { withClients: false }),
            loadXuiClients()
        ]);
    } catch (error) {
        updateXuiStatusOffline(error.message);
        setXuiTableMessage('xui-inbounds-table', 8, '加载 3x-ui 配置失败');
    }
}

async function loadXuiBackendStatuses() {
    const configuredBackends = xuiBackends.filter(backend => backend.configured);
    await Promise.all(configuredBackends.map(async backend => {
        await fetchXuiBackendStatus(backend.id);
    }));
    renderXuiBackendCards();
    renderXuiInboundGroups();
}

async function fetchXuiBackendStatus(backendId) {
    try {
        const response = await fetch(`/api/xui/server/status?backend_id=${encodeURIComponent(backendId)}`);
        const data = await response.json();
        xuiBackendStatuses[backendId] = {
            loaded: true,
            online: !!data.online,
            status: data.status || {},
            message: data.message || ''
        };
        return xuiBackendStatuses[backendId];
    } catch (error) {
        xuiBackendStatuses[backendId] = {
            loaded: true,
            online: false,
            status: {},
            message: error.message
        };
        return xuiBackendStatuses[backendId];
    }
}

function collectXuiBackendPayload() {
    return {
        name: document.getElementById('xuiBackendName').value.trim(),
        base_url: document.getElementById('xuiBaseUrl').value.trim(),
        public_host: document.getElementById('xuiPublicHost').value.trim(),
        auth_mode: document.getElementById('xuiAuthMode').value,
        username: document.getElementById('xuiUsername').value.trim(),
        password: document.getElementById('xuiPassword').value,
        api_token: document.getElementById('xuiApiToken').value.trim(),
        verify_ssl: document.getElementById('xuiVerifySsl').checked,
        timeout: Number(document.getElementById('xuiTimeout').value || 15)
    };
}

function markXuiBackendDraftDirty() {
    const modal = document.getElementById('xuiBackendModal');
    if (!modal || modal.style.display !== 'block') return;

    xuiBackendDraftTested = false;
    const confirmBtn = document.getElementById('xuiBackendConfirmBtn');
    if (confirmBtn) confirmBtn.disabled = true;

    const hint = document.getElementById('xuiBackendTestHint');
    if (hint && !hint.classList.contains('loading')) {
        setXuiBackendTestHint('配置已变更，请重新测试连接。', 'idle');
    }
}

function bindXuiBackendDraftDirtyHandlers() {
    [
        'xuiBackendName',
        'xuiTimeout',
        'xuiBaseUrl',
        'xuiPublicHost',
        'xuiAuthMode',
        'xuiApiToken',
        'xuiUsername',
        'xuiPassword',
        'xuiVerifySsl'
    ].forEach(id => {
        const element = document.getElementById(id);
        if (!element) return;
        const eventName = element.type === 'checkbox' || element.tagName === 'SELECT' ? 'change' : 'input';
        element.addEventListener(eventName, markXuiBackendDraftDirty);
    });
}

function ensureXuiBackendSelected() {
    if (!currentXuiBackendId) {
        alert('请先选择或新增一个 3x-ui 后端');
        return false;
    }
    return true;
}

async function selectXuiBackend(backendId) {
    setCurrentXuiBackendId(backendId || null);
    const backend = getCurrentXuiBackend();
    syncCurrentXuiInboundsFromGroup();
    syncCurrentXuiClientsFromGroup();
    renderXuiBackendCards();
    renderXuiInboundGroups();

    if (!backend || !backend.configured) {
        updateXuiStatusOffline(backend ? '当前后端还未配置完整' : '请先新增一个 3x-ui 后端');
        renderXuiInboundGroups();
        return;
    }

    await Promise.all([
        loadXuiServerStatus(),
        loadXuiInbounds(currentXuiBackendId, { withClients: false }),
        loadXuiClients()
    ]);
}

function showXuiBackendModal(backendId = null) {
    const backend = backendId ? xuiBackends.find(item => Number(item.id) === Number(backendId)) : null;
    xuiBackendModalMode = backend ? 'edit' : 'create';
    xuiEditingBackendId = backend ? backend.id : null;
    xuiBackendDraftTested = false;

    document.getElementById('xuiBackendModalTitle').textContent = backend ? '编辑 3x-ui 后端' : '新增 3x-ui 后端';
    fillXuiSettingsForm(backend || {
        name: '',
        base_url: '',
        public_host: '',
        auth_mode: 'token',
        username: '',
        verify_ssl: true,
        timeout: 15
    });
    setXuiBackendTestHint('请先填写信息并测试连接。', 'idle');
    document.getElementById('xuiBackendConfirmBtn').disabled = true;
    document.getElementById('xuiBackendModal').style.display = 'block';
}

function setXuiBackendTestHint(message, state = 'idle') {
    const hint = document.getElementById('xuiBackendTestHint');
    if (!hint) return;
    hint.className = `xui-test-hint ${state}`;
    hint.textContent = message;
}

function formatXuiBackendTestError(message) {
    const text = String(message || '连接失败，请检查配置。');
    if (/CERTIFICATE_VERIFY_FAILED|SSLCertVerificationError|self-signed|证书校验失败|自签/i.test(text)) {
        return 'HTTPS 证书校验失败。这个后端使用自签证书时，请关闭 HTTPS 证书验证后重新测试连接。';
    }
    return text;
}

async function testXuiBackendDraft() {
    const payload = collectXuiBackendPayload();
    if (xuiEditingBackendId) {
        payload.backend_id = xuiEditingBackendId;
    }

    if (!payload.name) {
        setXuiBackendTestHint('请填写后端名称。', 'error');
        return;
    }
    if (!payload.base_url) {
        setXuiBackendTestHint('请填写 3x-ui 面板地址。', 'error');
        return;
    }

    xuiBackendDraftTested = false;
    document.getElementById('xuiBackendConfirmBtn').disabled = true;
    setXuiBackendTestHint('正在测试连接...', 'loading');

    try {
        const response = await fetch('/api/xui/backends/test-draft', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.success) {
            xuiBackendDraftTested = true;
            document.getElementById('xuiBackendConfirmBtn').disabled = false;
            setXuiBackendTestHint('连接成功，可以确认保存。', 'success');
            return;
        }
        setXuiBackendTestHint(formatXuiBackendTestError(data.message), 'error');
    } catch (error) {
        setXuiBackendTestHint(formatXuiBackendTestError('连接失败: ' + error.message), 'error');
    }
}

async function confirmXuiBackend() {
    if (!xuiBackendDraftTested) {
        alert('请先测试连接成功后再确认保存');
        return;
    }

    if (xuiBackendModalMode === 'edit') {
        await saveXuiBackend();
    } else {
        await createXuiBackend();
    }
}

async function createXuiBackend() {
    const payload = collectXuiBackendPayload();

    if (!payload.name) {
        alert('请填写后端名称');
        return;
    }
    if (!payload.base_url) {
        alert('请填写 3x-ui 面板地址');
        return;
    }

    try {
        const response = await fetch('/api/xui/backends', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!data.success) {
            alert('新增失败: ' + (data.message || '未知错误'));
            return;
        }
        setCurrentXuiBackendId(data.backend.id);
        closeModal('xuiBackendModal');
        await loadXuiDashboard();
    } catch (error) {
        alert('新增失败: ' + error.message);
    }
}

async function saveXuiBackend() {
    const backendId = xuiEditingBackendId || currentXuiBackendId;
    if (!backendId) {
        alert('请先选择或新增一个 3x-ui 后端');
        return;
    }
    const payload = collectXuiBackendPayload();

    if (!payload.name) {
        alert('请填写后端名称');
        return;
    }
    if (!payload.base_url) {
        alert('请填写 3x-ui 面板地址');
        return;
    }

    try {
        const response = await fetch(`/api/xui/backends/${backendId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!data.success) {
            alert('保存失败: ' + (data.message || '未知错误'));
            return;
        }
        delete xuiInboundGroups[String(backendId)];
        delete xuiClientGroups[String(backendId)];
        xuiExpandedInboundBackends.delete(Number(backendId));
        setCurrentXuiBackendId(backendId);
        closeModal('xuiBackendModal');
        await loadXuiDashboard();
    } catch (error) {
        alert('保存失败: ' + error.message);
    }
}

async function saveXuiSettings() {
    await saveXuiBackend();
}

async function deleteSelectedXuiBackend() {
    if (!ensureXuiBackendSelected()) return;
    await deleteXuiBackend(currentXuiBackendId);
}

async function deleteXuiBackend(backendId) {
    const targetBackendId = Number(backendId);
    if (!targetBackendId) return;

    const backend = xuiBackends.find(item => Number(item.id) === targetBackendId);
    const name = backend ? (backend.name || `后端 ${targetBackendId}`) : `后端 ${targetBackendId}`;
    if (!confirm(`确定要删除 3x-ui 后端“${name}”吗？本操作只删除本系统里的连接配置，不会删除远程 3x-ui 数据。`)) return;

    try {
        const response = await fetch(`/api/xui/backends/${targetBackendId}`, { method: 'DELETE' });
        const data = await response.json();
        if (data.success) {
            delete xuiBackendStatuses[targetBackendId];
            delete xuiInboundGroups[String(targetBackendId)];
            delete xuiClientGroups[String(targetBackendId)];
            xuiExpandedInboundBackends.delete(targetBackendId);
            if (Number(currentXuiBackendId) === targetBackendId) {
                setCurrentXuiBackendId(null);
            }
            await loadXuiDashboard();
        } else {
            alert('删除失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}

async function testXuiBackendCard(backendId) {
    const targetBackendId = Number(backendId);
    const backend = xuiBackends.find(item => Number(item.id) === targetBackendId);
    if (!backend) return;

    if (!backend.configured) {
        alert('请先编辑该后端，测试成功并确认保存。');
        showXuiBackendModal(targetBackendId);
        return;
    }

    xuiBackendStatuses[targetBackendId] = {
        loaded: false,
        online: false,
        status: {},
        message: '检测中'
    };
    renderXuiBackendCards();

    const status = await fetchXuiBackendStatus(targetBackendId);
    renderXuiBackendCards();

    if (Number(currentXuiBackendId) === targetBackendId) {
        if (status.online) {
            updateXuiStatus({ success: true, online: true, status: status.status || {} });
        } else {
            updateXuiStatusOffline(status.message || '连接失败');
        }
    }

    alert(status.online ? '3x-ui 连接成功' : `连接失败: ${status.message || '未知错误'}`);
}

async function testXuiConnection() {
    if (!ensureXuiBackendSelected()) return;

    try {
        const response = await fetch(`/api/xui/backends/${currentXuiBackendId}/test`, { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            updateXuiStatus({ success: true, online: true, status: data.status || {} });
            alert('✅ 3x-ui 连接成功');
        } else {
            updateXuiStatusOffline(data.message || '连接失败');
            alert('❌ ' + (data.message || '连接失败'));
        }
    } catch (error) {
        updateXuiStatusOffline(error.message);
        alert('连接失败: ' + error.message);
    }
}

function updateXuiStatusOffline(message) {
    if (currentXuiBackendId) {
        xuiBackendStatuses[currentXuiBackendId] = {
            loaded: true,
            online: false,
            status: {},
            message: message || ''
        };
    }

    const onlineEl = document.getElementById('xui-online-state');
    const cpuEl = document.getElementById('xui-cpu-load');
    const memoryEl = document.getElementById('xui-memory-usage');
    const xrayEl = document.getElementById('xui-xray-state');
    if (onlineEl) {
        onlineEl.textContent = '离线';
        onlineEl.title = message || '';
    }
    if (cpuEl) cpuEl.textContent = '-';
    if (memoryEl) memoryEl.textContent = '-';
    if (xrayEl) xrayEl.textContent = '-';

    renderXuiBackendCards();
    renderXuiInboundGroups();
}

function updateXuiStatus(data) {
    if (!data.success || !data.online) {
        updateXuiStatusOffline(data.message || '离线');
        return;
    }

    const status = data.status || {};
    const load = status.load || {};
    const memory = status.mem || {};
    const xray = status.xray || {};
    const cpu = Number(status.cpu || 0);
    const loadText = load.load1 !== undefined ? ` / ${Number(load.load1).toFixed(2)}` : '';
    const memoryPercent = memory.total ? Math.round((memory.current || 0) / memory.total * 100) : 0;

    if (currentXuiBackendId) {
        xuiBackendStatuses[currentXuiBackendId] = {
            loaded: true,
            online: true,
            status,
            message: ''
        };
    }

    const onlineEl = document.getElementById('xui-online-state');
    const cpuEl = document.getElementById('xui-cpu-load');
    const memoryEl = document.getElementById('xui-memory-usage');
    const xrayEl = document.getElementById('xui-xray-state');
    if (onlineEl) {
        onlineEl.textContent = '在线';
        onlineEl.title = '';
    }
    if (cpuEl) cpuEl.textContent = `${cpu.toFixed(1)}%${loadText}`;
    if (memoryEl) memoryEl.textContent = memory.total ? `${memoryPercent}%` : '-';
    if (xrayEl) xrayEl.textContent = xray.state || '-';

    renderXuiBackendCards();
    renderXuiInboundGroups();
}

function xuiBackendQuery() {
    return xuiBackendQueryFor(currentXuiBackendId);
}

async function loadXuiServerStatus() {
    const response = await fetch(`/api/xui/server/status?${xuiBackendQuery()}`);
    const data = await response.json();
    updateXuiStatus(data);
}

function xuiBackendQueryFor(backendId) {
    const targetBackendId = backendId || currentXuiBackendId;
    if (!targetBackendId) {
        throw new Error('请先选择一个 3x-ui 后端');
    }
    return `backend_id=${encodeURIComponent(targetBackendId)}`;
}

function getXuiInboundGroup(backendId) {
    const key = String(backendId);
    if (!xuiInboundGroups[key]) {
        xuiInboundGroups[key] = {
            loaded: false,
            loading: false,
            error: '',
            inbounds: []
        };
    }
    return xuiInboundGroups[key];
}

function getXuiInboundsForBackend(backendId) {
    return getXuiInboundGroup(backendId).inbounds || [];
}

function getXuiClientGroup(backendId) {
    const key = String(backendId);
    if (!xuiClientGroups[key]) {
        xuiClientGroups[key] = {
            loaded: false,
            loading: false,
            error: '',
            clients: []
        };
    }
    return xuiClientGroups[key];
}

function getXuiClientsForBackend(backendId) {
    return getXuiClientGroup(backendId).clients || [];
}

function syncCurrentXuiInboundsFromGroup() {
    xuiInbounds = currentXuiBackendId ? getXuiInboundsForBackend(currentXuiBackendId) : [];
}

function syncCurrentXuiClientsFromGroup() {
    xuiClients = currentXuiBackendId ? getXuiClientsForBackend(currentXuiBackendId) : [];
}

function setXuiInboundGroupsMessage(message) {
    const container = document.getElementById('xui-inbound-groups');
    if (!container) return;
    container.innerHTML = `<div class="xui-empty-state">${escapeHtml(message)}</div>`;
}

async function loadXuiInbounds(backendId = currentXuiBackendId, options = {}) {
    const targetBackendId = Number(backendId || currentXuiBackendId);
    if (!targetBackendId) {
        setXuiInboundGroupsMessage('请先选择或新增一个 3x-ui 后端');
        return;
    }

    const backend = xuiBackends.find(item => Number(item.id) === targetBackendId);
    const group = getXuiInboundGroup(targetBackendId);

    if (!backend || !backend.configured) {
        group.loaded = true;
        group.loading = false;
        group.error = backend ? '当前后端还未配置完整' : '后端不存在';
        group.inbounds = [];
        if (Number(currentXuiBackendId) === targetBackendId) syncCurrentXuiInboundsFromGroup();
        renderXuiInboundGroups();
        return;
    }

    if (options.expand) {
        xuiExpandedInboundBackends.add(targetBackendId);
    }

    group.loading = true;
    group.error = '';
    renderXuiInboundGroups();

    try {
        const response = await fetch(`/api/xui/inbounds?${xuiBackendQueryFor(targetBackendId)}`);
        const data = await response.json();
        if (!data.success) {
            group.loaded = true;
            group.loading = false;
            group.error = data.message || '加载入站节点失败';
            group.inbounds = [];
            if (Number(currentXuiBackendId) === targetBackendId) syncCurrentXuiInboundsFromGroup();
            renderXuiInboundGroups();
            return;
        }

        group.loaded = true;
        group.loading = false;
        group.error = '';
        group.inbounds = data.inbounds || [];
        if (Number(currentXuiBackendId) === targetBackendId) syncCurrentXuiInboundsFromGroup();
        renderXuiInboundGroups();

        if (options.withClients !== false) {
            const clientGroup = getXuiClientGroup(targetBackendId);
            if (!clientGroup.loaded && !clientGroup.loading) {
                await loadXuiClients(targetBackendId);
            }
        }
    } catch (error) {
        group.loaded = true;
        group.loading = false;
        group.error = '加载入站节点失败: ' + error.message;
        group.inbounds = [];
        if (Number(currentXuiBackendId) === targetBackendId) syncCurrentXuiInboundsFromGroup();
        renderXuiInboundGroups();
    }
}

async function toggleXuiInboundGroup(backendId) {
    const targetBackendId = Number(backendId);
    if (!targetBackendId) return;

    if (xuiExpandedInboundBackends.has(targetBackendId)) {
        xuiExpandedInboundBackends.delete(targetBackendId);
        renderXuiInboundGroups();
        return;
    }

    xuiExpandedInboundBackends.add(targetBackendId);
    const group = getXuiInboundGroup(targetBackendId);
    const clientGroup = getXuiClientGroup(targetBackendId);
    renderXuiInboundGroups();
    const tasks = [];
    if (!group.loaded && !group.loading) {
        tasks.push(loadXuiInbounds(targetBackendId, { expand: true, withClients: false }));
    }
    if (!clientGroup.loaded && !clientGroup.loading) {
        tasks.push(loadXuiClients(targetBackendId));
    }
    await Promise.all(tasks);
}

function renderXuiInbounds() {
    renderXuiInboundGroups();
}

function renderXuiInboundGroups() {
    const container = document.getElementById('xui-inbound-groups');
    if (!container) return;
    container.innerHTML = '';

    if (!xuiBackends.length) {
        setXuiInboundGroupsMessage('请先新增一个 3x-ui 后端');
        return;
    }

    xuiBackends.forEach(backend => {
        const backendId = Number(backend.id);
        const group = getXuiInboundGroup(backendId);
        const expanded = xuiExpandedInboundBackends.has(backendId);
        const isCurrent = Number(currentXuiBackendId) === backendId;
        const countText = group.loaded && !group.error ? `${group.inbounds.length} 个节点` : (group.loading ? '加载中' : '点击展开');
        const statusClass = !backend.configured ? 'badge-secondary' : (xuiBackendStatuses[backendId]?.online ? 'badge-success' : 'badge-info');
        const statusText = !backend.configured ? '未配置' : (xuiBackendStatuses[backendId]?.online ? '在线' : '待检测');

        const item = document.createElement('div');
        item.className = `xui-inbound-group${expanded ? ' expanded' : ''}${isCurrent ? ' current' : ''}`;
        item.innerHTML = `
            <button class="xui-inbound-group-header" type="button" onclick="toggleXuiInboundGroup(${backendId})">
                <span class="xui-inbound-caret">${expanded ? '▼' : '▶'}</span>
                <span class="xui-inbound-title">
                    <strong>${escapeHtml(backend.name || ('后端 ' + backendId))}</strong>
                    <small>${escapeHtml(backend.base_url || '未填写地址')} · 订阅地址 ${escapeHtml(backend.public_host || '自动提取')}</small>
                </span>
                <span class="badge ${statusClass}">${statusText}</span>
                <span class="xui-inbound-count">${countText}</span>
            </button>
            <div class="xui-inbound-group-body">
                ${expanded ? renderXuiInboundGroupBody(backend, group) : ''}
            </div>
        `;
        container.appendChild(item);
    });
}

function renderXuiInboundGroupBody(backend, group) {
    const backendId = Number(backend.id);
    if (!backend.configured) {
        return '<div class="xui-group-message">该后端还未配置完整，请先编辑并测试连接</div>';
    }
    if (group.loading) {
        return '<div class="xui-group-message">正在加载入站节点...</div>';
    }
    if (group.error) {
        return `
            <div class="xui-group-message error">
                ${escapeHtml(group.error)}
                <button class="btn btn-secondary btn-small" onclick="event.stopPropagation(); loadXuiInbounds(${backendId}, { expand: true });">重试</button>
            </div>
        `;
    }
    if (!group.loaded) {
        return '<div class="xui-group-message">点击后正在准备加载...</div>';
    }
    if (!group.inbounds.length) {
        return '<div class="xui-group-message">暂无入站节点</div>';
    }

    const clientGroup = getXuiClientGroup(backendId);
    const nodeCards = group.inbounds.map(inbound => renderXuiInboundNodeCard(inbound, backendId, clientGroup)).join('');
    return `
        <div class="xui-node-client-grid">
            ${nodeCards}
        </div>
    `;
}

function getXuiClientsForInbound(backendId, inboundId) {
    const targetInboundId = Number(inboundId);
    return getXuiClientsForBackend(backendId).filter(client =>
        (client.inboundIds || []).map(Number).includes(targetInboundId)
    );
}

function renderXuiInboundNodeCard(inbound, backendId, clientGroup) {
    const used = Number(inbound.up || 0) + Number(inbound.down || 0);
    const total = Number(inbound.total || 0);
    const percent = total ? Math.min(100, Math.round(used / total * 100)) : 0;
    const clients = getXuiClientsForInbound(backendId, inbound.id);
    const clientState = clientGroup.loading
        ? '<span class="badge badge-info">客户端加载中</span>'
        : clientGroup.error
            ? '<span class="badge badge-danger">客户端加载失败</span>'
            : `<span class="badge ${clients.length ? 'badge-primary' : 'badge-danger'}">${clients.length} 个客户端</span>`;

    return `
        <div class="xui-node-client-card">
            <div class="xui-node-parent">
                <div class="xui-node-card-header">
                    <div class="xui-node-main">
                        <span class="xui-node-kind">入站节点</span>
                        <strong>${escapeHtml(inbound.remark)}</strong>
                        <small>${escapeHtml(inbound.tag || ('inbound-' + inbound.id))}</small>
                    </div>
                    <div class="xui-node-badges">
                        <span class="badge badge-info">${escapeHtml(String(inbound.protocol || '').toUpperCase())}</span>
                        <span class="badge ${inbound.enable ? 'badge-success' : 'badge-danger'}">${inbound.enable ? '启用' : '停用'}</span>
                        ${clientState}
                    </div>
                    <div class="xui-node-actions">
                        <button type="button" class="btn btn-primary btn-small" onclick="event.stopPropagation(); showAddXuiClientModal(${backendId}, ${inbound.id})">新增客户端</button>
                        <button type="button" class="btn btn-info btn-small" onclick="event.stopPropagation(); showEditXuiInboundModal(${inbound.id}, ${backendId})">编辑节点</button>
                        <button type="button" class="btn btn-danger btn-small" onclick="event.stopPropagation(); deleteXuiInbound(${inbound.id}, ${backendId}, this)">删除节点</button>
                    </div>
                </div>
                <div class="xui-node-meta">
                    <span>端口：${escapeHtml(inbound.listen || '0.0.0.0')}:${inbound.port || '-'}</span>
                    <span>流量：${formatBytes(used)} / ${total ? formatBytes(total) : '不限'}</span>
                    <span>到期：${escapeHtml(formatXuiExpiry(inbound.expiryTime))}</span>
                </div>
                <div class="xui-usage-bar"><span style="width: ${percent}%;"></span></div>
            </div>
            ${renderXuiInboundClientList(clients, backendId, inbound.id, clientGroup)}
        </div>
    `;
}

function renderXuiInboundClientList(clients, backendId, inboundId, clientGroup) {
    if (clientGroup.loading) {
        return '<div class="xui-client-child-panel"><div class="xui-client-list-message">正在加载下级客户端...</div></div>';
    }
    if (clientGroup.error) {
        return `
            <div class="xui-client-child-panel">
            <div class="xui-client-list-message error">
                ${escapeHtml(clientGroup.error)}
                <button class="btn btn-secondary btn-small" onclick="loadXuiClients(${backendId})">重试</button>
            </div>
            </div>
        `;
    }
    if (!clientGroup.loaded) {
        return '<div class="xui-client-child-panel"><div class="xui-client-list-message">下级客户端尚未加载</div></div>';
    }
    if (!clients.length) {
        return `
            <div class="xui-client-child-panel empty">
            <div class="xui-client-list-message warning">
                未绑定客户端，节点暂不可用。
                <button class="btn btn-primary btn-small" onclick="showAddXuiClientModal(${backendId}, ${inboundId})">为此节点新增客户端</button>
            </div>
            </div>
        `;
    }

    const items = clients.map(client => renderXuiInboundClientItem(client, backendId)).join('');
    return `
        <div class="xui-client-child-panel">
            <div class="xui-client-list-head">
                <strong>下级客户端</strong>
                <span>${clients.length} 个</span>
            </div>
            <div class="xui-client-list">
                ${items}
            </div>
        </div>
    `;
}

function renderXuiInboundClientItem(client, backendId) {
    const used = Number(client.traffic?.used || 0);
    const total = Number(client.totalGB || 0);
    const percent = total ? Math.min(100, Math.round(used / total * 100)) : 0;
    return `
        <div class="xui-client-row">
            <span class="xui-client-branch"></span>
            <div class="xui-client-name">
                <span class="xui-client-kind">客户端</span>
                <strong>${escapeHtml(client.email)}</strong>
                ${client.comment ? `<small>${escapeHtml(client.comment)}</small>` : ''}
            </div>
            <div class="xui-client-status">
                <span class="badge ${client.enable ? 'badge-success' : 'badge-danger'}">${client.enable ? '启用' : '停用'}</span>
                <span class="badge ${client.online ? 'badge-success' : 'badge-secondary'}">${client.online ? '在线' : '离线'}</span>
            </div>
            <div class="xui-client-usage">
                ${formatBytes(used)} / ${total ? formatBytes(total) : '不限'}
                <div class="xui-usage-bar"><span style="width: ${percent}%;"></span></div>
            </div>
            <div class="xui-client-expiry">${escapeHtml(formatXuiExpiry(client.expiryTime))}</div>
            <div class="action-buttons">
                <button class="btn btn-info btn-small" onclick="showEditXuiClientModal('${escapeJs(client.email)}', ${backendId})">编辑</button>
                <button class="btn btn-danger btn-small" onclick="deleteXuiClient('${escapeJs(client.email)}', ${backendId})">删除</button>
            </div>
        </div>
    `;
}

async function loadXuiClients(backendId = currentXuiBackendId) {
    const targetBackendId = Number(backendId || currentXuiBackendId);
    if (!targetBackendId) return;

    const clientGroup = getXuiClientGroup(targetBackendId);
    clientGroup.loading = true;
    clientGroup.error = '';
    renderXuiInboundGroups();

    try {
        const response = await fetch(`/api/xui/clients?${xuiBackendQueryFor(targetBackendId)}`);
        const data = await response.json();
        if (!data.success) {
            clientGroup.loaded = true;
            clientGroup.loading = false;
            clientGroup.error = data.message || '加载客户端失败';
            clientGroup.clients = [];
            if (Number(currentXuiBackendId) === targetBackendId) syncCurrentXuiClientsFromGroup();
            renderXuiInboundGroups();
            return;
        }

        clientGroup.loaded = true;
        clientGroup.loading = false;
        clientGroup.error = '';
        clientGroup.clients = data.clients || [];
        if (Number(currentXuiBackendId) === targetBackendId) syncCurrentXuiClientsFromGroup();

        if (data.inbounds) {
            const inboundGroup = getXuiInboundGroup(targetBackendId);
            if (!inboundGroup.inbounds.length) {
                inboundGroup.loaded = true;
                inboundGroup.loading = false;
                inboundGroup.error = '';
                inboundGroup.inbounds = data.inbounds;
                if (Number(currentXuiBackendId) === targetBackendId) syncCurrentXuiInboundsFromGroup();
            }
        }
        renderXuiInboundGroups();
        renderXuiClients();
    } catch (error) {
        clientGroup.loaded = true;
        clientGroup.loading = false;
        clientGroup.error = '加载客户端失败: ' + error.message;
        clientGroup.clients = [];
        if (Number(currentXuiBackendId) === targetBackendId) syncCurrentXuiClientsFromGroup();
        renderXuiInboundGroups();
    }
}

function renderXuiClients() {
    renderXuiInboundGroups();
}

function xuiInboundBaseId(prefix) {
    if (prefix === 'edit') return 'editXuiInbound';
    if (prefix === USER_QUICK_INBOUND_PREFIX) return 'userQuickXuiInbound';
    return 'xuiInbound';
}

function xuiInboundMountId(prefix) {
    if (prefix === 'edit') return 'editXuiInboundEditorMount';
    if (prefix === USER_QUICK_INBOUND_PREFIX) return 'userQuickXuiInboundEditorMount';
    return 'xuiInboundEditorMount';
}

function isXuiInboundCreatePrefix(prefix) {
    return prefix === 'add' || prefix === USER_QUICK_INBOUND_PREFIX;
}

function xuiInboundFieldId(prefix, field) {
    return `${xuiInboundBaseId(prefix)}${field}`;
}

function xuiInboundField(prefix, field) {
    return document.getElementById(xuiInboundFieldId(prefix, field));
}

function xuiDeepClone(value) {
    if (value === undefined || value === null) return value;
    return JSON.parse(JSON.stringify(value));
}

function xuiJson(value) {
    return JSON.stringify(value ?? {}, null, 2);
}

function xuiSelectOptions(options, selected) {
    return options.map(option => `
        <option value="${escapeHtml(option.value)}"${option.value === selected ? ' selected' : ''}>${escapeHtml(option.label)}</option>
    `).join('');
}

function xuiConfiguredBackends() {
    return xuiBackends.filter(backend => backend.configured);
}

function xuiDefaultInboundBackendId() {
    const configured = xuiConfiguredBackends();
    const current = configured.find(backend => Number(backend.id) === Number(currentXuiBackendId));
    return Number(current?.id || configured[0]?.id || 0);
}

function xuiBackendSelectOptions(selectedBackendId) {
    const configured = xuiConfiguredBackends();
    if (!configured.length) {
        return '<option value="">暂无已配置后端</option>';
    }
    return configured.map(backend => {
        const status = xuiBackendStatuses[backend.id] || {};
        const stateText = status.online ? '在线' : status.loaded ? '离线' : '待检测';
        const label = `${backend.name || ('后端 ' + backend.id)} - ${stateText}`;
        return `<option value="${backend.id}"${Number(backend.id) === Number(selectedBackendId) ? ' selected' : ''}>${escapeHtml(label)}</option>`;
    }).join('');
}

function randomXuiInboundPort(backendId = xuiDefaultInboundBackendId()) {
    const usedPorts = new Set(
        getXuiInboundsForBackend(backendId)
            .map(inbound => Number(inbound.port || 0))
            .filter(Boolean)
    );
    const minPort = 20000;
    const maxPort = 59999;
    for (let attempt = 0; attempt < 80; attempt += 1) {
        const port = Math.floor(Math.random() * (maxPort - minPort + 1)) + minPort;
        if (!usedPorts.has(port)) return port;
    }
    return Math.floor(Math.random() * (maxPort - minPort + 1)) + minPort;
}

function xuiDateTimeLocalFromMs(value) {
    const ms = Number(value || 0);
    if (!ms) return '';
    const date = new Date(ms);
    if (Number.isNaN(date.getTime())) return '';
    const pad = part => String(part).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function xuiDateTimeLocalToMs(value) {
    if (!value) return 0;
    const date = new Date(value);
    const ms = date.getTime();
    return Number.isNaN(ms) ? 0 : ms;
}

function xuiParseJsonText(rawValue, fallback, label, silent = false) {
    const raw = String(rawValue ?? '').trim();
    if (!raw) return xuiDeepClone(fallback);
    try {
        return JSON.parse(raw);
    } catch (error) {
        if (!silent) alert(`${label} JSON 格式错误: ${error.message}`);
        throw error;
    }
}

function xuiListFromText(value) {
    return String(value || '')
        .split(/[\n,]/)
        .map(item => item.trim())
        .filter(Boolean);
}

function xuiListToText(value) {
    return Array.isArray(value) ? value.join(', ') : (value || '');
}

function xuiFirstValue(...values) {
    for (const value of values) {
        if (value !== undefined && value !== null && value !== '') return value;
    }
    return '';
}

function xuiListFromAny(value) {
    if (Array.isArray(value)) return value.map(item => String(item).trim()).filter(Boolean);
    return xuiListFromText(value);
}

function xuiNumbersFromText(value) {
    return String(value || '')
        .split(/[\s,]+/)
        .map(item => Number(item))
        .filter(item => Number.isFinite(item));
}

function xuiRandomHex(length = 8) {
    const bytes = new Uint8Array(Math.ceil(length / 2));
    if (window.crypto?.getRandomValues) {
        window.crypto.getRandomValues(bytes);
    } else {
        for (let index = 0; index < bytes.length; index += 1) {
            bytes[index] = Math.floor(Math.random() * 256);
        }
    }
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('').slice(0, length);
}

function xuiDefaultRealityShortIds() {
    return [xuiRandomHex(8)];
}

function xuiApiObject(data) {
    if (!data || typeof data !== 'object') return data;
    if (data.obj !== undefined) return data.obj;
    if (data.cert !== undefined) return data.cert;
    if (data.auth !== undefined) return data.auth;
    if (data.seed !== undefined) return data.seed;
    if (data.kem !== undefined) return data.kem;
    if (data.payload && typeof data.payload === 'object' && data.payload.obj !== undefined) return data.payload.obj;
    if (data.payload !== undefined) return data.payload;
    return data;
}

function xuiInboundBackendIdFor(prefix) {
    return Number(xuiInboundField(prefix, 'BackendId')?.value || xuiInboundEditorStates[prefix]?.backendId || currentXuiBackendId || 0);
}

function xuiReadJsonField(prefix, field, fallback, label, silent = false) {
    const el = xuiInboundField(prefix, field);
    return xuiParseJsonText(el ? el.value : '', fallback, label, silent);
}

function xuiInboundNormalizedRaw(inbound) {
    const raw = xuiDeepClone(inbound?.raw || inbound || {});
    raw.settings = xuiDeepClone(inbound?.settings || xuiParseJsonText(raw.settings, {}, 'settings', true));
    raw.streamSettings = xuiDeepClone(inbound?.streamSettings || xuiParseJsonText(raw.streamSettings, {}, 'streamSettings', true));
    raw.sniffing = xuiDeepClone(inbound?.sniffing || xuiParseJsonText(raw.sniffing, {}, 'sniffing', true));
    return raw;
}

function xuiInboundDefaultPayload(backendId = xuiDefaultInboundBackendId()) {
    return {
        enable: true,
        remark: '',
        listen: '',
        port: randomXuiInboundPort(backendId),
        protocol: 'vless',
        total: 0,
        expiryTime: 0,
        settings: { clients: [], decryption: 'none', encryption: 'none', fallbacks: [] },
        streamSettings: {
            network: 'tcp',
            security: 'none',
            tcpSettings: { acceptProxyProtocol: false, header: { type: 'none' } }
        },
        sniffing: {
            enabled: true,
            destOverride: ['http', 'tls', 'quic', 'fakedns'],
            metadataOnly: false,
            routeOnly: false
        }
    };
}

function xuiInboundInitialPayload(inbound, backendId = xuiDefaultInboundBackendId()) {
    if (!inbound) return xuiInboundDefaultPayload(backendId);
    const payload = xuiInboundNormalizedRaw(inbound);
    payload.settings = payload.settings || {};
    payload.streamSettings = payload.streamSettings || {};
    payload.sniffing = payload.sniffing || {};
    return payload;
}

function xuiInboundProtocolSections(prefix, settings) {
    const fallbackJson = xuiJson(settings.fallbacks || []);
    const accountsJson = xuiJson(settings.accounts || []);
    const peersJson = xuiJson(settings.peers || []);
    const wgAddress = Array.isArray(settings.address) ? settings.address.join(', ') : (settings.address || '10.0.0.1/24');
    const vlessSeedValues = [
        ...xuiListFromAny(settings.testseed || settings.visionTestSeed || []),
        900,
        500,
        900,
        256
    ].slice(0, 4);
    const vlessAuthSelected = (settings.decryption && settings.decryption !== 'none') || (settings.encryption && settings.encryption !== 'none')
        ? `${settings.decryption || 'none'} / ${settings.encryption || 'none'}`
        : 'None';
    return `
        <div class="xui-form-grid xui-protocol-section" data-xui-protocol-section="vless">
            <div class="form-group">
                <label>瑙ｅ瘑</label>
                <input type="text" id="${xuiInboundFieldId(prefix, 'Decryption')}" value="${escapeHtml(settings.decryption || 'none')}">
            </div>
            <div class="form-group">
                <label>加密</label>
                <input type="text" id="${xuiInboundFieldId(prefix, 'Encryption')}" value="${escapeHtml(settings.encryption || 'none')}">
            </div>
            <div class="form-group xui-span-2">
                <div class="xui-form-actions xui-inline-actions">
                    <button type="button" class="btn btn-info btn-small" onclick="fillXuiVlessAuth('${prefix}', 'x25519')">X25519 认证</button>
                    <button type="button" class="btn btn-info btn-small" onclick="fillXuiVlessAuth('${prefix}', 'mlkem768')">ML-KEM-768 认证</button>
                    <button type="button" class="btn btn-danger btn-small" onclick="clearXuiVlessAuth('${prefix}')">清除</button>
                </div>
                <small id="${xuiInboundFieldId(prefix, 'VlessAuthSelected')}">已选择：${escapeHtml(vlessAuthSelected)}</small>
            </div>
            <div class="form-group xui-span-2">
                <label>Vision testseed</label>
                <div class="xui-inline-fields">
                    ${vlessSeedValues.map((value, index) => `
                        <input type="number" min="0" id="${xuiInboundFieldId(prefix, `VisionSeed${index}`)}" value="${escapeHtml(value)}">
                    `).join('')}
                </div>
                <small>仅对使用 xtls-rprx-vision flow 的客户端生效；其他客户端会忽略</small>
            </div>
            <div class="form-group xui-span-2">
                <div class="xui-fallback-box">
                    <div class="xui-fallback-header">
                        <span>Fallbacks</span>
                        <div class="xui-form-actions xui-inline-actions">
                            <button type="button" class="btn btn-info btn-small" onclick="addXuiVlessFallback('${prefix}')">添加回落</button>
                            <button type="button" class="btn btn-secondary btn-small" onclick="fillXuiVlessFallbacks('${prefix}')">全部添加</button>
                        </div>
                    </div>
                    <textarea id="${xuiInboundFieldId(prefix, 'Fallbacks')}" rows="5">${escapeHtml(fallbackJson)}</textarea>
                    <small>保存到 3x-ui fallbacks JSON；不需要回落时保持 []。</small>
                </div>
            </div>
        </div>
        <div class="xui-form-grid xui-protocol-section" data-xui-protocol-section="vmess">
            <div class="form-group checkbox-group">
                <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'DisableInsecureEncryption')}" ${settings.disableInsecureEncryption ? 'checked' : ''}> 禁用不安全加密</label>
            </div>
        </div>
        <div class="xui-form-grid xui-protocol-section" data-xui-protocol-section="trojan">
            <div class="form-group xui-span-2">
                <label>Fallbacks JSON</label>
                <textarea id="${xuiInboundFieldId(prefix, 'TrojanFallbacks')}" rows="4">${escapeHtml(fallbackJson)}</textarea>
            </div>
        </div>
        <div class="xui-form-grid xui-protocol-section" data-xui-protocol-section="shadowsocks">
            <div class="form-group">
                <label>加密方法</label>
                <select id="${xuiInboundFieldId(prefix, 'SsMethod')}">
                    ${xuiSelectOptions([
                        { value: 'aes-256-gcm', label: 'aes-256-gcm' },
                        { value: 'aes-128-gcm', label: 'aes-128-gcm' },
                        { value: 'chacha20-poly1305', label: 'chacha20-poly1305' },
                        { value: '2022-blake3-aes-128-gcm', label: '2022-blake3-aes-128-gcm' },
                        { value: '2022-blake3-aes-256-gcm', label: '2022-blake3-aes-256-gcm' },
                        { value: '2022-blake3-chacha20-poly1305', label: '2022-blake3-chacha20-poly1305' }
                    ], settings.method || 'aes-256-gcm')}
                </select>
            </div>
            <div class="form-group">
                <label>密码</label>
                <input type="text" id="${xuiInboundFieldId(prefix, 'SsPassword')}" value="${escapeHtml(settings.password || '')}">
            </div>
            <div class="form-group">
                <label>网络</label>
                <select id="${xuiInboundFieldId(prefix, 'SsNetwork')}">
                    ${xuiSelectOptions([
                        { value: 'tcp,udp', label: 'TCP + UDP' },
                        { value: 'tcp', label: 'TCP' },
                        { value: 'udp', label: 'UDP' }
                    ], settings.network || 'tcp,udp')}
                </select>
            </div>
        </div>
        <div class="xui-form-grid xui-protocol-section" data-xui-protocol-section="wireguard">
            <div class="form-group">
                <label>Secret Key</label>
                <input type="text" id="${xuiInboundFieldId(prefix, 'WgSecretKey')}" value="${escapeHtml(settings.secretKey || '')}">
            </div>
            <div class="form-group">
                <label>地址</label>
                <input type="text" id="${xuiInboundFieldId(prefix, 'WgAddress')}" value="${escapeHtml(wgAddress)}">
            </div>
            <div class="form-group">
                <label>MTU</label>
                <input type="number" id="${xuiInboundFieldId(prefix, 'WgMtu')}" value="${Number(settings.mtu || 1420)}">
            </div>
            <div class="form-group">
                <label>Workers</label>
                <input type="number" id="${xuiInboundFieldId(prefix, 'WgWorkers')}" value="${Number(settings.workers || 0)}">
            </div>
            <div class="form-group checkbox-group">
                <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'WgKernelMode')}" ${settings.kernelMode ? 'checked' : ''}> Kernel Mode</label>
            </div>
            <div class="form-group xui-span-2">
                <label>Peers JSON</label>
                <textarea id="${xuiInboundFieldId(prefix, 'WgPeers')}" rows="4">${escapeHtml(peersJson)}</textarea>
            </div>
        </div>
        <div class="xui-form-grid xui-protocol-section" data-xui-protocol-section="hysteria2">
            <div class="form-group">
                <label>伪装地址</label>
                <input type="text" id="${xuiInboundFieldId(prefix, 'HyMasquerade')}" value="${escapeHtml(settings.masquerade || '')}">
            </div>
            <div class="form-group">
                <label>上行 Mbps</label>
                <input type="number" id="${xuiInboundFieldId(prefix, 'HyUpMbps')}" value="${Number(settings.up_mbps || settings.upMbps || 100)}">
            </div>
            <div class="form-group">
                <label>下行 Mbps</label>
                <input type="number" id="${xuiInboundFieldId(prefix, 'HyDownMbps')}" value="${Number(settings.down_mbps || settings.downMbps || 100)}">
            </div>
            <div class="form-group checkbox-group">
                <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'HyIgnoreBandwidth')}" ${settings.ignoreClientBandwidth ? 'checked' : ''}> 忽略客户端带宽</label>
            </div>
        </div>
        <div class="xui-form-grid xui-protocol-section" data-xui-protocol-section="http">
            <div class="form-group xui-span-2">
                <label>Accounts JSON</label>
                <textarea id="${xuiInboundFieldId(prefix, 'HttpAccounts')}" rows="4">${escapeHtml(accountsJson)}</textarea>
            </div>
            <div class="form-group checkbox-group">
                <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'AllowTransparent')}" ${settings.allowTransparent ? 'checked' : ''}> Allow Transparent</label>
            </div>
            <div class="form-group">
                <label>User Level</label>
                <input type="number" id="${xuiInboundFieldId(prefix, 'HttpUserLevel')}" value="${Number(settings.userLevel || 0)}">
            </div>
        </div>
        <div class="xui-form-grid xui-protocol-section" data-xui-protocol-section="socks">
            <div class="form-group">
                <label>认证</label>
                <select id="${xuiInboundFieldId(prefix, 'SocksAuth')}">
                    ${xuiSelectOptions([{ value: 'noauth', label: 'noauth' }, { value: 'password', label: 'password' }], settings.auth || 'noauth')}
                </select>
            </div>
            <div class="form-group">
                <label>绑定 IP</label>
                <input type="text" id="${xuiInboundFieldId(prefix, 'SocksIp')}" value="${escapeHtml(settings.ip || '127.0.0.1')}">
            </div>
            <div class="form-group checkbox-group">
                <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'SocksUdp')}" ${settings.udp !== false ? 'checked' : ''}> UDP</label>
            </div>
            <div class="form-group xui-span-2">
                <label>Accounts JSON</label>
                <textarea id="${xuiInboundFieldId(prefix, 'SocksAccounts')}" rows="4">${escapeHtml(accountsJson)}</textarea>
            </div>
        </div>
        <div class="xui-form-grid xui-protocol-section" data-xui-protocol-section="dokodemo-door">
            <div class="form-group">
                <label>目标地址</label>
                <input type="text" id="${xuiInboundFieldId(prefix, 'TargetAddress')}" value="${escapeHtml(settings.address || '')}">
            </div>
            <div class="form-group">
                <label>目标端口</label>
                <input type="number" id="${xuiInboundFieldId(prefix, 'TargetPort')}" value="${Number(settings.port || 0)}">
            </div>
            <div class="form-group">
                <label>网络</label>
                <select id="${xuiInboundFieldId(prefix, 'TargetNetwork')}">
                    ${xuiSelectOptions([
                        { value: 'tcp,udp', label: 'TCP + UDP' },
                        { value: 'tcp', label: 'TCP' },
                        { value: 'udp', label: 'UDP' }
                    ], settings.network || 'tcp,udp')}
                </select>
            </div>
            <div class="form-group checkbox-group">
                <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'FollowRedirect')}" ${settings.followRedirect ? 'checked' : ''}> Follow Redirect</label>
            </div>
        </div>
        <div class="xui-form-grid xui-protocol-section" data-xui-protocol-section="tun">
            <div class="form-group">
                <label>Stack</label>
                <select id="${xuiInboundFieldId(prefix, 'TunStack')}">
                    ${xuiSelectOptions([{ value: 'system', label: 'system' }, { value: 'gvisor', label: 'gVisor' }, { value: 'mixed', label: 'mixed' }], settings.stack || 'system')}
                </select>
            </div>
            <div class="form-group">
                <label>MTU</label>
                <input type="number" id="${xuiInboundFieldId(prefix, 'TunMtu')}" value="${Number(settings.mtu || 1500)}">
            </div>
            <div class="form-group checkbox-group">
                <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'TunNat')}" ${settings.endpointIndependentNat ? 'checked' : ''}> Endpoint Independent NAT</label>
            </div>
            <div class="form-group checkbox-group">
                <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'TunSniff')}" ${settings.sniff !== false ? 'checked' : ''}> Sniff</label>
            </div>
        </div>
    `;
}

function renderXuiInboundEditor(prefix, inbound = null) {
    const mount = document.getElementById(xuiInboundMountId(prefix));
    if (!mount) return;

    const createMode = isXuiInboundCreatePrefix(prefix);
    const initialBackendId = createMode
        ? Number(xuiInboundEditorStates[prefix]?.backendId || xuiDefaultInboundBackendId())
        : null;
    const payload = xuiInboundInitialPayload(inbound, initialBackendId);
    const settings = payload.settings || {};
    const stream = payload.streamSettings || {};
    const sniffing = payload.sniffing || {};
    const protocol = payload.protocol || 'vless';
    const network = stream.network || 'tcp';
    const security = stream.security || 'none';
    const tlsSettings = stream.tlsSettings || stream.xtlsSettings || {};
    const realitySettings = stream.realitySettings || {};
    const tlsNestedSettings = tlsSettings.settings || {};
    const tcpSettings = stream.tcpSettings || {};
    const wsSettings = stream.wsSettings || {};
    const grpcSettings = stream.grpcSettings || {};
    const kcpSettings = stream.kcpSettings || {};
    const httpupgradeSettings = stream.httpupgradeSettings || {};
    const xhttpSettings = stream.xhttpSettings || {};
    const activeTab = xuiInboundEditorStates[prefix]?.activeTab || 'base';
    const destOverride = Array.isArray(sniffing.destOverride) ? sniffing.destOverride : ['http', 'tls', 'quic', 'fakedns'];
    const pathValue = wsSettings.path || httpupgradeSettings.path || xhttpSettings.path || '/';
    const hostValue = wsSettings.host || wsSettings.headers?.Host || httpupgradeSettings.host || xhttpSettings.host || tlsSettings.serverName || '';
    const selectedBackendId = createMode ? initialBackendId : null;
    const tlsCertificate = (Array.isArray(tlsSettings.certificates) && tlsSettings.certificates[0]) ? tlsSettings.certificates[0] : {};
    const tlsAlpnValue = xuiListToText(tlsSettings.alpn || ['h2', 'http/1.1']);
    const tlsCurveValue = xuiListToText(tlsSettings.curvePreferences || tlsNestedSettings.curvePreferences || []);
    const tlsPinnedValue = xuiListToText(tlsSettings.pinnedPeerCertificateChainSha256 || tlsNestedSettings.pinnedPeerCertSha256 || []);
    const tlsVerifyNamesValue = xuiListToText(tlsSettings.verifyPeerCertInNames || tlsNestedSettings.verifyPeerCertInNames || []);
    const realityNestedSettings = realitySettings.settings || {};
    const realityDestValue = xuiFirstValue(realitySettings.target, realitySettings.dest, 'www.amd.com:443');
    const realityServerNamesValue = xuiListToText(realitySettings.serverNames || realityNestedSettings.serverNames || (realityNestedSettings.serverName ? [realityNestedSettings.serverName] : ['www.amd.com']));
    const realityShortIdsValue = xuiListToText(
        (Array.isArray(realitySettings.shortIds) && realitySettings.shortIds.length)
            ? realitySettings.shortIds
            : ((security === 'reality' || createMode) ? xuiDefaultRealityShortIds() : [])
    );
    const realityPublicKeyValue = xuiFirstValue(realityNestedSettings.publicKey, realitySettings.publicKey);
    const realityMldsaSeedValue = xuiFirstValue(realitySettings.mldsa65Seed, realityNestedSettings.mldsa65Seed);
    const realityMldsaVerifyValue = xuiFirstValue(realityNestedSettings.mldsa65Verify, realitySettings.mldsa65Verify, realitySettings.mldsa65PublicKey);

    xuiInboundEditorStates[prefix] = {
        ...(xuiInboundEditorStates[prefix] || {}),
        mode: prefix === 'edit' ? 'edit' : 'add',
        inbound,
        seedPayload: payload,
        activeTab,
        backendId: selectedBackendId || xuiInboundEditorStates[prefix]?.backendId || null,
        autoPort: createMode ? Number(payload.port || 0) : null
    };

    mount.innerHTML = `
        <div class="xui-inbound-editor" data-prefix="${escapeHtml(prefix)}">
            <div class="xui-inbound-tabs">
                ${XUI_INBOUND_TABS.map(tab => `
                    <button type="button" class="${tab.value === activeTab ? 'active' : ''}" data-xui-inbound-tab="${tab.value}" onclick="switchXuiInboundEditorTab('${prefix}', '${tab.value}')">${escapeHtml(tab.label)}</button>
                `).join('')}
            </div>

            <div class="xui-inbound-tab-panel ${activeTab === 'base' ? 'active' : ''}" data-xui-inbound-panel="base">
                <div class="xui-form-grid">
                    ${createMode ? `
                    <div class="form-group xui-span-2">
                        <label>生成到后端</label>
                        <select id="${xuiInboundFieldId(prefix, 'BackendId')}">
                            ${xuiBackendSelectOptions(selectedBackendId)}
                        </select>
                        <small>入站节点会创建到这里选择的 3x-ui 后端</small>
                    </div>
                    ` : ''}
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'Enable')}" ${payload.enable !== false ? 'checked' : ''}> 启用</label>
                    </div>
                    <div class="form-group">
                        <label>备注</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'Remark')}" value="${escapeHtml(payload.remark || '')}" placeholder="例如: VLESS-443">
                    </div>
                    <div class="form-group">
                        <label>协议</label>
                        <select id="${xuiInboundFieldId(prefix, 'Protocol')}">${xuiSelectOptions(XUI_INBOUND_PROTOCOL_OPTIONS, protocol)}</select>
                    </div>
                    <div class="form-group">
                        <label>地址</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'Listen')}" value="${escapeHtml(payload.listen || '')}" placeholder="留空表示监听所有 IP">
                    </div>
                    <div class="form-group">
                        <label>分享地址策略</label>
                        <select id="${xuiInboundFieldId(prefix, 'ShareStrategy')}">
                            ${xuiSelectOptions([
                                { value: 'inbound', label: '入站监听地址' },
                                { value: 'backend', label: '后端面板地址' },
                                { value: 'custom', label: '高级 JSON 指定' }
                            ], 'inbound')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>订阅排序</label>
                        <input type="number" id="${xuiInboundFieldId(prefix, 'SubSort')}" value="${Number(payload.subSort || payload.sort || 0)}">
                    </div>
                    <div class="form-group">
                        <label>端口</label>
                        <div class="xui-port-row">
                            <input type="number" id="${xuiInboundFieldId(prefix, 'Port')}" min="1" max="65535" value="${escapeHtml(payload.port || '')}" placeholder="自动随机">
                            ${createMode ? `<button type="button" class="btn btn-secondary btn-small" onclick="regenerateXuiInboundPort('${prefix}')">随机</button>` : ''}
                        </div>
                    </div>
                    <div class="form-group">
                        <label>总流量 GB</label>
                        <input type="number" id="${xuiInboundFieldId(prefix, 'TotalGb')}" min="0" step="0.1" value="${xuiBytesToGb(payload.total || 0)}">
                    </div>
                    <div class="form-group">
                        <label>流量重置</label>
                        <select id="${xuiInboundFieldId(prefix, 'Reset')}">
                            ${xuiSelectOptions([
                                { value: '0', label: '从不' },
                                { value: '1', label: '每日' },
                                { value: '2', label: '每周' },
                                { value: '3', label: '每月' }
                            ], String(payload.reset || 0))}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>到期时间</label>
                        <input type="datetime-local" id="${xuiInboundFieldId(prefix, 'ExpiryTime')}" value="${escapeHtml(xuiDateTimeLocalFromMs(payload.expiryTime || 0))}">
                    </div>
                </div>
            </div>

            <div class="xui-inbound-tab-panel ${activeTab === 'protocol' ? 'active' : ''}" data-xui-inbound-panel="protocol">
                ${xuiInboundProtocolSections(prefix, settings)}
            </div>

            <div class="xui-inbound-tab-panel ${activeTab === 'transport' ? 'active' : ''}" data-xui-inbound-panel="transport">
                <div class="xui-form-grid">
                    <div class="form-group">
                        <label>传输</label>
                        <select id="${xuiInboundFieldId(prefix, 'Network')}">${xuiSelectOptions(XUI_INBOUND_NETWORK_OPTIONS, network)}</select>
                    </div>
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'AcceptProxyProtocol')}" ${(tcpSettings.acceptProxyProtocol || wsSettings.acceptProxyProtocol || httpupgradeSettings.acceptProxyProtocol) ? 'checked' : ''}> Proxy Protocol</label>
                    </div>
                    <div class="form-group checkbox-group" data-xui-network-section="tcp">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'HttpObfuscation')}" ${tcpSettings.header?.type === 'http' ? 'checked' : ''}> HTTP 娣锋穯</label>
                    </div>
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'Sockopt')}" ${stream.sockopt ? 'checked' : ''}> Sockopt</label>
                    </div>
                    <div class="form-group" data-xui-network-section="path">
                        <label>路径</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'Path')}" value="${escapeHtml(pathValue)}" placeholder="/ws">
                    </div>
                    <div class="form-group" data-xui-network-section="host">
                        <label>Host</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'Host')}" value="${escapeHtml(hostValue)}">
                    </div>
                    <div class="form-group" data-xui-network-section="grpc">
                        <label>gRPC 服务名</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'GrpcServiceName')}" value="${escapeHtml(grpcSettings.serviceName || '')}">
                    </div>
                    <div class="form-group" data-xui-network-section="kcp">
                        <label>mKCP Header</label>
                        <select id="${xuiInboundFieldId(prefix, 'KcpHeader')}">
                            ${xuiSelectOptions([
                                { value: 'none', label: 'none' },
                                { value: 'srtp', label: 'srtp' },
                                { value: 'utp', label: 'utp' },
                                { value: 'wechat-video', label: 'wechat-video' },
                                { value: 'dtls', label: 'dtls' },
                                { value: 'wireguard', label: 'wireguard' }
                            ], kcpSettings.header?.type || 'none')}
                        </select>
                    </div>
                    <div class="form-group" data-xui-network-section="kcp">
                        <label>mKCP MTU</label>
                        <input type="number" id="${xuiInboundFieldId(prefix, 'KcpMtu')}" value="${Number(kcpSettings.mtu || 1350)}">
                    </div>
                    <div class="form-group" data-xui-network-section="kcp">
                        <label>mKCP TTI</label>
                        <input type="number" id="${xuiInboundFieldId(prefix, 'KcpTti')}" value="${Number(kcpSettings.tti || 20)}">
                    </div>
                    <div class="form-group" data-xui-network-section="kcp">
                        <label>上行容量</label>
                        <input type="number" id="${xuiInboundFieldId(prefix, 'KcpUplink')}" value="${Number(kcpSettings.uplinkCapacity || 5)}">
                    </div>
                    <div class="form-group" data-xui-network-section="kcp">
                        <label>下行容量</label>
                        <input type="number" id="${xuiInboundFieldId(prefix, 'KcpDownlink')}" value="${Number(kcpSettings.downlinkCapacity || 20)}">
                    </div>
                    <div class="form-group checkbox-group" data-xui-network-section="kcp">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'KcpCongestion')}" ${kcpSettings.congestion ? 'checked' : ''}> Congestion</label>
                    </div>
                    <div class="form-group" data-xui-network-section="xhttp">
                        <label>XHTTP 妯″紡</label>
                        <select id="${xuiInboundFieldId(prefix, 'XhttpMode')}">
                            ${xuiSelectOptions([
                                { value: 'auto', label: 'auto' },
                                { value: 'packet-up', label: 'packet-up' },
                                { value: 'stream-up', label: 'stream-up' },
                                { value: 'stream-one', label: 'stream-one' }
                            ], xhttpSettings.mode || 'auto')}
                        </select>
                    </div>
                    <div class="form-group xui-span-2" data-xui-network-section="xhttp">
                        <label>XHTTP Extra JSON</label>
                        <textarea id="${xuiInboundFieldId(prefix, 'XhttpExtra')}" rows="4">${escapeHtml(xuiJson(xhttpSettings.extra || {}))}</textarea>
                    </div>
                    <div class="form-group xui-span-2" data-xui-network-section="tcp">
                        <label>TCP Masks JSON</label>
                        <textarea id="${xuiInboundFieldId(prefix, 'TcpMasks')}" rows="3">${escapeHtml(xuiJson(tcpSettings.masks || []))}</textarea>
                    </div>
                </div>
            </div>

            <div class="xui-inbound-tab-panel ${activeTab === 'security' ? 'active' : ''}" data-xui-inbound-panel="security">
                <input type="hidden" id="${xuiInboundFieldId(prefix, 'Security')}" value="${escapeHtml(security)}">
                <div class="xui-segmented">
                    ${XUI_INBOUND_SECURITY_OPTIONS.map(option => `
                        <button type="button" class="${option.value === security ? 'active' : ''}" data-xui-security="${option.value}" onclick="setXuiInboundSecurity('${prefix}', '${option.value}')">${escapeHtml(option.label)}</button>
                    `).join('')}
                </div>
                <div class="xui-form-grid xui-security-fields" data-xui-security-section="tls">
                    <div class="form-group">
                        <label>SNI</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'Sni')}" value="${escapeHtml(tlsSettings.serverName || realitySettings.serverNames?.[0] || hostValue || '')}" placeholder="SNI">
                    </div>
                    <div class="form-group">
                        <label>Cipher Suites</label>
                        <select id="${xuiInboundFieldId(prefix, 'CipherSuites')}">
                            ${xuiSelectOptions([
                                { value: '', label: '自动' },
                                { value: 'TLS_AES_128_GCM_SHA256', label: 'TLS_AES_128_GCM_SHA256' },
                                { value: 'TLS_AES_256_GCM_SHA384', label: 'TLS_AES_256_GCM_SHA384' },
                                { value: 'TLS_CHACHA20_POLY1305_SHA256', label: 'TLS_CHACHA20_POLY1305_SHA256' }
                            ], tlsSettings.cipherSuites || '')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>最小版本</label>
                        <select id="${xuiInboundFieldId(prefix, 'TlsMinVersion')}">
                            ${xuiSelectOptions([{ value: '1.0', label: '1.0' }, { value: '1.1', label: '1.1' }, { value: '1.2', label: '1.2' }, { value: '1.3', label: '1.3' }], tlsSettings.minVersion || '1.2')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>最大版本</label>
                        <select id="${xuiInboundFieldId(prefix, 'TlsMaxVersion')}">
                            ${xuiSelectOptions([{ value: '1.0', label: '1.0' }, { value: '1.1', label: '1.1' }, { value: '1.2', label: '1.2' }, { value: '1.3', label: '1.3' }], tlsSettings.maxVersion || '1.3')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>uTLS</label>
                        <select id="${xuiInboundFieldId(prefix, 'TlsFingerprint')}">
                            ${xuiSelectOptions([
                                { value: 'chrome', label: 'chrome' },
                                { value: 'firefox', label: 'firefox' },
                                { value: 'safari', label: 'safari' },
                                { value: 'ios', label: 'ios' },
                                { value: 'android', label: 'android' },
                                { value: 'edge', label: 'edge' },
                                { value: '360', label: '360' },
                                { value: 'qq', label: 'qq' },
                                { value: 'random', label: 'random' },
                                { value: 'randomized', label: 'randomized' }
                            ], tlsSettings.fingerprint || tlsNestedSettings.fingerprint || 'chrome')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>ALPN</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'Alpn')}" value="${escapeHtml(tlsAlpnValue)}" placeholder="h2, http/1.1">
                    </div>
                    <div class="form-group xui-span-2">
                        <label>曲线偏好</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'CurvePreferences')}" value="${escapeHtml(tlsCurveValue)}" placeholder="例如: X25519, P-256">
                    </div>
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'RejectUnknownSni')}" ${tlsSettings.rejectUnknownSni ? 'checked' : ''}> 拒绝未知 SNI</label>
                    </div>
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'DisableSystemRoot')}" ${tlsSettings.disableSystemRoot ? 'checked' : ''}> 禁用系统根证书</label>
                    </div>
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'SessionResumption')}" ${tlsSettings.enableSessionResumption ? 'checked' : ''}> 会话恢复</label>
                    </div>
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'TlsOneTimeLoading')}" ${tlsSettings.oneTimeLoading || tlsNestedSettings.oneTimeLoading ? 'checked' : ''}> 一次性加载</label>
                    </div>
                    <div class="form-group xui-span-2">
                        <label>数字证书</label>
                        <input type="hidden" id="${xuiInboundFieldId(prefix, 'TlsCertMode')}" value="${escapeHtml(tlsCertificate.certificate || tlsCertificate.key ? 'content' : 'file')}">
                        <div class="xui-segmented compact">
                            <button type="button" data-xui-cert-mode="file" onclick="setXuiTlsCertMode('${prefix}', 'file')">文件路径</button>
                            <button type="button" data-xui-cert-mode="content" onclick="setXuiTlsCertMode('${prefix}', 'content')">文件内容</button>
                        </div>
                    </div>
                    <div class="form-group" data-xui-cert-section="file">
                        <label>公钥文件</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'CertFile')}" value="${escapeHtml(tlsCertificate.certificateFile || '')}">
                    </div>
                    <div class="form-group" data-xui-cert-section="file">
                        <label>私钥文件</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'KeyFile')}" value="${escapeHtml(tlsCertificate.keyFile || '')}">
                    </div>
                    <div class="form-group" data-xui-cert-section="content">
                        <label>公钥</label>
                        <textarea id="${xuiInboundFieldId(prefix, 'CertContent')}" rows="3">${escapeHtml(tlsCertificate.certificate || '')}</textarea>
                    </div>
                    <div class="form-group" data-xui-cert-section="content">
                        <label>私钥</label>
                        <textarea id="${xuiInboundFieldId(prefix, 'KeyContent')}" rows="3">${escapeHtml(tlsCertificate.key || '')}</textarea>
                    </div>
                    <div class="form-group xui-span-2">
                        <div class="xui-form-actions">
                            <button type="button" class="btn btn-info btn-small" onclick="fillXuiTlsCertFromBackend('${prefix}')">从面板设置证书</button>
                            <button type="button" class="btn btn-danger btn-small" onclick="clearXuiTlsCertificate('${prefix}')">清除</button>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>OCSP Stapling</label>
                        <div class="xui-unit-row">
                            <input type="number" id="${xuiInboundFieldId(prefix, 'OcspStapling')}" min="0" value="${Number(tlsSettings.ocspStapling || tlsNestedSettings.ocspStapling || 0)}">
                            <span>s</span>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>使用选项</label>
                        <select id="${xuiInboundFieldId(prefix, 'TlsUsage')}">
                            ${xuiSelectOptions([
                                { value: 'encipherment', label: 'encipherment' },
                                { value: 'verify', label: 'verify' },
                                { value: 'issue', label: 'issue' }
                            ], tlsSettings.usage || tlsNestedSettings.usage || 'encipherment')}
                        </select>
                    </div>
                    <div class="form-group xui-span-2">
                        <label>主密钥日志</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'MasterKeyLog')}" value="${escapeHtml(tlsSettings.masterKeyLog || tlsNestedSettings.masterKeyLog || '')}" placeholder="/path/to/sslkeylog.txt">
                    </div>
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'EchSockopt')}" ${tlsSettings.echSockopt || tlsNestedSettings.echSockopt ? 'checked' : ''}> ECH Sockopt</label>
                    </div>
                    <div></div>
                    <div class="form-group">
                        <label>ECH key</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'EchKey')}" value="${escapeHtml(xuiFirstValue(tlsSettings.echServerKeys, tlsNestedSettings.echKey))}">
                    </div>
                    <div class="form-group">
                        <label>ECH 配置</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'EchConfig')}" value="${escapeHtml(xuiFirstValue(tlsSettings.echConfigList, tlsNestedSettings.echConfig))}">
                    </div>
                    <div class="form-group xui-span-2">
                        <div class="xui-form-actions">
                            <button type="button" class="btn btn-info btn-small" onclick="fetchXuiEchCertificate('${prefix}')">获取 ECH 证书</button>
                            <button type="button" class="btn btn-danger btn-small" onclick="clearXuiEchFields('${prefix}')">清除</button>
                        </div>
                    </div>
                    <div class="form-group xui-span-2">
                        <label>固定对端证书 SHA-256</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'PinnedPeerCertSha256')}" value="${escapeHtml(tlsPinnedValue)}" placeholder="十六进制哈希，逗号分隔">
                    </div>
                    <div class="form-group xui-span-2">
                        <label>按名称验证对端证书</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'VerifyPeerCertNames')}" value="${escapeHtml(tlsVerifyNamesValue)}" placeholder="example.com">
                    </div>
                </div>
                <div class="xui-form-grid xui-security-fields" data-xui-security-section="reality">
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'RealityShow')}" ${realitySettings.show ? 'checked' : ''}> 显示</label>
                    </div>
                    <div class="form-group">
                        <label>Xver</label>
                        <input type="number" id="${xuiInboundFieldId(prefix, 'RealityXver')}" min="0" value="${Number(realitySettings.xver || 0)}">
                    </div>
                    <div class="form-group">
                        <label>uTLS</label>
                        <select id="${xuiInboundFieldId(prefix, 'RealityFingerprint')}">
                            ${xuiSelectOptions(XUI_TLS_FINGERPRINT_OPTIONS, realityNestedSettings.fingerprint || 'chrome')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>目标</label>
                        <div class="xui-port-row">
                            <input type="text" id="${xuiInboundFieldId(prefix, 'RealityDest')}" value="${escapeHtml(realityDestValue)}" placeholder="www.amd.com:443">
                            <button type="button" class="btn btn-secondary btn-small" onclick="randomizeXuiRealityTarget('${prefix}')">随机</button>
                        </div>
                    </div>
                    <div class="form-group xui-span-2">
                        <label>SNI</label>
                        <div class="xui-port-row">
                            <input type="text" id="${xuiInboundFieldId(prefix, 'RealityServerNames')}" value="${escapeHtml(realityServerNamesValue)}" placeholder="www.amd.com">
                            <button type="button" class="btn btn-secondary btn-small" onclick="syncXuiRealitySniFromTarget('${prefix}')">同步</button>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>最大时间差 (ms)</label>
                        <input type="number" id="${xuiInboundFieldId(prefix, 'RealityMaxTimeDiff')}" min="0" value="${Number(realitySettings.maxTimediff ?? realitySettings.maxTimeDiff ?? 0)}">
                    </div>
                    <div class="form-group">
                        <label>最小客户端版本</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'RealityMinClientVer')}" value="${escapeHtml(realitySettings.minClientVer || '')}" placeholder="25.9.11">
                    </div>
                    <div class="form-group">
                        <label>最大客户端版本</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'RealityMaxClientVer')}" value="${escapeHtml(realitySettings.maxClientVer || '')}" placeholder="25.9.11">
                    </div>
                    <div class="form-group">
                        <label>Short IDs</label>
                        <div class="xui-port-row">
                            <input type="text" id="${xuiInboundFieldId(prefix, 'RealityShortIds')}" value="${escapeHtml(realityShortIdsValue)}" placeholder="必填，逗号分隔">
                            <button type="button" class="btn btn-secondary btn-small" onclick="randomizeXuiRealityShortIds('${prefix}')">随机</button>
                        </div>
                    </div>
                    <div class="form-group xui-span-2">
                        <label>SpiderX</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'RealitySpiderX')}" value="${escapeHtml(realityNestedSettings.spiderX || '/')}">
                    </div>
                    <div class="form-group">
                        <label>公钥</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'RealityPublicKey')}" value="${escapeHtml(realityPublicKeyValue)}">
                    </div>
                    <div class="form-group">
                        <label>私钥</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'RealityPrivateKey')}" value="${escapeHtml(realitySettings.privateKey || '')}">
                    </div>
                    <div class="form-group xui-span-2">
                        <div class="xui-form-actions xui-inline-actions">
                            <button type="button" class="btn btn-info btn-small" onclick="fetchXuiRealityCertificate('${prefix}')">获取新证书</button>
                            <button type="button" class="btn btn-danger btn-small" onclick="clearXuiRealityCertificate('${prefix}')">清除</button>
                        </div>
                    </div>
                    <div class="form-group xui-span-2">
                        <label>mldsa65 Seed</label>
                        <textarea id="${xuiInboundFieldId(prefix, 'RealityMldsa65Seed')}" rows="2">${escapeHtml(realityMldsaSeedValue)}</textarea>
                    </div>
                    <div class="form-group xui-span-2">
                        <label>mldsa65 Verify</label>
                        <textarea id="${xuiInboundFieldId(prefix, 'RealityMldsa65Verify')}" rows="2">${escapeHtml(realityMldsaVerifyValue)}</textarea>
                    </div>
                    <div class="form-group xui-span-2">
                        <div class="xui-form-actions xui-inline-actions">
                            <button type="button" class="btn btn-info btn-small" onclick="fetchXuiMldsa65Seed('${prefix}')">获取 Seed</button>
                            <button type="button" class="btn btn-danger btn-small" onclick="clearXuiMldsa65Seed('${prefix}')">清除</button>
                        </div>
                    </div>
                    <div class="form-group xui-span-2">
                        <label>主密钥日志</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'RealityMasterKeyLog')}" value="${escapeHtml(realitySettings.masterKeyLog || realityNestedSettings.masterKeyLog || '')}" placeholder="/path/to/sslkeylog.txt">
                    </div>
                    <div class="form-group xui-span-2">
                        <details class="xui-advanced-details">
                            <summary>限制 Fallback</summary>
                            <textarea id="${xuiInboundFieldId(prefix, 'RealityLimitFallback')}" rows="4">${escapeHtml(xuiJson(realitySettings.limitFallback || realityNestedSettings.limitFallback || {}))}</textarea>
                        </details>
                    </div>
                </div>
            </div>

            <div class="xui-inbound-tab-panel ${activeTab === 'sniffing' ? 'active' : ''}" data-xui-inbound-panel="sniffing">
                <div class="xui-form-grid">
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'SniffingEnabled')}" ${sniffing.enabled !== false ? 'checked' : ''}> 启用嗅探</label>
                    </div>
                    ${['http', 'tls', 'quic', 'fakedns'].map(item => `
                        <div class="form-group checkbox-group">
                            <label><input type="checkbox" id="${xuiInboundFieldId(prefix, `Sniff${item}`)}" ${destOverride.includes(item) ? 'checked' : ''}> ${escapeHtml(item)}</label>
                        </div>
                    `).join('')}
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'SniffMetadataOnly')}" ${sniffing.metadataOnly ? 'checked' : ''}> Metadata Only</label>
                    </div>
                    <div class="form-group checkbox-group">
                        <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'SniffRouteOnly')}" ${sniffing.routeOnly ? 'checked' : ''}> Route Only</label>
                    </div>
                    <div class="form-group xui-span-2">
                        <label>排除的 IP</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'SniffIpsExcluded')}" value="${escapeHtml(xuiListToText(sniffing.ipsExcluded || []))}" placeholder="IP/CIDR/geoip:* / ext:*">
                    </div>
                    <div class="form-group xui-span-2">
                        <label>排除的域名</label>
                        <input type="text" id="${xuiInboundFieldId(prefix, 'SniffDomainsExcluded')}" value="${escapeHtml(xuiListToText(sniffing.domainsExcluded || []))}" placeholder="domain:* / ext:*">
                    </div>
                </div>
            </div>

            <div class="xui-inbound-tab-panel ${activeTab === 'advanced' ? 'active' : ''}" data-xui-inbound-panel="advanced">
                <div class="form-group checkbox-group">
                    <label><input type="checkbox" id="${xuiInboundFieldId(prefix, 'AdvancedUse')}"> 保存时使用高级 JSON</label>
                </div>
                <div class="form-group">
                    <label>完整 inbound payload</label>
                    <textarea id="${xuiInboundFieldId(prefix, 'AdvancedPayload')}" rows="14" spellcheck="false"></textarea>
                </div>
                <div class="xui-form-actions">
                    <button type="button" class="btn btn-secondary btn-small" onclick="updateXuiInboundAdvancedPreview('${prefix}', true)">从表单生成 JSON</button>
                    <button type="button" class="btn btn-info btn-small" onclick="applyXuiInboundAdvancedJson('${prefix}')">从 JSON 回填表单</button>
                    <button type="button" class="btn btn-secondary btn-small" onclick="formatXuiInboundAdvancedJson('${prefix}')">格式化</button>
                </div>
            </div>
        </div>
    `;

    bindXuiInboundEditor(prefix);
    refreshXuiInboundEditor(prefix);
    updateXuiInboundAdvancedPreview(prefix, true);
}

function bindXuiInboundEditor(prefix) {
    const mount = document.getElementById(xuiInboundMountId(prefix));
    if (!mount) return;
    mount.querySelectorAll('input, select, textarea').forEach(el => {
        if (el.id === xuiInboundFieldId(prefix, 'AdvancedPayload')) return;
        el.addEventListener('input', () => {
            refreshXuiInboundEditor(prefix);
            updateXuiInboundAdvancedPreview(prefix, false);
        });
        el.addEventListener('change', () => {
            refreshXuiInboundEditor(prefix);
            updateXuiInboundAdvancedPreview(prefix, false);
        });
    });
    const advancedUse = xuiInboundField(prefix, 'AdvancedUse');
    if (advancedUse) {
        advancedUse.addEventListener('change', () => updateXuiInboundAdvancedPreview(prefix, false));
    }
    const backendSelect = xuiInboundField(prefix, 'BackendId');
    if (backendSelect) {
        backendSelect.addEventListener('change', () => {
            const previousAutoPort = Number(xuiInboundEditorStates[prefix]?.autoPort || 0);
            const portInput = xuiInboundField(prefix, 'Port');
            xuiInboundEditorStates[prefix] = {
                ...(xuiInboundEditorStates[prefix] || {}),
                backendId: Number(backendSelect.value || 0)
            };
            if (portInput && (!portInput.value || Number(portInput.value) === previousAutoPort)) {
                regenerateXuiInboundPort(prefix);
            }
        });
    }
}

function switchXuiInboundEditorTab(prefix, tab) {
    if (!xuiInboundEditorStates[prefix]) return;
    xuiInboundEditorStates[prefix].activeTab = tab;
    document.querySelectorAll(`#${xuiInboundMountId(prefix)} [data-xui-inbound-tab]`).forEach(button => {
        button.classList.toggle('active', button.dataset.xuiInboundTab === tab);
    });
    document.querySelectorAll(`#${xuiInboundMountId(prefix)} [data-xui-inbound-panel]`).forEach(panel => {
        panel.classList.toggle('active', panel.dataset.xuiInboundPanel === tab);
    });
}

function setXuiInboundSecurity(prefix, security) {
    const input = xuiInboundField(prefix, 'Security');
    if (input) input.value = security;
    refreshXuiInboundEditor(prefix);
    updateXuiInboundAdvancedPreview(prefix, false);
}

function setXuiTlsCertMode(prefix, mode) {
    const input = xuiInboundField(prefix, 'TlsCertMode');
    if (input) input.value = mode;
    refreshXuiInboundEditor(prefix);
    updateXuiInboundAdvancedPreview(prefix, false);
}

function clearXuiTlsCertificate(prefix) {
    ['CertFile', 'KeyFile', 'CertContent', 'KeyContent'].forEach(field => {
        const input = xuiInboundField(prefix, field);
        if (input) input.value = '';
    });
    updateXuiInboundAdvancedPreview(prefix, false);
}

async function fillXuiTlsCertFromBackend(prefix) {
    const backendId = Number(xuiInboundField(prefix, 'BackendId')?.value || xuiInboundEditorStates[prefix]?.backendId || currentXuiBackendId || 0);
    if (!backendId) {
        alert('请先选择后端');
        return;
    }
    try {
        const response = await fetch(`/api/xui/server/web-cert-files?${xuiBackendQueryFor(backendId)}`);
        const data = await response.json();
        if (!data.success) {
            alert('获取证书路径失败: ' + (data.message || '未知错误'));
            return;
        }
        const cert = data.cert || data.obj || data.payload || {};
        const certFile = xuiFirstValue(cert.certificateFile, cert.certFile, cert.publicKeyFile, cert.cert, cert.certificate);
        const keyFile = xuiFirstValue(cert.keyFile, cert.privateKeyFile, cert.key, cert.privateKey);
        if (certFile) xuiInboundField(prefix, 'CertFile').value = certFile;
        if (keyFile) xuiInboundField(prefix, 'KeyFile').value = keyFile;
        setXuiTlsCertMode(prefix, 'file');
    } catch (error) {
        alert('获取证书路径失败: ' + error.message);
    }
}

function clearXuiEchFields(prefix) {
    ['EchKey', 'EchConfig'].forEach(field => {
        const input = xuiInboundField(prefix, field);
        if (input) input.value = '';
    });
    updateXuiInboundAdvancedPreview(prefix, false);
}

async function fetchXuiEchCertificate(prefix) {
    const backendId = Number(xuiInboundField(prefix, 'BackendId')?.value || xuiInboundEditorStates[prefix]?.backendId || currentXuiBackendId || 0);
    if (!backendId) {
        alert('请先选择后端');
        return;
    }
    const sni = xuiInboundField(prefix, 'Sni')?.value.trim() || '';
    if (!sni) {
        alert('请先填写 SNI');
        return;
    }
    try {
        const response = await fetch('/api/xui/server/ech-cert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ backend_id: backendId, sni })
        });
        const data = await response.json();
        if (!data.success) {
            alert('获取 ECH 证书失败: ' + (data.message || '未知错误'));
            return;
        }
        const cert = data.cert || data.obj || data.payload || {};
        const echKey = xuiFirstValue(cert.echServerKeys, cert.serverKeys, cert.key, cert.privateKey, cert.echKey);
        const echConfig = xuiFirstValue(cert.echConfigList, cert.configList, cert.configs, cert.echConfig);
        if (echKey) xuiInboundField(prefix, 'EchKey').value = Array.isArray(echKey) ? echKey.join(',') : echKey;
        if (echConfig) xuiInboundField(prefix, 'EchConfig').value = Array.isArray(echConfig) ? echConfig.join(',') : echConfig;
        updateXuiInboundAdvancedPreview(prefix, false);
    } catch (error) {
        alert('获取 ECH 证书失败: ' + error.message);
    }
}

function updateXuiVlessAuthLabel(prefix) {
    const label = document.getElementById(xuiInboundFieldId(prefix, 'VlessAuthSelected'));
    if (!label) return;
    const decryption = xuiInboundField(prefix, 'Decryption')?.value.trim() || 'none';
    const encryption = xuiInboundField(prefix, 'Encryption')?.value.trim() || 'none';
    label.textContent = `已选择：${decryption === 'none' && encryption === 'none' ? 'None' : `${decryption} / ${encryption}`}`;
}

async function fetchXuiServerHelper(prefix, path, label) {
    const backendId = xuiInboundBackendIdFor(prefix);
    if (!backendId) {
        alert('请先选择后端');
        return null;
    }
    try {
        const response = await fetch(`${path}?${xuiBackendQueryFor(backendId)}`, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' }
        });
        const raw = await response.text();
        let data;
        try {
            data = JSON.parse(raw);
        } catch (parseError) {
            const redirectedToLogin = response.redirected || (response.url || '').includes('/login');
            const detail = redirectedToLogin
                ? '登录状态已过期，请刷新页面重新登录'
                : `接口返回了非 JSON 内容，HTTP ${response.status}`;
            alert(`${label}失败: ${detail}`);
            return null;
        }
        if (!data.success) {
            alert(`${label}失败: ${data.message || '未知错误'}`);
            return null;
        }
        return xuiApiObject(data);
    } catch (error) {
        alert(`${label}失败: ${error.message}`);
        return null;
    }
}

async function fillXuiVlessAuth(prefix, type) {
    const obj = await fetchXuiServerHelper(prefix, '/api/xui/server/vless-auth', '获取 VLESS 认证');
    const auths = Array.isArray(obj?.auths) ? obj.auths : (Array.isArray(obj) ? obj : []);
    if (!auths.length) {
        alert('当前后端没有返回可用的 VLESS 认证选项');
        return;
    }
    const needle = type === 'mlkem768' ? 'ml' : 'x25519';
    const auth = auths.find(item => {
        const text = `${item.id || ''} ${item.label || ''} ${item.name || ''}`.toLowerCase().replace(/[-_ ]/g, '');
        return text.includes(needle.replace(/[-_ ]/g, ''));
    }) || auths[0];
    const decryption = xuiFirstValue(auth.decryption, auth.decrypt, auth.dec, 'none');
    const encryption = xuiFirstValue(auth.encryption, auth.encrypt, auth.enc, 'none');
    if (xuiInboundField(prefix, 'Decryption')) xuiInboundField(prefix, 'Decryption').value = decryption;
    if (xuiInboundField(prefix, 'Encryption')) xuiInboundField(prefix, 'Encryption').value = encryption;
    updateXuiVlessAuthLabel(prefix);
    updateXuiInboundAdvancedPreview(prefix, false);
}

function clearXuiVlessAuth(prefix) {
    if (xuiInboundField(prefix, 'Decryption')) xuiInboundField(prefix, 'Decryption').value = 'none';
    if (xuiInboundField(prefix, 'Encryption')) xuiInboundField(prefix, 'Encryption').value = 'none';
    updateXuiVlessAuthLabel(prefix);
    updateXuiInboundAdvancedPreview(prefix, false);
}

function setXuiFallbacks(prefix, fallbacks) {
    const input = xuiInboundField(prefix, 'Fallbacks');
    if (!input) return;
    input.value = xuiJson(fallbacks);
    updateXuiInboundAdvancedPreview(prefix, false);
}

function addXuiVlessFallback(prefix) {
    const current = xuiReadJsonField(prefix, 'Fallbacks', [], 'Fallbacks', true);
    const fallbacks = Array.isArray(current) ? current : [];
    fallbacks.push({ name: '', alpn: '', path: '', dest: '', xver: 0 });
    setXuiFallbacks(prefix, fallbacks);
}

function fillXuiVlessFallbacks(prefix) {
    const backendId = xuiInboundBackendIdFor(prefix) || xuiDefaultInboundBackendId();
    const currentInboundId = Number(currentXuiEditInboundId || 0);
    const fallbacks = getXuiInboundsForBackend(backendId)
        .filter(inbound => Number(inbound.id || 0) !== currentInboundId && inbound.port)
        .map(inbound => ({
            name: inbound.remark || inbound.tag || `inbound-${inbound.port}`,
            alpn: '',
            path: '',
            dest: String(inbound.port),
            xver: 0
        }));
    if (!fallbacks.length) {
        alert('当前后端没有可自动加入的其他入站节点');
        return;
    }
    setXuiFallbacks(prefix, fallbacks);
}

function syncXuiRealitySniFromTarget(prefix) {
    const dest = xuiInboundField(prefix, 'RealityDest')?.value.trim() || '';
    const host = dest.replace(/^\[?([^\]:]+)\]?.*$/, '$1');
    if (host && xuiInboundField(prefix, 'RealityServerNames')) {
        xuiInboundField(prefix, 'RealityServerNames').value = host;
    }
    updateXuiInboundAdvancedPreview(prefix, false);
}

function randomizeXuiRealityTarget(prefix) {
    const target = XUI_REALITY_TARGET_PRESETS[Math.floor(Math.random() * XUI_REALITY_TARGET_PRESETS.length)];
    if (xuiInboundField(prefix, 'RealityDest')) {
        xuiInboundField(prefix, 'RealityDest').value = target;
    }
    syncXuiRealitySniFromTarget(prefix);
}

function randomizeXuiRealityShortIds(prefix) {
    const values = [8, 4, 8, 2, 8, 8].map(length => xuiRandomHex(length));
    if (xuiInboundField(prefix, 'RealityShortIds')) {
        xuiInboundField(prefix, 'RealityShortIds').value = values.join(', ');
    }
    updateXuiInboundAdvancedPreview(prefix, false);
}

async function fetchXuiRealityCertificate(prefix) {
    const obj = await fetchXuiServerHelper(prefix, '/api/xui/server/x25519-cert', '获取 Reality 证书');
    if (!obj) return;
    const privateKey = xuiFirstValue(obj.privateKey, obj.private_key);
    const publicKey = xuiFirstValue(obj.publicKey, obj.public_key);
    if (privateKey && xuiInboundField(prefix, 'RealityPrivateKey')) xuiInboundField(prefix, 'RealityPrivateKey').value = privateKey;
    if (publicKey && xuiInboundField(prefix, 'RealityPublicKey')) xuiInboundField(prefix, 'RealityPublicKey').value = publicKey;
    updateXuiInboundAdvancedPreview(prefix, false);
}

function clearXuiRealityCertificate(prefix) {
    ['RealityPublicKey', 'RealityPrivateKey'].forEach(field => {
        const input = xuiInboundField(prefix, field);
        if (input) input.value = '';
    });
    updateXuiInboundAdvancedPreview(prefix, false);
}

async function fetchXuiMldsa65Seed(prefix) {
    const obj = await fetchXuiServerHelper(prefix, '/api/xui/server/mldsa65', '获取 ML-DSA-65 Seed');
    if (!obj) return;
    const seed = xuiFirstValue(obj.seed, obj.privateKey, obj.private_key);
    const verify = xuiFirstValue(obj.publicKey, obj.public_key, obj.verify);
    if (seed && xuiInboundField(prefix, 'RealityMldsa65Seed')) xuiInboundField(prefix, 'RealityMldsa65Seed').value = seed;
    if (verify && xuiInboundField(prefix, 'RealityMldsa65Verify')) xuiInboundField(prefix, 'RealityMldsa65Verify').value = verify;
    updateXuiInboundAdvancedPreview(prefix, false);
}

function clearXuiMldsa65Seed(prefix) {
    ['RealityMldsa65Seed', 'RealityMldsa65Verify'].forEach(field => {
        const input = xuiInboundField(prefix, field);
        if (input) input.value = '';
    });
    updateXuiInboundAdvancedPreview(prefix, false);
}

function regenerateXuiInboundPort(prefix = 'add') {
    const backendId = Number(xuiInboundField(prefix, 'BackendId')?.value || xuiInboundEditorStates[prefix]?.backendId || xuiDefaultInboundBackendId());
    const port = randomXuiInboundPort(backendId);
    const portInput = xuiInboundField(prefix, 'Port');
    if (portInput) {
        portInput.value = port;
    }
    xuiInboundEditorStates[prefix] = {
        ...(xuiInboundEditorStates[prefix] || {}),
        backendId,
        autoPort: port
    };
    refreshXuiInboundEditor(prefix);
    updateXuiInboundAdvancedPreview(prefix, false);
}

function refreshXuiInboundEditor(prefix) {
    const protocol = xuiInboundField(prefix, 'Protocol')?.value || 'vless';
    const network = xuiInboundField(prefix, 'Network')?.value || 'tcp';
    const securityInput = xuiInboundField(prefix, 'Security');
    let security = securityInput?.value || 'none';
    const mount = document.getElementById(xuiInboundMountId(prefix));
    if (!mount) return;

    const allowedSecurityValues = protocol === 'vmess'
        ? XUI_VMESS_SECURITY_VALUES
        : (protocol === 'vless' ? XUI_VLESS_SECURITY_VALUES : null);
    if (allowedSecurityValues && !allowedSecurityValues.has(security)) {
        security = 'none';
        if (securityInput) securityInput.value = security;
    }

    const hideProtocolTab = protocol === 'vmess';
    const protocolTabButton = mount.querySelector('[data-xui-inbound-tab="protocol"]');
    const protocolTabPanel = mount.querySelector('[data-xui-inbound-panel="protocol"]');
    if (protocolTabButton) protocolTabButton.classList.toggle('hidden', hideProtocolTab);
    if (protocolTabPanel) protocolTabPanel.classList.toggle('hidden', hideProtocolTab);
    if (hideProtocolTab && protocolTabPanel?.classList.contains('active')) {
        switchXuiInboundEditorTab(prefix, 'base');
    }

    mount.querySelectorAll('[data-xui-protocol-section]').forEach(section => {
        section.classList.toggle('hidden', section.dataset.xuiProtocolSection !== protocol);
    });
    mount.querySelectorAll('[data-xui-network-section]').forEach(section => {
        const target = section.dataset.xuiNetworkSection;
        const visible = target === network
            || (target === 'path' && ['ws', 'httpupgrade', 'xhttp'].includes(network))
            || (target === 'host' && ['ws', 'httpupgrade', 'xhttp'].includes(network));
        section.classList.toggle('hidden', !visible);
    });
    mount.querySelectorAll('[data-xui-security]').forEach(button => {
        const unsupportedForProtocol = allowedSecurityValues && !allowedSecurityValues.has(button.dataset.xuiSecurity);
        button.classList.toggle('hidden', unsupportedForProtocol);
        button.classList.toggle('active', button.dataset.xuiSecurity === security);
    });
    mount.querySelectorAll('[data-xui-security-section]').forEach(section => {
        const target = section.dataset.xuiSecuritySection;
        section.classList.toggle('hidden', !(
            (target === 'tls' && ['tls', 'xtls'].includes(security)) ||
            (target === 'reality' && security === 'reality')
        ));
    });

    const certMode = xuiInboundField(prefix, 'TlsCertMode')?.value || 'file';
    mount.querySelectorAll('[data-xui-cert-mode]').forEach(button => {
        button.classList.toggle('active', button.dataset.xuiCertMode === certMode);
    });
    mount.querySelectorAll('[data-xui-cert-section]').forEach(section => {
        section.classList.toggle('hidden', section.dataset.xuiCertSection !== certMode);
    });

    if (protocol === 'vless') updateXuiVlessAuthLabel(prefix);

    const advancedUse = xuiInboundField(prefix, 'AdvancedUse');
    const advancedPayload = xuiInboundField(prefix, 'AdvancedPayload');
    if (advancedPayload && advancedUse) {
        advancedPayload.readOnly = !advancedUse.checked;
        advancedPayload.classList.toggle('readonly', !advancedUse.checked);
    }
}

function buildXuiInboundSettings(prefix, protocol, existingSettings = {}, silent = false) {
    const clients = Array.isArray(existingSettings.clients) ? xuiDeepClone(existingSettings.clients) : [];
    const accounts = Array.isArray(existingSettings.accounts) ? xuiDeepClone(existingSettings.accounts) : [];
    const peers = Array.isArray(existingSettings.peers) ? xuiDeepClone(existingSettings.peers) : [];

    if (protocol === 'vless') {
        const testseed = [0, 1, 2, 3]
            .map(index => Number(xuiInboundField(prefix, `VisionSeed${index}`)?.value || 0))
            .filter(value => Number.isFinite(value));
        return {
            ...existingSettings,
            clients,
            decryption: xuiInboundField(prefix, 'Decryption')?.value.trim() || 'none',
            encryption: xuiInboundField(prefix, 'Encryption')?.value.trim() || 'none',
            testseed: testseed.length === 4 ? testseed : (Array.isArray(existingSettings.testseed) ? existingSettings.testseed : [900, 500, 900, 256]),
            fallbacks: xuiReadJsonField(prefix, 'Fallbacks', [], 'Fallbacks', silent)
        };
    }
    if (protocol === 'vmess') {
        return {
            ...existingSettings,
            clients,
            disableInsecureEncryption: Boolean(xuiInboundField(prefix, 'DisableInsecureEncryption')?.checked)
        };
    }
    if (protocol === 'trojan') {
        return {
            ...existingSettings,
            clients,
            fallbacks: xuiReadJsonField(prefix, 'TrojanFallbacks', [], 'Fallbacks', silent)
        };
    }
    if (protocol === 'shadowsocks') {
        return {
            ...existingSettings,
            clients,
            method: xuiInboundField(prefix, 'SsMethod')?.value || 'aes-256-gcm',
            password: xuiInboundField(prefix, 'SsPassword')?.value.trim() || existingSettings.password || '',
            network: xuiInboundField(prefix, 'SsNetwork')?.value || 'tcp,udp'
        };
    }
    if (protocol === 'wireguard') {
        return {
            ...existingSettings,
            secretKey: xuiInboundField(prefix, 'WgSecretKey')?.value.trim() || existingSettings.secretKey || '',
            address: String(xuiInboundField(prefix, 'WgAddress')?.value || '10.0.0.1/24').split(',').map(item => item.trim()).filter(Boolean),
            peers: xuiReadJsonField(prefix, 'WgPeers', peers, 'Peers', silent),
            mtu: Number(xuiInboundField(prefix, 'WgMtu')?.value || 1420),
            kernelMode: Boolean(xuiInboundField(prefix, 'WgKernelMode')?.checked),
            workers: Number(xuiInboundField(prefix, 'WgWorkers')?.value || 0)
        };
    }
    if (protocol === 'hysteria2') {
        return {
            ...existingSettings,
            clients,
            masquerade: xuiInboundField(prefix, 'HyMasquerade')?.value.trim() || '',
            up_mbps: Number(xuiInboundField(prefix, 'HyUpMbps')?.value || 100),
            down_mbps: Number(xuiInboundField(prefix, 'HyDownMbps')?.value || 100),
            ignoreClientBandwidth: Boolean(xuiInboundField(prefix, 'HyIgnoreBandwidth')?.checked)
        };
    }
    if (protocol === 'http') {
        return {
            ...existingSettings,
            accounts: xuiReadJsonField(prefix, 'HttpAccounts', accounts, 'Accounts', silent),
            allowTransparent: Boolean(xuiInboundField(prefix, 'AllowTransparent')?.checked),
            userLevel: Number(xuiInboundField(prefix, 'HttpUserLevel')?.value || 0)
        };
    }
    if (protocol === 'socks') {
        return {
            ...existingSettings,
            auth: xuiInboundField(prefix, 'SocksAuth')?.value || 'noauth',
            accounts: xuiReadJsonField(prefix, 'SocksAccounts', accounts, 'Accounts', silent),
            udp: Boolean(xuiInboundField(prefix, 'SocksUdp')?.checked),
            ip: xuiInboundField(prefix, 'SocksIp')?.value.trim() || '127.0.0.1',
            userLevel: Number(existingSettings.userLevel || 0)
        };
    }
    if (protocol === 'dokodemo-door') {
        return {
            ...existingSettings,
            address: xuiInboundField(prefix, 'TargetAddress')?.value.trim() || '',
            port: Number(xuiInboundField(prefix, 'TargetPort')?.value || 0),
            network: xuiInboundField(prefix, 'TargetNetwork')?.value || 'tcp,udp',
            followRedirect: Boolean(xuiInboundField(prefix, 'FollowRedirect')?.checked),
            userLevel: Number(existingSettings.userLevel || 0)
        };
    }
    if (protocol === 'tun') {
        return {
            ...existingSettings,
            mtu: Number(xuiInboundField(prefix, 'TunMtu')?.value || 1500),
            stack: xuiInboundField(prefix, 'TunStack')?.value || 'system',
            endpointIndependentNat: Boolean(xuiInboundField(prefix, 'TunNat')?.checked),
            sniff: Boolean(xuiInboundField(prefix, 'TunSniff')?.checked)
        };
    }
    return { ...existingSettings, clients };
}

function buildXuiInboundStreamSettings(prefix, existingStream = {}, silent = false) {
    const network = xuiInboundField(prefix, 'Network')?.value || 'tcp';
    const security = xuiInboundField(prefix, 'Security')?.value || 'none';
    const acceptProxyProtocol = Boolean(xuiInboundField(prefix, 'AcceptProxyProtocol')?.checked);
    const path = xuiInboundField(prefix, 'Path')?.value.trim() || '/';
    const host = xuiInboundField(prefix, 'Host')?.value.trim() || '';
    const stream = {
        ...existingStream,
        network,
        security
    };

    if (network === 'tcp') {
        stream.tcpSettings = {
            ...(existingStream.tcpSettings || {}),
            acceptProxyProtocol,
            header: { type: xuiInboundField(prefix, 'HttpObfuscation')?.checked ? 'http' : 'none' }
        };
        const masks = xuiReadJsonField(prefix, 'TcpMasks', [], 'TCP Masks', silent);
        if (Array.isArray(masks) && masks.length) stream.tcpSettings.masks = masks;
    }
    if (network === 'kcp') {
        stream.kcpSettings = {
            ...(existingStream.kcpSettings || {}),
            mtu: Number(xuiInboundField(prefix, 'KcpMtu')?.value || 1350),
            tti: Number(xuiInboundField(prefix, 'KcpTti')?.value || 20),
            uplinkCapacity: Number(xuiInboundField(prefix, 'KcpUplink')?.value || 5),
            downlinkCapacity: Number(xuiInboundField(prefix, 'KcpDownlink')?.value || 20),
            congestion: Boolean(xuiInboundField(prefix, 'KcpCongestion')?.checked),
            readBufferSize: Number(existingStream.kcpSettings?.readBufferSize || 2),
            writeBufferSize: Number(existingStream.kcpSettings?.writeBufferSize || 2),
            header: { type: xuiInboundField(prefix, 'KcpHeader')?.value || 'none' }
        };
    }
    if (network === 'ws') {
        stream.wsSettings = {
            ...(existingStream.wsSettings || {}),
            acceptProxyProtocol,
            path,
            host,
            headers: host ? { Host: host } : {}
        };
    }
    if (network === 'grpc') {
        stream.grpcSettings = {
            ...(existingStream.grpcSettings || {}),
            serviceName: xuiInboundField(prefix, 'GrpcServiceName')?.value.trim() || '',
            multiMode: Boolean(existingStream.grpcSettings?.multiMode)
        };
    }
    if (network === 'httpupgrade') {
        stream.httpupgradeSettings = {
            ...(existingStream.httpupgradeSettings || {}),
            acceptProxyProtocol,
            path,
            host,
            headers: host ? { Host: host } : {}
        };
    }
    if (network === 'xhttp') {
        stream.xhttpSettings = {
            ...(existingStream.xhttpSettings || {}),
            path,
            host,
            mode: xuiInboundField(prefix, 'XhttpMode')?.value || 'auto',
            extra: xuiReadJsonField(prefix, 'XhttpExtra', {}, 'XHTTP Extra', silent)
        };
    }

    if (xuiInboundField(prefix, 'Sockopt')?.checked) {
        stream.sockopt = existingStream.sockopt || {
            tcpFastOpen: false,
            tproxy: 'off',
            domainStrategy: 'AsIs',
            dialerProxy: ''
        };
    } else {
        delete stream.sockopt;
    }

    const sni = xuiInboundField(prefix, 'Sni')?.value.trim() || '';
    const alpn = String(xuiInboundField(prefix, 'Alpn')?.value || '').split(',').map(item => item.trim()).filter(Boolean);
    if (security === 'tls' || security === 'xtls') {
        const key = security === 'xtls' ? 'xtlsSettings' : 'tlsSettings';
        const existingTls = existingStream[key] || {};
        const nestedSettings = { ...(existingTls.settings || {}) };
        const certFile = xuiInboundField(prefix, 'CertFile')?.value.trim() || '';
        const keyFile = xuiInboundField(prefix, 'KeyFile')?.value.trim() || '';
        const certContent = xuiInboundField(prefix, 'CertContent')?.value.trim() || '';
        const keyContent = xuiInboundField(prefix, 'KeyContent')?.value.trim() || '';
        const certMode = xuiInboundField(prefix, 'TlsCertMode')?.value || 'file';
        const cipherSuites = xuiInboundField(prefix, 'CipherSuites')?.value || '';
        const fingerprint = xuiInboundField(prefix, 'TlsFingerprint')?.value || '';
        const curvePreferences = xuiListFromText(xuiInboundField(prefix, 'CurvePreferences')?.value);
        const ocspStapling = Number(xuiInboundField(prefix, 'OcspStapling')?.value || 0);
        const usage = xuiInboundField(prefix, 'TlsUsage')?.value || '';
        const masterKeyLog = xuiInboundField(prefix, 'MasterKeyLog')?.value.trim() || '';
        const echKey = xuiInboundField(prefix, 'EchKey')?.value.trim() || '';
        const echConfig = xuiInboundField(prefix, 'EchConfig')?.value.trim() || '';
        const pinnedPeerCertSha256 = xuiListFromText(xuiInboundField(prefix, 'PinnedPeerCertSha256')?.value);
        const verifyPeerCertNames = xuiListFromText(xuiInboundField(prefix, 'VerifyPeerCertNames')?.value);
        const certificate = {};
        if (certMode === 'content') {
            if (certContent) certificate.certificate = certContent;
            if (keyContent) certificate.key = keyContent;
        } else {
            if (certFile) certificate.certificateFile = certFile;
            if (keyFile) certificate.keyFile = keyFile;
        }
        if (fingerprint) nestedSettings.fingerprint = fingerprint;
        if (curvePreferences.length) nestedSettings.curvePreferences = curvePreferences;
        if (usage) nestedSettings.usage = usage;
        if (ocspStapling > 0) nestedSettings.ocspStapling = ocspStapling;
        if (xuiInboundField(prefix, 'TlsOneTimeLoading')?.checked) nestedSettings.oneTimeLoading = true;
        if (xuiInboundField(prefix, 'EchSockopt')?.checked) nestedSettings.echSockopt = true;
        if (echKey) nestedSettings.echKey = echKey;
        if (echConfig) nestedSettings.echConfig = echConfig;
        stream[key] = {
            ...existingTls,
            serverName: sni,
            minVersion: xuiInboundField(prefix, 'TlsMinVersion')?.value || existingTls.minVersion || '1.2',
            maxVersion: xuiInboundField(prefix, 'TlsMaxVersion')?.value || existingTls.maxVersion || '1.3',
            cipherSuites,
            certificates: Object.keys(certificate).length ? [certificate] : (existingTls.certificates || []),
            alpn,
            rejectUnknownSni: Boolean(xuiInboundField(prefix, 'RejectUnknownSni')?.checked),
            disableSystemRoot: Boolean(xuiInboundField(prefix, 'DisableSystemRoot')?.checked),
            enableSessionResumption: Boolean(xuiInboundField(prefix, 'SessionResumption')?.checked),
            fingerprint,
            curvePreferences,
            settings: nestedSettings
        };
        if (masterKeyLog) stream[key].masterKeyLog = masterKeyLog;
        if (ocspStapling > 0) stream[key].ocspStapling = ocspStapling;
        if (xuiInboundField(prefix, 'TlsOneTimeLoading')?.checked) stream[key].oneTimeLoading = true;
        if (usage) stream[key].usage = usage;
        if (echKey) stream[key].echServerKeys = xuiListFromText(echKey);
        if (echConfig) stream[key].echConfigList = xuiListFromText(echConfig);
        if (pinnedPeerCertSha256.length) stream[key].pinnedPeerCertificateChainSha256 = pinnedPeerCertSha256;
        if (verifyPeerCertNames.length) stream[key].verifyPeerCertInNames = verifyPeerCertNames;
        if (security === 'tls') delete stream.xtlsSettings;
        if (security === 'xtls') delete stream.tlsSettings;
        delete stream.realitySettings;
    }
    if (security === 'reality') {
        const target = xuiInboundField(prefix, 'RealityDest')?.value.trim() || 'www.amd.com:443';
        const serverNames = xuiListFromText(xuiInboundField(prefix, 'RealityServerNames')?.value);
        let shortIds = xuiListFromText(xuiInboundField(prefix, 'RealityShortIds')?.value);
        if (!shortIds.length) {
            shortIds = xuiDefaultRealityShortIds();
            const shortIdsInput = xuiInboundField(prefix, 'RealityShortIds');
            if (shortIdsInput) shortIdsInput.value = shortIds.join(', ');
        }
        const publicKey = xuiInboundField(prefix, 'RealityPublicKey')?.value.trim() || '';
        const mldsa65Seed = xuiInboundField(prefix, 'RealityMldsa65Seed')?.value.trim() || '';
        const mldsa65Verify = xuiInboundField(prefix, 'RealityMldsa65Verify')?.value.trim() || '';
        const masterKeyLog = xuiInboundField(prefix, 'RealityMasterKeyLog')?.value.trim() || '';
        const maxTimediff = Number(xuiInboundField(prefix, 'RealityMaxTimeDiff')?.value || 0);
        const limitFallback = xuiReadJsonField(prefix, 'RealityLimitFallback', {}, '限制 Fallback', silent);
        const nestedSettings = {
            ...(existingStream.realitySettings?.settings || {}),
            fingerprint: xuiInboundField(prefix, 'RealityFingerprint')?.value.trim() || 'chrome',
            serverName: serverNames[0] || target.split(':')[0] || 'www.amd.com',
            spiderX: xuiInboundField(prefix, 'RealitySpiderX')?.value.trim() || '/'
        };
        if (publicKey) nestedSettings.publicKey = publicKey;
        if (mldsa65Verify) nestedSettings.mldsa65Verify = mldsa65Verify;
        if (masterKeyLog) nestedSettings.masterKeyLog = masterKeyLog;
        stream.realitySettings = {
            ...(existingStream.realitySettings || {}),
            show: Boolean(xuiInboundField(prefix, 'RealityShow')?.checked),
            xver: Number(xuiInboundField(prefix, 'RealityXver')?.value || 0),
            target,
            dest: target,
            serverNames: serverNames.length ? serverNames : [target.split(':')[0] || 'www.amd.com'],
            privateKey: xuiInboundField(prefix, 'RealityPrivateKey')?.value.trim() || '',
            minClientVer: xuiInboundField(prefix, 'RealityMinClientVer')?.value.trim() || '',
            maxClientVer: xuiInboundField(prefix, 'RealityMaxClientVer')?.value.trim() || '',
            maxTimediff,
            maxTimeDiff: maxTimediff,
            shortIds,
            settings: nestedSettings
        };
        if (publicKey) stream.realitySettings.publicKey = publicKey;
        if (mldsa65Seed) stream.realitySettings.mldsa65Seed = mldsa65Seed;
        if (mldsa65Verify) stream.realitySettings.mldsa65Verify = mldsa65Verify;
        if (masterKeyLog) stream.realitySettings.masterKeyLog = masterKeyLog;
        if (limitFallback && typeof limitFallback === 'object' && Object.keys(limitFallback).length) {
            stream.realitySettings.limitFallback = limitFallback;
        }
        delete stream.tlsSettings;
        delete stream.xtlsSettings;
    }
    if (security === 'none') {
        delete stream.tlsSettings;
        delete stream.xtlsSettings;
        delete stream.realitySettings;
    }
    return stream;
}

function buildXuiInboundSniffing(prefix) {
    const destOverride = ['http', 'tls', 'quic', 'fakedns'].filter(item => xuiInboundField(prefix, `Sniff${item}`)?.checked);
    const sniffing = {
        enabled: Boolean(xuiInboundField(prefix, 'SniffingEnabled')?.checked),
        destOverride,
        metadataOnly: Boolean(xuiInboundField(prefix, 'SniffMetadataOnly')?.checked),
        routeOnly: Boolean(xuiInboundField(prefix, 'SniffRouteOnly')?.checked)
    };
    const ipsExcluded = xuiListFromText(xuiInboundField(prefix, 'SniffIpsExcluded')?.value);
    const domainsExcluded = xuiListFromText(xuiInboundField(prefix, 'SniffDomainsExcluded')?.value);
    if (ipsExcluded.length) sniffing.ipsExcluded = ipsExcluded;
    if (domainsExcluded.length) sniffing.domainsExcluded = domainsExcluded;
    return sniffing;
}

function buildXuiInboundPayloadFromForm(prefix, silent = false) {
    try {
        const state = xuiInboundEditorStates[prefix] || {};
        const seed = xuiDeepClone(state.seedPayload || xuiInboundDefaultPayload());
        ['id', 'up', 'down', 'clientStats', 'raw'].forEach(key => delete seed[key]);

        const protocol = xuiInboundField(prefix, 'Protocol')?.value || 'vless';
        const port = Number(xuiInboundField(prefix, 'Port')?.value || (silent ? 443 : NaN));
        const remark = xuiInboundField(prefix, 'Remark')?.value.trim() || (silent ? 'New Inbound' : '');
        if (!remark) {
            if (!silent) alert('请填写节点备注');
            return null;
        }
        if (!Number.isInteger(port) || port < 1 || port > 65535) {
            if (!silent) alert('端口必须是 1-65535 的整数');
            return null;
        }

        const totalGb = Number(xuiInboundField(prefix, 'TotalGb')?.value || 0);
        const payload = {
            ...seed,
            enable: Boolean(xuiInboundField(prefix, 'Enable')?.checked),
            remark,
            listen: xuiInboundField(prefix, 'Listen')?.value.trim() || '',
            port,
            protocol,
            total: totalGb > 0 ? Math.round(totalGb * 1024 * 1024 * 1024) : 0,
            expiryTime: xuiDateTimeLocalToMs(xuiInboundField(prefix, 'ExpiryTime')?.value),
            reset: Number(xuiInboundField(prefix, 'Reset')?.value || 0),
            settings: buildXuiInboundSettings(prefix, protocol, seed.settings || {}, silent),
            streamSettings: buildXuiInboundStreamSettings(prefix, seed.streamSettings || {}, silent),
            sniffing: buildXuiInboundSniffing(prefix)
        };
        const subSort = Number(xuiInboundField(prefix, 'SubSort')?.value || 0);
        if (subSort) payload.subSort = subSort;
        return payload;
    } catch (error) {
        if (!silent) console.error('构建入站 payload 失败:', error);
        return null;
    }
}

function updateXuiInboundAdvancedPreview(prefix, force = false) {
    const advancedUse = xuiInboundField(prefix, 'AdvancedUse');
    const advancedPayload = xuiInboundField(prefix, 'AdvancedPayload');
    if (!advancedPayload) return;
    refreshXuiInboundEditor(prefix);
    if (!advancedUse?.checked || force) {
        const payload = buildXuiInboundPayloadFromForm(prefix, true);
        if (payload) advancedPayload.value = xuiJson(payload);
    }
}

function applyXuiInboundAdvancedJson(prefix) {
    const advancedPayload = xuiInboundField(prefix, 'AdvancedPayload');
    if (!advancedPayload) return;
    let parsed;
    try {
        parsed = JSON.parse(advancedPayload.value);
    } catch (error) {
        alert('高级 JSON 格式错误: ' + error.message);
        return;
    }
    xuiInboundEditorStates[prefix] = {
        ...(xuiInboundEditorStates[prefix] || {}),
        seedPayload: parsed,
        inbound: { raw: parsed, settings: parsed.settings, streamSettings: parsed.streamSettings, sniffing: parsed.sniffing }
    };
    renderXuiInboundEditor(prefix, xuiInboundEditorStates[prefix].inbound);
}

function formatXuiInboundAdvancedJson(prefix) {
    const advancedPayload = xuiInboundField(prefix, 'AdvancedPayload');
    if (!advancedPayload) return;
    try {
        advancedPayload.value = xuiJson(JSON.parse(advancedPayload.value));
    } catch (error) {
        alert('高级 JSON 格式错误: ' + error.message);
    }
}

function collectXuiInboundPayload(prefix) {
    const advancedUse = xuiInboundField(prefix, 'AdvancedUse');
    const advancedPayload = xuiInboundField(prefix, 'AdvancedPayload');
    if (advancedUse?.checked) {
        try {
            return {
                inbound_payload: JSON.parse(advancedPayload.value),
                preserve_clients: true
            };
        } catch (error) {
            alert('高级 JSON 格式错误: ' + error.message);
            return null;
        }
    }
    const payload = buildXuiInboundPayloadFromForm(prefix, false);
    if (!payload) return null;
    return {
        inbound_payload: payload,
        preserve_clients: true
    };
}

function showAddXuiInboundModal() {
    const backendId = xuiDefaultInboundBackendId();
    if (!backendId) {
        alert('请先新增并配置一个 3x-ui 后端，再创建入站节点');
        return;
    }
    xuiInboundEditorStates.add = { activeTab: 'base', mode: 'add', inbound: null, backendId };
    renderXuiInboundEditor('add');
    document.getElementById('addXuiInboundModal').style.display = 'block';
}

async function createXuiInbound() {
    const backendId = Number(xuiInboundField('add', 'BackendId')?.value || xuiInboundEditorStates.add?.backendId || 0);
    if (!backendId) {
        alert('请选择要生成入站节点的 3x-ui 后端');
        return;
    }
    const payload = collectXuiInboundPayload('add');
    if (!payload) return;
    payload.backend_id = backendId;

    try {
        const response = await fetch('/api/xui/inbounds', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.success) {
            closeModal('addXuiInboundModal');
            setCurrentXuiBackendId(backendId);
            syncCurrentXuiInboundsFromGroup();
            syncCurrentXuiClientsFromGroup();
            renderXuiBackendCards();
            renderXuiInboundGroups();
            await loadXuiInbounds(backendId, { expand: true });
            await loadXuiClients(backendId);
        } else {
            alert('创建失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        alert('创建失败: ' + error.message);
    }
}

function showEditXuiInboundModal(inboundId, backendId = currentXuiBackendId) {
    const targetBackendId = Number(backendId || currentXuiBackendId);
    const inbound = getXuiInboundsForBackend(targetBackendId).find(item => Number(item.id) === Number(inboundId));
    if (!inbound) {
        alert('入站节点不存在');
        return;
    }

    setCurrentXuiBackendId(targetBackendId);
    syncCurrentXuiInboundsFromGroup();
    renderXuiBackendCards();
    renderXuiInboundGroups();
    currentXuiEditInboundId = inboundId;
    currentXuiEditInboundBackendId = targetBackendId;
    xuiInboundEditorStates.edit = { activeTab: 'base', mode: 'edit', inbound };
    renderXuiInboundEditor('edit', inbound);
    document.getElementById('editXuiInboundModal').style.display = 'block';
}

async function saveXuiInboundEdit() {
    if (!currentXuiEditInboundId) return;
    const targetBackendId = currentXuiEditInboundBackendId || currentXuiBackendId;
    if (!targetBackendId) return;
    const payload = collectXuiInboundPayload('edit');
    if (!payload) return;
    payload.backend_id = targetBackendId;

    try {
        const response = await fetch(`/api/xui/inbounds/${currentXuiEditInboundId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.success) {
            closeModal('editXuiInboundModal');
            await loadXuiInbounds(targetBackendId, { expand: true });
            if (Number(currentXuiBackendId) === Number(targetBackendId)) {
                await loadXuiClients();
            }
        } else {
            alert('保存失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        alert('保存失败: ' + error.message);
    }
}

async function deleteXuiInbound(inboundId, backendId = currentXuiBackendId, actionButton = null) {
    const targetBackendId = Number(backendId || currentXuiBackendId);
    if (!targetBackendId) return;
    if (!confirm('确定要删除这个 3x-ui 入站节点吗？此操作会影响挂载的客户端。')) return;
    const originalText = actionButton?.textContent || '删除节点';

    try {
        if (actionButton) {
            actionButton.disabled = true;
            actionButton.textContent = '删除中...';
        }
        const response = await fetch(`/api/xui/inbounds/${inboundId}?${xuiBackendQueryFor(targetBackendId)}`, { method: 'DELETE' });
        let data;
        try {
            data = await response.json();
        } catch (parseError) {
            throw new Error(`HTTP ${response.status}: ${response.statusText || '响应不是 JSON'}`);
        }
        if (!response.ok || !data.success) {
            throw new Error(data.message || '未知错误');
        }

        const group = getXuiInboundGroup(targetBackendId);
        group.inbounds = (group.inbounds || []).filter(item => Number(item.id) !== Number(inboundId));
        const clientGroup = getXuiClientGroup(targetBackendId);
        clientGroup.clients = (clientGroup.clients || []).filter(client =>
            !(client.inboundIds || []).map(Number).includes(Number(inboundId))
        );
        if (Number(currentXuiBackendId) === Number(targetBackendId)) {
            syncCurrentXuiInboundsFromGroup();
            syncCurrentXuiClientsFromGroup();
        }
        renderXuiInboundGroups();

        await loadXuiInbounds(targetBackendId, { expand: true });
        if (Number(currentXuiBackendId) === Number(targetBackendId)) {
            await loadXuiClients();
        }
    } catch (error) {
        alert('删除失败: ' + error.message);
    } finally {
        if (actionButton && document.body.contains(actionButton)) {
            actionButton.disabled = false;
            actionButton.textContent = originalText;
        }
    }
}

function renderXuiInboundOptions(selectId, selectedIds = [], backendId = currentXuiBackendId) {
    const select = document.getElementById(selectId);
    const selected = new Set(selectedIds.map(Number));
    const inbounds = getXuiInboundsForBackend(backendId);
    select.innerHTML = '';

    if (!inbounds.length) {
        const option = document.createElement('option');
        option.textContent = '暂无可用入站节点';
        option.disabled = true;
        select.appendChild(option);
        return;
    }

    inbounds.forEach(inbound => {
        const option = document.createElement('option');
        option.value = inbound.id;
        option.textContent = `${inbound.remark} (${String(inbound.protocol).toUpperCase()} :${inbound.port})`;
        option.selected = selected.has(Number(inbound.id));
        select.appendChild(option);
    });
}

async function showAddXuiClientModal(backendId = currentXuiBackendId, inboundId = null) {
    const targetBackendId = Number(backendId || currentXuiBackendId);
    if (!targetBackendId) {
        alert('请先选择或新增一个 3x-ui 后端');
        return;
    }

    setCurrentXuiBackendId(targetBackendId);
    syncCurrentXuiInboundsFromGroup();
    syncCurrentXuiClientsFromGroup();
    renderXuiBackendCards();
    renderXuiInboundGroups();

    const group = getXuiInboundGroup(targetBackendId);
    if (!group.loaded && !group.loading) {
        await loadXuiInbounds(targetBackendId, { expand: true });
    }

    const selectedIds = inboundId ? [Number(inboundId)] : [];
    const backend = xuiBackends.find(item => Number(item.id) === targetBackendId);
    const inbound = inboundId
        ? getXuiInboundsForBackend(targetBackendId).find(item => Number(item.id) === Number(inboundId))
        : null;
    const hint = document.getElementById('xuiClientNodeHint');
    if (hint) {
        hint.textContent = inbound
            ? `将客户端挂载到：${backend?.name || '当前后端'} / ${inbound.remark || ('节点 ' + inbound.id)}`
            : '请选择要挂载的入站节点。';
    }
    document.getElementById('xuiClientEmail').value = '';
    document.getElementById('xuiClientSubId').value = '';
    document.getElementById('xuiClientTotalGb').value = 0;
    document.getElementById('xuiClientExpiryDays').value = 0;
    document.getElementById('xuiClientLimitIp').value = 0;
    document.getElementById('xuiClientComment').value = '';
    document.getElementById('xuiClientEnable').checked = true;
    renderXuiInboundOptions('xuiClientInboundIds', selectedIds, targetBackendId);
    document.getElementById('addXuiClientModal').style.display = 'block';
}

async function createXuiClient() {
    if (!ensureXuiBackendSelected()) return;

    const email = document.getElementById('xuiClientEmail').value.trim();
    const inboundIds = getSelectedNumberValues('xuiClientInboundIds');
    if (!email) {
        alert('请填写客户端 Email / 唯一标识');
        return;
    }
    if (!inboundIds.length) {
        alert('请至少选择一个入站节点');
        return;
    }

    const payload = {
        email,
        sub_id: document.getElementById('xuiClientSubId').value.trim(),
        total_gb: document.getElementById('xuiClientTotalGb').value,
        expiry_days: document.getElementById('xuiClientExpiryDays').value,
        limit_ip: document.getElementById('xuiClientLimitIp').value,
        comment: document.getElementById('xuiClientComment').value.trim(),
        enable: document.getElementById('xuiClientEnable').checked,
        inbound_ids: inboundIds,
        backend_id: currentXuiBackendId
    };

    try {
        const response = await fetch('/api/xui/clients', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.success) {
            closeModal('addXuiClientModal');
            await loadXuiInbounds(currentXuiBackendId, { expand: true, withClients: false });
            await loadXuiClients(currentXuiBackendId);
        } else {
            alert('创建失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        alert('创建失败: ' + error.message);
    }
}

async function showEditXuiClientModal(email, backendId = currentXuiBackendId) {
    const targetBackendId = Number(backendId || currentXuiBackendId);
    setCurrentXuiBackendId(targetBackendId);
    syncCurrentXuiInboundsFromGroup();
    syncCurrentXuiClientsFromGroup();

    if (!getXuiInboundGroup(targetBackendId).loaded) {
        await loadXuiInbounds(targetBackendId, { expand: true, withClients: false });
    }

    const client = getXuiClientsForBackend(targetBackendId).find(item => item.email === email);
    if (!client) {
        alert('客户端不存在');
        return;
    }

    currentXuiEditClientEmail = email;
    currentXuiEditClientBackendId = targetBackendId;
    document.getElementById('editXuiClientEmailLabel').textContent = email;
    document.getElementById('editXuiClientUsageLabel').textContent =
        `${formatBytes(client.traffic?.used || 0)} / ${client.totalGB ? formatBytes(client.totalGB) : '不限'}`;
    document.getElementById('editXuiClientTotalGb').value = xuiBytesToGb(client.totalGB);
    document.getElementById('editXuiClientExpiryDays').value = xuiDaysFromExpiry(client.expiryTime);
    document.getElementById('editXuiClientLimitIp').value = client.limitIp || 0;
    document.getElementById('editXuiClientComment').value = client.comment || '';
    document.getElementById('editXuiClientEnable').checked = client.enable !== false;
    renderXuiInboundOptions('editXuiClientInboundIds', client.inboundIds || [], targetBackendId);
    document.getElementById('editXuiClientModal').style.display = 'block';
}

async function saveXuiClientEdit() {
    if (!currentXuiEditClientEmail) return;
    const targetBackendId = currentXuiEditClientBackendId || currentXuiBackendId;
    if (!targetBackendId) return;

    const payload = {
        total_gb: document.getElementById('editXuiClientTotalGb').value,
        expiry_days: document.getElementById('editXuiClientExpiryDays').value,
        limit_ip: document.getElementById('editXuiClientLimitIp').value,
        comment: document.getElementById('editXuiClientComment').value.trim(),
        enable: document.getElementById('editXuiClientEnable').checked,
        inbound_ids: getSelectedNumberValues('editXuiClientInboundIds'),
        backend_id: targetBackendId
    };

    try {
        const response = await fetch(`/api/xui/clients/${encodeURIComponent(currentXuiEditClientEmail)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.success) {
            closeModal('editXuiClientModal');
            await loadXuiInbounds(targetBackendId, { expand: true, withClients: false });
            await loadXuiClients(targetBackendId);
        } else {
            alert('保存失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        alert('保存失败: ' + error.message);
    }
}

async function deleteXuiClient(email, backendId = currentXuiBackendId) {
    const targetBackendId = Number(backendId || currentXuiBackendId);
    if (!targetBackendId) return;
    if (!confirm(`确定要删除客户端 ${email} 吗？`)) return;

    try {
        const response = await fetch(`/api/xui/clients/${encodeURIComponent(email)}?${xuiBackendQueryFor(targetBackendId)}`, { method: 'DELETE' });
        const data = await response.json();
        if (data.success) {
            await loadXuiInbounds(targetBackendId, { expand: true, withClients: false });
            await loadXuiClients(targetBackendId);
        } else {
            alert('删除失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}

// ============ 管理员设置============

async function loadAdminProfile() {
    try {
        const response = await fetch('/api/admin/profile');
        const data = await response.json();
        
        document.getElementById('current-username').textContent = data.username;
        document.getElementById('account-created').textContent = data.created_at;
    } catch (error) {
        console.error('加载管理员信息失败', error);
    }
}

async function changePassword() {
    const currentPassword = document.getElementById('current-password').value.trim();
    const newPassword = document.getElementById('new-password').value.trim();
    const confirmPassword = document.getElementById('confirm-password').value.trim();
    
    // 验证输入
    if (!currentPassword || !newPassword || !confirmPassword) {
        alert('请填写完整信息');
        return;
    }
    
    if (newPassword.length < 6) {
        alert('新密码至少需要 6 位字符');
        return;
    }
    
    if (newPassword !== confirmPassword) {
        alert('两次输入的新密码不一致');
        return;
    }
    
    try {
        const response = await fetch('/api/admin/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // 清空表单
            document.getElementById('current-password').value = '';
            document.getElementById('new-password').value = '';
            document.getElementById('confirm-password').value = '';
        } else {
            alert('❌ ' + data.message);
        }
    } catch (error) {
        alert('修改失败: ' + error.message);
    }
}

async function changeUsername() {
    const newUsername = document.getElementById('new-username').value.trim();
    const password = document.getElementById('username-password').value.trim();
    
    // 验证输入
    if (!newUsername || !password) {
        alert('请填写完整信息');
        return;
    }
    
    if (newUsername.length < 3) {
        alert('用户名至少需要 3 位字符');
        return;
    }
    
    if (!confirm('确定要修改用户名吗？修改后需要使用新用户名登录。')) {
        return;
    }
    
    try {
        const response = await fetch('/api/admin/change-username', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                new_username: newUsername,
                password: password
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // 更新显示
            document.getElementById('current-username').textContent = newUsername;
            document.querySelector('.admin-name').textContent = '👤 ' + newUsername;
            // 清空表单
            document.getElementById('new-username').value = '';
            document.getElementById('username-password').value = '';
        } else {
            alert('❌ ' + data.message);
        }
    } catch (error) {
        alert('修改失败: ' + error.message);
    }
}

// ============ 模板管理 ============

async function loadTemplates() {
    try {
        const response = await fetch('/api/templates');
        allTemplates = await response.json();
        
        const tbody = document.querySelector('#templates-table tbody');
        tbody.innerHTML = '';
        
        allTemplates.forEach(template => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${template.name}</strong></td>
                <td>${template.description || '-'}</td>
                <td><span class="badge badge-info">${template.usage_count} 次</span></td>
                <td>${template.is_default ? '<span class="badge badge-success">默认</span>' : '-'}</td>
                <td>${template.created_at}</td>
                <td class="action-buttons">
                    <button class="btn btn-primary btn-small" onclick="showEditTemplateModal(${template.id})">编辑</button>
                    ${!template.is_default ? `<button class="btn btn-success btn-small" onclick="setDefaultTemplate(${template.id})">设为默认</button>` : ''}
                    <button class="btn btn-danger btn-small" onclick="deleteTemplate(${template.id})">删除</button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('加载模板失败:', error);
    }
}

function showAddTemplateModal() {
    document.getElementById('templateName').value = '';
    document.getElementById('templateDescription').value = '';
    document.getElementById('templateContent').value = '';
    document.getElementById('addTemplateModal').style.display = 'block';
}

async function addTemplate() {
    const name = document.getElementById('templateName').value.trim();
    const description = document.getElementById('templateDescription').value.trim();
    const content = document.getElementById('templateContent').value.trim();
    
    if (!name || !content) {
        alert('请填写模板名称和内容');
        return;
    }
    
    try {
        const response = await fetch('/api/templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, content })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('addTemplateModal');
            loadTemplates();
            loadStats();
        } else {
            alert('❌ ' + data.message);
        }
    } catch (error) {
        alert('创建失败: ' + error.message);
    }
}

async function showEditTemplateModal(templateId) {
    currentEditTemplateId = templateId;
    
    try {
        const response = await fetch(`/api/templates/${templateId}`);
        const template = await response.json();
        
        document.getElementById('editTemplateName').value = template.name;
        document.getElementById('editTemplateDescription').value = template.description || '';
        document.getElementById('editTemplateContent').value = template.content;
        document.getElementById('editTemplateModal').style.display = 'block';
    } catch (error) {
        alert('加载模板失败: ' + error.message);
    }
}

async function saveTemplateEdit() {
    const name = document.getElementById('editTemplateName').value.trim();
    const description = document.getElementById('editTemplateDescription').value.trim();
    const content = document.getElementById('editTemplateContent').value.trim();
    
    if (!name || !content) {
        alert('请填写模板名称和内容');
        return;
    }
    
    try {
        const response = await fetch(`/api/templates/${currentEditTemplateId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, content })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('editTemplateModal');
            loadTemplates();
        } else {
            alert('❌ ' + data.message);
        }
    } catch (error) {
        alert('保存失败: ' + error.message);
    }
}

async function deleteTemplate(templateId) {
    if (!confirm('确定要删除此模板吗？')) return;
    
    try {
        const response = await fetch(`/api/templates/${templateId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                loadTemplates();
                loadStats();
            } else {
                alert('❌ ' + data.message);
            }
        } else {
            // 处理 400 状态码
            const data = await response.json();
            alert('❌ ' + (data.message || '删除失败'));
        }
    } catch (error) {
        console.error('删除模板错误:', error);
        alert('删除失败: ' + error.message);
    }
}

async function setDefaultTemplate(templateId) {
    try {
        const response = await fetch(`/api/templates/${templateId}/set-default`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            loadTemplates();
        } else {
            alert('❌ 设置失败');
        }
    } catch (error) {
        alert('设置失败: ' + error.message);
    }
}

// 导入配置文件相关
let importFileContent = '';

function showImportTemplateModal() {
    document.getElementById('importTemplateName').value = '';
    document.getElementById('importTemplateDescription').value = '';
    document.getElementById('importTemplateFile').value = '';
    document.getElementById('importPreviewContainer').style.display = 'none';
    document.getElementById('importTemplatePreview').value = '';
    document.getElementById('importTemplateBtn').disabled = true;
    importFileContent = '';
    document.getElementById('importTemplateModal').style.display = 'block';
}

function handleTemplateFileSelect(event) {
    const file = event.target.files[0];
    if (!file) {
        importFileContent = '';
        document.getElementById('importTemplateBtn').disabled = true;
        document.getElementById('importPreviewContainer').style.display = 'none';
        return;
    }
    
    const reader = new FileReader();
    reader.onload = function(e) {
        importFileContent = e.target.result;
        
        // 显示预览（前50行）
        const lines = importFileContent.split('\n');
        const preview = lines.slice(0, 50).join('\n');
        document.getElementById('importTemplatePreview').value = preview +
            (lines.length > 50 ? '\n\n... 还有 ' + (lines.length - 50) + ' 行' : '');
        document.getElementById('importPreviewContainer').style.display = 'block';
        
        // 启用导入按钮
        document.getElementById('importTemplateBtn').disabled = false;
        
        if (!document.getElementById('importTemplateName').value) {
            const filename = file.name.replace(/\.(yaml|yml)$/i, '');
            document.getElementById('importTemplateName').value = filename;
        }
    };
    
    reader.onerror = function() {
        alert('读取文件失败');
        document.getElementById('importTemplateBtn').disabled = true;
    };
    
    reader.readAsText(file, 'UTF-8');
}

async function importTemplateFromFile() {
    const name = document.getElementById('importTemplateName').value.trim();
    const description = document.getElementById('importTemplateDescription').value.trim();
    
    if (!name) {
        alert('请填写模板名称');
        return;
    }
    
    if (!importFileContent) {
        alert('请选择配置文件');
        return;
    }
    
    try {
        const response = await fetch('/api/templates/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                description: description,
                content: importFileContent
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('importTemplateModal');
            loadTemplates();
            loadStats();
        } else {
            alert('❌ ' + data.message);
        }
    } catch (error) {
        alert('导入失败: ' + error.message);
    }
}

// ============ 节点编辑功能 ============

async function showEditNodeModal(nodeId) {
    currentEditNodeId = nodeId;
    
    // 获取节点信息
    try {
        const response = await fetch(`/api/nodes/${nodeId}/detail`);
        const node = await response.json();
        
        if (!node) {
            alert('节点不存在');
            return;
        }
        
        // 保存协议类型（用于保存时使用）
        currentEditNodeProtocol = node.protocol;
        
        // 填充基本信息
        document.getElementById('editNodeName').value = node.name;
        document.getElementById('editNodeProtocol').value = node.protocol.toUpperCase();
        
        // 生成配置字段
        const fieldsContainer = document.getElementById('editNodeConfigFields');
        fieldsContainer.innerHTML = '';
        
        renderNodeConfigFields(fieldsContainer, node.protocol, node.config);
        
        document.getElementById('editNodeModal').style.display = 'block';
    } catch (error) {
        alert('加载节点信息失败: ' + error.message);
    }
}

async function saveNodeEdit() {
    const name = document.getElementById('editNodeName').value.trim();
    
    if (!name) {
        alert('节点名称不能为空');
        return;
    }
    
    // 收集配置数据
    const config = collectNodeConfig('editNodeConfigFields');
    config.name = name;
    config.type = currentEditNodeProtocol; // 添加协议类型
    
    try {
        const response = await fetch(`/api/nodes/${currentEditNodeId}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('editNodeModal');
            // 刷新所有相关数据
            loadNodes();
            loadUsers();
            loadSubscriptions();
        } else {
            alert('❌ ' + data.message);
        }
    } catch (error) {
        alert('更新失败: ' + error.message);
    }
}

// ============ 手动创建节点功能 ============

function showManualCreateNodeModal() {
    // 填充订阅选择下拉框
    const select = document.getElementById('manualNodeSubscription');
    select.innerHTML = '<option value="">不归属任何分组</option>';
    allSubscriptions.forEach(sub => {
        const option = document.createElement('option');
        option.value = sub.id;
        option.textContent = sub.name;
        select.appendChild(option);
    });
    
    // 重置表单
    document.getElementById('manualNodeName').value = '';
    document.getElementById('manualNodeProtocol').value = '';
    document.getElementById('manualNodeConfigFields').innerHTML = '';
    
    document.getElementById('manualCreateNodeModal').style.display = 'block';
}

function updateManualNodeFields() {
    const protocol = document.getElementById('manualNodeProtocol').value;
    const fieldsContainer = document.getElementById('manualNodeConfigFields');
    
    if (!protocol) {
        fieldsContainer.innerHTML = '';
        return;
    }
    
    fieldsContainer.innerHTML = '';
    renderNodeConfigFields(fieldsContainer, protocol, {});
}

async function createManualNode() {
    const name = document.getElementById('manualNodeName').value.trim();
    const protocol = document.getElementById('manualNodeProtocol').value;
    const subscription_id = document.getElementById('manualNodeSubscription').value || null;
    
    if (!name) {
        alert('请输入节点名称');
        return;
    }
    
    if (!protocol) {
        alert('请选择协议类型');
        return;
    }
    
    // 收集配置数据
    const config = collectNodeConfig('manualNodeConfigFields');
    config.name = name;
    config.type = protocol;
    
    try {
        const response = await fetch('/api/nodes/manual-create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config, subscription_id })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeModal('manualCreateNodeModal');
            loadNodes();
            loadSubscriptions(); // 刷新订阅列表以更新节点数
            loadUsers(); // 刷新用户列表以更新节点数
            loadStats();
        } else {
            alert('❌ ' + data.message);
        }
    } catch (error) {
        alert('创建失败: ' + error.message);
    }
}

// ============ 节点配置字段渲染 ============

function renderNodeConfigFields(container, protocol, config) {
    const fields = getProtocolFields(protocol);
    
    // 预处理配置 - 将嵌套配置展开为平面字段
    const flatConfig = { ...config };
    
    // WebSocket 配置展开
    if (config['ws-opts']) {
        if (config['ws-opts']['path']) flatConfig['ws-path'] = config['ws-opts']['path'];
        if (config['ws-opts']['headers'] && config['ws-opts']['headers']['Host']) {
            flatConfig['ws-host'] = config['ws-opts']['headers']['Host'];
        }
    }
    
    // HTTP/2 配置展开
    if (config['h2-opts']) {
        if (config['h2-opts']['path']) flatConfig['h2-path'] = config['h2-opts']['path'];
        if (config['h2-opts']['host'] && config['h2-opts']['host'][0]) {
            flatConfig['h2-host'] = config['h2-opts']['host'][0];
        }
    }
    
    // gRPC 配置展开
    if (config['grpc-opts'] && config['grpc-opts']['grpc-service-name']) {
        flatConfig['grpc-service-name'] = config['grpc-opts']['grpc-service-name'];
    }
    
    // Reality 配置展开
    if (config['reality-opts']) {
        if (config['reality-opts']['public-key']) {
            flatConfig['reality-public-key'] = config['reality-opts']['public-key'];
        }
        if (config['reality-opts']['short-id']) {
            flatConfig['reality-short-id'] = config['reality-opts']['short-id'];
        }
    }
    
    // SS 插件配置展开
    if (config['plugin-opts']) {
        if (config['plugin-opts']['mode']) {
            flatConfig['plugin-opts-mode'] = config['plugin-opts']['mode'];
        }
        if (config['plugin-opts']['host']) {
            flatConfig['plugin-opts-host'] = config['plugin-opts']['host'];
        }
    }
    
    // ALPN 数组转字符串
    if (config['alpn'] && Array.isArray(config['alpn'])) {
        flatConfig['alpn'] = config['alpn'].join(', ');
    }
    
    // 渲染字段
    fields.forEach(field => {
        const formGroup = document.createElement('div');
        formGroup.className = 'form-group';
        
        const label = document.createElement('label');
        label.textContent = field.label;
        if (field.required) {
            label.innerHTML += ' <span style="color: red;">*</span>';
        }
        formGroup.appendChild(label);
        
        let input;
        
        if (field.type === 'select') {
            input = document.createElement('select');
            field.options.forEach(opt => {
                const option = document.createElement('option');
                option.value = opt.value;
                option.textContent = opt.label;
                input.appendChild(option);
            });
            const value = flatConfig[field.key];
            input.value = value !== undefined ? value : (field.default || '');
        } else if (field.type === 'checkbox') {
            input = document.createElement('input');
            input.type = 'checkbox';
            const value = flatConfig[field.key];
            input.checked = value !== undefined ? value : (field.default || false);
        } else if (field.type === 'number') {
            input = document.createElement('input');
            input.type = 'number';
            const value = flatConfig[field.key];
            input.value = value !== undefined ? value : (field.default || '');
            if (field.min !== undefined) input.min = field.min;
            if (field.max !== undefined) input.max = field.max;
        } else {
            input = document.createElement('input');
            input.type = 'text';
            const value = flatConfig[field.key];
            input.value = value !== undefined ? value : (field.default || '');
            if (field.placeholder) input.placeholder = field.placeholder;
        }
        
        input.id = `node-field-${field.key}`;
        input.dataset.key = field.key;
        
        formGroup.appendChild(input);
        
        // 个UUID 字段添加生成按钮
        if (field.key === 'uuid') {
            const uuidBtn = document.createElement('button');
            uuidBtn.type = 'button';
            uuidBtn.className = 'btn btn-secondary btn-small';
            uuidBtn.textContent = '🎲 生成UUID';
            uuidBtn.style.marginTop = '5px';
            uuidBtn.onclick = function() {
                input.value = generateUUID();
            };
            formGroup.appendChild(uuidBtn);
        }
        
        if (field.description) {
            const desc = document.createElement('small');
            desc.style.color = '#666';
            desc.textContent = field.description;
            formGroup.appendChild(desc);
        }
        
        container.appendChild(formGroup);
    });
}

function collectNodeConfig(containerId) {
    const container = document.getElementById(containerId);
    const inputs = container.querySelectorAll('input, select, textarea');
    const config = {};
    
    inputs.forEach(input => {
        const key = input.dataset.key;
        if (!key) return;
        
        if (input.type === 'checkbox') {
            config[key] = input.checked;
        } else if (input.type === 'number') {
            const value = input.value.trim();
            if (value) {
                config[key] = parseInt(value);
            }
        } else {
            const value = input.value.trim();
            if (value) {
                config[key] = value;
            }
        }
    });
    
    // 处理传输层配置 - 转换为 Clash 格式
    const network = config['network'];
    
    // WebSocket 配置
    if (network === 'ws') {
        if (config['ws-path'] || config['ws-host']) {
            config['ws-opts'] = {};
            if (config['ws-path']) {
                config['ws-opts']['path'] = config['ws-path'];
                delete config['ws-path'];
            }
            if (config['ws-host']) {
                config['ws-opts']['headers'] = { 'Host': config['ws-host'] };
                delete config['ws-host'];
            }
        }
    }
    
    // HTTP/2 配置
    if (network === 'h2') {
        if (config['h2-path'] || config['h2-host']) {
            config['h2-opts'] = {};
            if (config['h2-path']) {
                config['h2-opts']['path'] = config['h2-path'];
                delete config['h2-path'];
            }
            if (config['h2-host']) {
                config['h2-opts']['host'] = [config['h2-host']];
                delete config['h2-host'];
            }
        }
    }
    
    // gRPC 配置
    if (network === 'grpc' && config['grpc-service-name']) {
        config['grpc-opts'] = {
            'grpc-service-name': config['grpc-service-name']
        };
        delete config['grpc-service-name'];
    }
    
    // Reality 配置
    if (config['reality-public-key'] || config['reality-short-id']) {
        config['reality-opts'] = {};
        if (config['reality-public-key']) {
            config['reality-opts']['public-key'] = config['reality-public-key'];
            delete config['reality-public-key'];
        }
        if (config['reality-short-id']) {
            config['reality-opts']['short-id'] = config['reality-short-id'];
            delete config['reality-short-id'];
        }
    }
    
    // SS 插件配置
    if (config['plugin']) {
        if (config['plugin-opts-mode'] || config['plugin-opts-host']) {
            config['plugin-opts'] = {};
            if (config['plugin-opts-mode']) {
                config['plugin-opts']['mode'] = config['plugin-opts-mode'];
                delete config['plugin-opts-mode'];
            }
            if (config['plugin-opts-host']) {
                config['plugin-opts']['host'] = config['plugin-opts-host'];
                delete config['plugin-opts-host'];
            }
        }
    }
    
    // ALPN 处理（字符串转数组）
    if (config['alpn']) {
        config['alpn'] = config['alpn'].split(',').map(s => s.trim()).filter(s => s);
    }
    
    return config;
}

function getProtocolFields(protocol) {
    const commonFields = [
        { key: 'name', label: '节点名称', type: 'text', required: true, placeholder: '例如：香港 01' },
        { key: 'server', label: '服务器地址', type: 'text', required: true, placeholder: 'example.com 或 IP' },
        { key: 'port', label: '端口', type: 'number', required: true, min: 1, max: 65535 },
        { key: 'udp', label: 'UDP 支持', type: 'checkbox', default: true }
    ];

    const fingerprintOptions = [
        { value: '', label: '默认' },
        { value: 'chrome', label: 'Chrome' },
        { value: 'firefox', label: 'Firefox' },
        { value: 'safari', label: 'Safari' },
        { value: 'ios', label: 'iOS' },
        { value: 'android', label: 'Android' },
        { value: 'edge', label: 'Edge' },
        { value: '360', label: '360 浏览器' },
        { value: 'qq', label: 'QQ 浏览器' }
    ];

    const transportFields = [
        { key: 'network', label: '传输协议', type: 'select', options: [
            { value: 'tcp', label: 'TCP' },
            { value: 'ws', label: 'WebSocket' },
            { value: 'h2', label: 'HTTP/2' },
            { value: 'grpc', label: 'gRPC' },
            { value: 'http', label: 'HTTP' }
        ]},
        { key: 'ws-path', label: 'WebSocket 路径', type: 'text', placeholder: '例如：/path' },
        { key: 'ws-host', label: 'WebSocket Host', type: 'text', placeholder: '例如：example.com' },
        { key: 'h2-path', label: 'HTTP/2 路径', type: 'text', placeholder: '例如：/path' },
        { key: 'h2-host', label: 'HTTP/2 Host', type: 'text', placeholder: '例如：example.com' },
        { key: 'grpc-service-name', label: 'gRPC 服务名', type: 'text', placeholder: '例如：GunService' }
    ];

    const tlsFields = [
        { key: 'tls', label: 'TLS', type: 'checkbox', default: false },
        { key: 'servername', label: 'Server Name / SNI', type: 'text', placeholder: '例如：example.com' },
        { key: 'skip-cert-verify', label: '跳过证书验证', type: 'checkbox', default: false },
        { key: 'client-fingerprint', label: '客户端指纹', type: 'select', options: fingerprintOptions },
        { key: 'alpn', label: 'ALPN', type: 'text', placeholder: '例如：h2,http/1.1' }
    ];

    const protocolSpecificFields = {
        ss: [
            ...commonFields,
            { key: 'cipher', label: '加密方式', type: 'select', required: true, options: [
                { value: 'aes-128-gcm', label: 'aes-128-gcm' },
                { value: 'aes-256-gcm', label: 'aes-256-gcm' },
                { value: 'chacha20-ietf-poly1305', label: 'chacha20-ietf-poly1305' },
                { value: 'xchacha20-ietf-poly1305', label: 'xchacha20-ietf-poly1305' },
                { value: '2022-blake3-aes-128-gcm', label: '2022-blake3-aes-128-gcm' },
                { value: '2022-blake3-aes-256-gcm', label: '2022-blake3-aes-256-gcm' },
                { value: '2022-blake3-chacha20-poly1305', label: '2022-blake3-chacha20-poly1305' }
            ]},
            { key: 'password', label: '密码', type: 'text', required: true },
            { key: 'plugin', label: '插件', type: 'select', options: [
                { value: '', label: '无插件' },
                { value: 'obfs', label: 'simple-obfs' },
                { value: 'v2ray-plugin', label: 'v2ray-plugin' },
                { value: 'shadow-tls', label: 'shadow-tls' },
                { value: 'restls', label: 'restls' }
            ]},
            { key: 'plugin-opts-mode', label: '插件模式', type: 'text', placeholder: '例如：tls 或 http' },
            { key: 'plugin-opts-host', label: '插件 Host', type: 'text', placeholder: '例如：cloudflare.com' }
        ],
        ssr: [
            ...commonFields,
            { key: 'cipher', label: '加密方式', type: 'text', required: true, placeholder: '例如：aes-256-cfb' },
            { key: 'password', label: '密码', type: 'text', required: true },
            { key: 'protocol', label: '协议', type: 'text', required: true, placeholder: '例如：origin' },
            { key: 'obfs', label: '混淆', type: 'text', required: true, placeholder: '例如：plain' },
            { key: 'protocol-param', label: '协议参数', type: 'text', placeholder: '可选' },
            { key: 'obfs-param', label: '混淆参数', type: 'text', placeholder: '可选' }
        ],
        vmess: [
            ...commonFields,
            { key: 'uuid', label: 'UUID', type: 'text', required: true },
            { key: 'alterId', label: 'Alter ID', type: 'number', default: 0, min: 0 },
            { key: 'cipher', label: '加密方式', type: 'select', options: [
                { value: 'auto', label: 'auto' },
                { value: 'aes-128-gcm', label: 'aes-128-gcm' },
                { value: 'chacha20-poly1305', label: 'chacha20-poly1305' },
                { value: 'none', label: 'none' },
                { value: 'zero', label: 'zero' }
            ]},
            ...transportFields,
            ...tlsFields
        ],
        vless: [
            ...commonFields,
            { key: 'uuid', label: 'UUID', type: 'text', required: true },
            { key: 'encryption', label: '加密方式', type: 'text', placeholder: 'none' },
            { key: 'flow', label: '流控', type: 'select', options: [
                { value: '', label: '无' },
                { value: 'xtls-rprx-vision', label: 'xtls-rprx-vision' },
                { value: 'xtls-rprx-vision-udp443', label: 'xtls-rprx-vision-udp443' }
            ]},
            ...transportFields,
            ...tlsFields,
            { key: 'reality-public-key', label: 'Reality Public Key', type: 'text' },
            { key: 'reality-short-id', label: 'Reality Short ID', type: 'text' }
        ],
        trojan: [
            ...commonFields,
            { key: 'password', label: '密码', type: 'text', required: true },
            ...transportFields,
            ...tlsFields
        ],
        hysteria2: [
            ...commonFields,
            { key: 'password', label: '密码/认证', type: 'text', required: true },
            { key: 'sni', label: 'SNI', type: 'text' },
            { key: 'skip-cert-verify', label: '跳过证书验证', type: 'checkbox', default: false },
            { key: 'fingerprint', label: '证书指纹', type: 'text', placeholder: '可选' },
            { key: 'obfs', label: '混淆类型', type: 'select', options: [
                { value: '', label: '无' },
                { value: 'salamander', label: 'salamander' }
            ]},
            { key: 'obfs-password', label: '混淆密码', type: 'text' },
            { key: 'up', label: '上传速度 Mbps', type: 'text' },
            { key: 'down', label: '下载速度 Mbps', type: 'text' }
        ],
        anytls: [
            ...commonFields,
            { key: 'password', label: '密码/认证', type: 'text', required: true },
            ...tlsFields,
            { key: 'idle-session-check-interval', label: '空闲会话检查间隔', type: 'number', default: 30, min: 1 },
            { key: 'idle-session-timeout', label: '空闲会话超时', type: 'number', default: 30, min: 1 },
            { key: 'min-idle-session', label: '最小空闲会话数', type: 'number', default: 0, min: 0 }
        ],
        socks5: [
            ...commonFields,
            { key: 'username', label: '用户名', type: 'text', placeholder: '可选' },
            { key: 'password', label: '密码', type: 'text', placeholder: '可选' },
            { key: 'tls', label: 'TLS', type: 'checkbox', default: false },
            { key: 'skip-cert-verify', label: '跳过证书验证', type: 'checkbox', default: false }
        ],
        http: [
            ...commonFields,
            { key: 'username', label: '用户名', type: 'text', placeholder: '可选' },
            { key: 'password', label: '密码', type: 'text', placeholder: '可选' },
            { key: 'tls', label: 'TLS/HTTPS', type: 'checkbox', default: false },
            { key: 'skip-cert-verify', label: '跳过证书验证', type: 'checkbox', default: false },
            { key: 'sni', label: 'SNI', type: 'text' }
        ]
    };

    return protocolSpecificFields[protocol] || commonFields;
}
// ============ 工具函数 ============

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// 点击模态框外部关闭
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
    }
}

// ============ 链式代理管理 ============

async function loadRelayNodes() {
    try {
        const response = await fetch('/api/nodes');
        const nodes = await response.json();
        
        // 筛选出链式节点：旧的 relay 协议或新的 dialer-proxy 方式
        const relayNodes = nodes.filter(n => n.protocol === 'relay' || n.dialer_proxy);
        
        const tbody = document.querySelector('#relay-nodes-table tbody');
        tbody.innerHTML = '';
        
        if (relayNodes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #999;">暂无链式节点，点击右上角按钮创建</td></tr>';
            return;
        }
        
        const nodeDetailsPromises = relayNodes.map(node =>
            fetch(`/api/nodes/${node.id}/detail`)
                .then(res => res.json())
                .catch(error => {
                    console.error('获取节点配置失败:', error);
                    return { config: {} };
                })
        );
        
        const nodeDetails = await Promise.all(nodeDetailsPromises);
        
        relayNodes.forEach((node, index) => {
            const config = nodeDetails[index].config || {};
            // 显示链式路径：旧方式（proxies 数组，新方式（dialer-proxy）
            let proxyChain = '-';
            if (config.proxies && Array.isArray(config.proxies)) {
                proxyChain = config.proxies.join(' → ');
            } else if (config['dialer-proxy']) {
                proxyChain = `${config['dialer-proxy']} → ${node.name}`;
            }
            
            // 显示所有关联的用户
            const userBadges = node.user_names && node.user_names.length > 0
                ? node.user_names.map(name => `<span class="badge badge-success" style="margin-right: 4px;">${name}</span>`).join('')
                : '<span class="badge badge-secondary">未分配</span>';
            
            // 订阅名称显示为badge
            const subscriptionBadge = node.subscription_name === '手动添加'
                ? '<span class="badge badge-secondary">手动添加</span>'
                : `<span class="badge badge-primary">${node.subscription_name}</span>`;
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${node.name}</strong></td>
                <td><code style="font-size: 12px;">${proxyChain}</code></td>
                <td>${subscriptionBadge}</td>
                <td>${userBadges}</td>
                <td class="action-buttons">
                    <button class="btn btn-primary btn-small" onclick="renameNode(${node.id}, '${node.name.replace(/'/g, "\\'")}')">📝 重命名</button>
                    <button class="btn btn-danger btn-small" onclick="deleteRelayNode(${node.id})">删除</button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('加载链式节点失败:', error);
    }
}

function showCreateRelayModal() {
    // 填充订阅选择下拉框
    const select = document.getElementById('relayNodeSubscription');
    select.innerHTML = '<option value="">不归属任何分组</option>';
    allSubscriptions.forEach(sub => {
        const option = document.createElement('option');
        option.value = sub.id;
        option.textContent = sub.name;
        select.appendChild(option);
    });
    
    // 清空命名模板
    document.getElementById('relayNodeNameTemplate').value = '';
    
    // 重置 UDP 选项（默认不启用）
    document.getElementById('relayEnableUdp').checked = false;
    
    // 渲染前置和后置节点列表
    renderRelayNodeSelections();
    
    document.getElementById('createRelayModal').style.display = 'block';
}

function renderRelayNodeSelections() {
    // 筛选出可用节点：非 relay 协议且没有 dialer-proxy 的节点
    const availableNodes = allNodes.filter(node => node.protocol !== 'relay' && !node.dialer_proxy);
    
    // 渲染前置节点
    const frontContainer = document.getElementById('relayFrontNodes');
    frontContainer.innerHTML = '';
    
    availableNodes.forEach(node => {
        const div = document.createElement('div');
        div.className = 'node-item';
        div.style.marginBottom = '8px';
        div.style.cursor = 'pointer';
        div.innerHTML = `
            <input type="checkbox" class="relay-front-checkbox" value="${node.id}" onchange="updateRelayCount()" style="margin-right: 8px;">
            <div class="node-item-info" style="flex: 1;">
                <div class="node-item-name">${node.name}</div>
                <div class="node-item-meta">${node.protocol.toUpperCase()}  • ${node.subscription_name}</div>
            </div>
        `;
        
        div.onclick = function(e) {
            if (e.target.type !== 'checkbox') {
                const checkbox = div.querySelector('input');
                checkbox.checked = !checkbox.checked;
                updateRelayCount();
            }
        };
        
        frontContainer.appendChild(div);
    });
    
    // 渲染后置节点
    const backContainer = document.getElementById('relayBackNodes');
    backContainer.innerHTML = '';
    
    availableNodes.forEach(node => {
        const div = document.createElement('div');
        div.className = 'node-item';
        div.style.marginBottom = '8px';
        div.style.cursor = 'pointer';
        div.innerHTML = `
            <input type="checkbox" class="relay-back-checkbox" value="${node.id}" onchange="updateRelayCount()" style="margin-right: 8px;">
            <div class="node-item-info" style="flex: 1;">
                <div class="node-item-name">${node.name}</div>
                <div class="node-item-meta">${node.protocol.toUpperCase()}  • ${node.subscription_name}</div>
            </div>
        `;
        
        div.onclick = function(e) {
            if (e.target.type !== 'checkbox') {
                const checkbox = div.querySelector('input');
                checkbox.checked = !checkbox.checked;
                updateRelayCount();
            }
        };
        
        backContainer.appendChild(div);
    });
    
    updateRelayCount();
}

function toggleAllFrontNodes() {
    const checkboxes = document.querySelectorAll('.relay-front-checkbox');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    
    checkboxes.forEach(cb => {
        cb.checked = !allChecked;
    });
    
    updateRelayCount();
}

function toggleAllBackNodes() {
    const checkboxes = document.querySelectorAll('.relay-back-checkbox');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    
    checkboxes.forEach(cb => {
        cb.checked = !allChecked;
    });
    
    updateRelayCount();
}

function updateRelayCount() {
    const frontChecked = document.querySelectorAll('.relay-front-checkbox:checked');
    const backChecked = document.querySelectorAll('.relay-back-checkbox:checked');
    
    const frontCount = frontChecked.length;
    const backCount = backChecked.length;
    const totalCount = frontCount * backCount;
    
    document.getElementById('frontNodeCount').textContent = frontCount;
    document.getElementById('backNodeCount').textContent = backCount;
    document.getElementById('relayGenerateCount').textContent = totalCount;
}

async function batchCreateRelayNodes() {
    const nameTemplate = document.getElementById('relayNodeNameTemplate').value.trim();
    const subscription_id = document.getElementById('relayNodeSubscription').value || null;
    const enableUdp = document.getElementById('relayEnableUdp').checked;
    
    // 获取选中的前置和后置节点
    const frontCheckboxes = document.querySelectorAll('.relay-front-checkbox:checked');
    const backCheckboxes = document.querySelectorAll('.relay-back-checkbox:checked');
    
    const frontNodeIds = Array.from(frontCheckboxes).map(cb => parseInt(cb.value));
    const backNodeIds = Array.from(backCheckboxes).map(cb => parseInt(cb.value));
    
    // 验证
    if (frontNodeIds.length === 0) {
        alert('请至少选择一个前置节点');
        return;
    }
    
    if (backNodeIds.length === 0) {
        alert('请至少选择一个后置节点');
        return;
    }
    
    // 获取节点信息（需要完整配置）
    const frontNodes = frontNodeIds.map(id => allNodes.find(n => n.id === id)).filter(n => n);
    const backNodes = backNodeIds.map(id => allNodes.find(n => n.id === id)).filter(n => n);
    
    const totalCount = frontNodes.length * backNodes.length;
    
    if (!confirm(`确定要生成 ${totalCount} 个链式节点吗？\n\n组合方式：\n${frontNodes.length} 个前置节点 × ${backNodes.length} 个后置节点 = ${totalCount} 个链式节点\nUDP支持：${enableUdp ? '已启用' : '已禁用'}\n\n注意：将使用 dialer-proxy 方式创建`)) {
        return;
    }
    
    // 生成所有组合 - 使用 dialer-proxy 方式
    const dialerProxyConfigs = [];
    for (const frontNode of frontNodes) {
        for (const backNode of backNodes) {
            // 生成节点名称
            let nodeName;
            if (nameTemplate) {
                nodeName = nameTemplate
                    .replace(/\[前置\]/g, frontNode.name)
                    .replace(/\[后置\]/g, backNode.name);
            } else {
                nodeName = `${frontNode.name}-${backNode.name}`;
            }
            
            // 构建 dialer-proxy 配置：复制后置节点配置，添加 dialer-proxy 指向前置节点
            const dialerConfig = {
                name: nodeName,
                backNodeId: backNode.id,
                frontNodeName: frontNode.name,
                enableUdp: enableUdp
            };
            
            dialerProxyConfigs.push(dialerConfig);
        }
    }
    
    try {
        // 调用批量创建API - 使用新的 dialer-proxy 方式
        const response = await fetch('/api/nodes/batch-dialer-proxy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                configs: dialerProxyConfigs,
                subscription_id: subscription_id
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ 成功创建 ${data.count} 个链式节点（dialer-proxy 方式）！`);
            closeModal('createRelayModal');
            loadRelayNodes();
            loadNodes();
            loadSubscriptions();
            loadUsers();
            loadStats();
        } else {
            alert('❌ 创建失败: ' + data.message);
        }
    } catch (error) {
        alert('❌ 创建失败: ' + error.message);
    }
}

async function deleteRelayNode(id) {
    if (!confirm('确定要删除此链式节点吗？')) return;
    
    try {
        const response = await fetch(`/api/nodes/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadRelayNodes();
            loadNodes(); // 刷新所有节点列表
            loadSubscriptions(); // 刷新订阅列表以更新节点数
            loadUsers(); // 刷新用户列表以更新节点数
            loadStats();
        } else {
            alert('删除失败');
        }
    } catch (error) {
        alert('删除失败: ' + error.message);
    }
}

// ============ 节点排序功能 ============

function editNodeOrder(nodeId, currentOrder) {
    const newOrder = prompt('请输入新的排序数字（数字越小越靠前）:', currentOrder);
    if (newOrder === null || newOrder === '') return;
    
    const orderNum = parseInt(newOrder);
    if (isNaN(orderNum) || orderNum < 0) {
        alert('请输入有效的数字（大于等于 0）');
        return;
    }
    
    updateNodeOrder(nodeId, orderNum);
}

async function updateNodeOrder(nodeId, order) {
    try {
        const response = await fetch(`/api/nodes/${nodeId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order: parseInt(order) })
        });
        
        if (response.ok) {
            // 刷新节点列表以显示新的排序
            loadNodes();
        } else {
            alert('更新排序失败');
        }
    } catch (error) {
        alert('更新排序失败: ' + error.message);
    }
}
