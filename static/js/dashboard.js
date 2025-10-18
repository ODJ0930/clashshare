// 全局变量
let currentUserId = null;
let currentEditUserId = null;
let currentSubscriptionId = null;
let currentEditTemplateId = null;
let currentEditNodeId = null;
let currentEditNodeProtocol = null; // 当前编辑节点的协议类型
let allNodes = [];
let allSubscriptions = [];
let allTemplates = [];
let selectedRelayNodes = []; // 选中的链式节点列表

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', () => {
    initTabNavigation();
    loadStats();
    loadSubscriptions();
    loadNodes();
    loadUsers();
    loadTemplates();
    loadAdminProfile();
    loadRelayNodes();
});

// 标签页导航
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
    if (!confirm('确定要删除此订阅及其所有节点吗？此操作不可恢复！')) return;
    
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
                <div class="node-item-meta">${node.protocol.toUpperCase()} • ${node.subscription_name}</div>
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
                    ${node.name !== node.original_name ? `<br><small style="color: #999;">原: ${node.original_name}</small>` : ''}
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

async function renameNode(id, currentName) {
    const newName = prompt('输入新名称:', currentName);
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
    
    if (!confirm(`确定要删除选中的 ${nodeIds.length} 个节点吗？此操作不可恢复！`)) {
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

async function loadUsers() {
    try {
        const response = await fetch('/api/users');
        const users = await response.json();
        
        const tbody = document.querySelector('#users-table tbody');
        tbody.innerHTML = '';
        
        users.forEach(user => {
            // 优先使用自定义后缀，否则使用系统token
            const token = user.custom_slug || user.subscription_token;
            const subUrl = `${window.location.origin}/sub/user/${token}`;
            const isCustom = user.custom_slug ? '🔗' : '';
            const templateName = user.template_name || '默认';
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${user.username}</strong></td>
                <td>${user.remark || '-'}</td>
                <td><span class="badge badge-info">${templateName}</span></td>
                <td><span class="badge badge-primary">${user.subscription_count} 个</span></td>
                <td><span class="badge badge-info">${user.node_count} 个</span></td>
                <td>
                    <span class="badge ${user.enabled ? 'badge-success' : 'badge-danger'}">
                        ${user.enabled ? '启用' : '禁用'}
                    </span>
                </td>
                <td>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <code class="url-display" style="flex: 1;" title="${user.custom_slug ? '自定义链接' : '系统生成链接'}">${isCustom}${truncateUrl(subUrl, 40)}</code>
                        <button class="copy-btn" onclick="copyToClipboard('${subUrl}')">📋 复制</button>
                    </div>
                </td>
                <td class="action-buttons">
                    <button class="btn btn-primary btn-small" onclick="showAssignSubscriptionsModal(${user.id}, '${user.username}')">📌 管理订阅</button>
                    <button class="btn btn-secondary btn-small" onclick="showEditUserModal(${user.id})">✏️ 编辑</button>
                    <button class="btn btn-secondary btn-small" onclick="toggleUserStatus(${user.id}, ${!user.enabled})">${user.enabled ? '禁用' : '启用'}</button>
                    <button class="btn btn-danger btn-small" onclick="deleteUser(${user.id})">删除</button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('加载用户失败:', error);
    }
}

function showAddUserModal() {
    document.getElementById('addUserModal').style.display = 'block';
    document.getElementById('userName').value = '';
    document.getElementById('userRemark').value = '';
}

async function addUser() {
    const username = document.getElementById('userName').value.trim();
    const remark = document.getElementById('userRemark').value.trim();
    
    if (!username) {
        alert('请填写名称');
        return;
    }
    
    try {
        const response = await fetch('/api/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, remark })
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
        const updateData = { username, remark, custom_slug: customSlug || null };
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

// ============ 管理员设置 ============

async function loadAdminProfile() {
    try {
        const response = await fetch('/api/admin/profile');
        const data = await response.json();
        
        document.getElementById('current-username').textContent = data.username;
        document.getElementById('account-created').textContent = data.created_at;
    } catch (error) {
        console.error('加载管理员信息失败:', error);
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
        alert('新密码至少需要6位字符');
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
        alert('用户名至少需要3位字符');
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
            // 处理非200状态码
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
        
        // 如果没有填写名称，使用文件名（去掉扩展名）
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
        
        // 为 UUID 字段添加生成按钮
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
        { key: 'server', label: '服务器地址', type: 'text', required: true, placeholder: '例如: example.com 或 1.2.3.4' },
        { key: 'port', label: '端口', type: 'number', required: true, min: 1, max: 65535, placeholder: '例如: 443' }
    ];
    
    const protocolSpecificFields = {
        'ss': [
            ...commonFields,
            { key: 'cipher', label: '加密方式', type: 'select', required: true, options: [
                { value: 'aes-128-gcm', label: 'aes-128-gcm (推荐)' },
                { value: 'aes-256-gcm', label: 'aes-256-gcm (推荐)' },
                { value: 'chacha20-ietf-poly1305', label: 'chacha20-ietf-poly1305 (推荐)' },
                { value: 'aes-128-cfb', label: 'aes-128-cfb' },
                { value: 'aes-192-cfb', label: 'aes-192-cfb' },
                { value: 'aes-256-cfb', label: 'aes-256-cfb' },
                { value: 'aes-128-ctr', label: 'aes-128-ctr' },
                { value: 'aes-192-ctr', label: 'aes-192-ctr' },
                { value: 'aes-256-ctr', label: 'aes-256-ctr' },
                { value: 'rc4-md5', label: 'rc4-md5 (不推荐)' },
                { value: 'chacha20', label: 'chacha20' },
                { value: 'chacha20-ietf', label: 'chacha20-ietf' },
                { value: 'xchacha20-ietf-poly1305', label: 'xchacha20-ietf-poly1305' },
                { value: '2022-blake3-aes-128-gcm', label: '2022-blake3-aes-128-gcm (SS2022)' },
                { value: '2022-blake3-aes-256-gcm', label: '2022-blake3-aes-256-gcm (SS2022)' },
                { value: '2022-blake3-chacha20-poly1305', label: '2022-blake3-chacha20-poly1305 (SS2022)' }
            ]},
            { key: 'password', label: '密码', type: 'text', required: true },
            { key: 'udp', label: 'UDP支持', type: 'checkbox', default: true },
            { key: 'plugin', label: '插件', type: 'select', options: [
                { value: '', label: '无插件' },
                { value: 'obfs', label: 'simple-obfs' },
                { value: 'v2ray-plugin', label: 'v2ray-plugin' },
                { value: 'shadow-tls', label: 'shadow-tls' },
                { value: 'restls', label: 'restls' }
            ]},
            { key: 'plugin-opts-mode', label: '插件模式', type: 'text', placeholder: '例如: tls 或 http', description: '仅在使用插件时需要' },
            { key: 'plugin-opts-host', label: '插件Host', type: 'text', placeholder: '例如: cloudflare.com', description: '仅在使用插件时需要' }
        ],
        'ssr': [
            ...commonFields,
            { key: 'cipher', label: '加密方式', type: 'select', required: true, options: [
                { value: 'aes-256-cfb', label: 'aes-256-cfb' },
                { value: 'aes-128-cfb', label: 'aes-128-cfb' },
                { value: 'chacha20', label: 'chacha20' },
                { value: 'chacha20-ietf', label: 'chacha20-ietf' },
                { value: 'rc4-md5', label: 'rc4-md5' }
            ]},
            { key: 'password', label: '密码', type: 'text', required: true },
            { key: 'protocol', label: '协议', type: 'select', required: true, options: [
                { value: 'origin', label: 'origin' },
                { value: 'auth_sha1_v4', label: 'auth_sha1_v4' },
                { value: 'auth_aes128_md5', label: 'auth_aes128_md5' },
                { value: 'auth_aes128_sha1', label: 'auth_aes128_sha1' },
                { value: 'auth_chain_a', label: 'auth_chain_a' },
                { value: 'auth_chain_b', label: 'auth_chain_b' }
            ]},
            { key: 'obfs', label: '混淆', type: 'select', required: true, options: [
                { value: 'plain', label: 'plain' },
                { value: 'http_simple', label: 'http_simple' },
                { value: 'http_post', label: 'http_post' },
                { value: 'tls1.2_ticket_auth', label: 'tls1.2_ticket_auth' }
            ]},
            { key: 'protocol-param', label: '协议参数', type: 'text', placeholder: '可选' },
            { key: 'obfs-param', label: '混淆参数', type: 'text', placeholder: '可选' }
        ],
        'vmess': [
            ...commonFields,
            { key: 'uuid', label: 'UUID', type: 'text', required: true, placeholder: '例如: 12345678-1234-1234-1234-123456789012' },
            { key: 'alterId', label: 'Alter ID', type: 'number', default: 0, min: 0, max: 65535, description: '推荐使用 0' },
            { key: 'cipher', label: '加密方式', type: 'select', options: [
                { value: 'auto', label: 'auto (推荐)' },
                { value: 'aes-128-gcm', label: 'aes-128-gcm' },
                { value: 'chacha20-poly1305', label: 'chacha20-poly1305' },
                { value: 'aes-128-cfb', label: 'aes-128-cfb' },
                { value: 'aes-256-cfb', label: 'aes-256-cfb' },
                { value: 'aes-256-gcm', label: 'aes-256-gcm' },
                { value: 'none', label: 'none (明文)' },
                { value: 'zero', label: 'zero' }
            ]},
            { key: 'network', label: '传输协议', type: 'select', options: [
                { value: 'tcp', label: 'TCP' },
                { value: 'ws', label: 'WebSocket' },
                { value: 'h2', label: 'HTTP/2' },
                { value: 'grpc', label: 'gRPC' },
                { value: 'http', label: 'HTTP' }
            ]},
            { key: 'tls', label: 'TLS', type: 'checkbox', default: false },
            { key: 'servername', label: 'TLS Server Name', type: 'text', placeholder: '例如: example.com', description: '仅TLS时使用' },
            { key: 'skip-cert-verify', label: '跳过证书验证', type: 'checkbox', default: false },
            { key: 'ws-path', label: 'WebSocket路径', type: 'text', placeholder: '例如: /path', description: '仅WebSocket时使用' },
            { key: 'ws-host', label: 'WebSocket Host', type: 'text', placeholder: '例如: example.com', description: '仅WebSocket时使用' },
            { key: 'h2-path', label: 'HTTP/2路径', type: 'text', placeholder: '例如: /path', description: '仅HTTP/2时使用' },
            { key: 'h2-host', label: 'HTTP/2 Host', type: 'text', placeholder: '例如: example.com', description: '仅HTTP/2时使用' },
            { key: 'grpc-service-name', label: 'gRPC服务名', type: 'text', placeholder: '例如: GunService', description: '仅gRPC时使用' }
        ],
        'vless': [
            ...commonFields,
            { key: 'uuid', label: 'UUID', type: 'text', required: true, placeholder: '例如: 12345678-1234-1234-1234-123456789012' },
            { key: 'flow', label: '流控', type: 'select', options: [
                { value: '', label: '无' },
                { value: 'xtls-rprx-vision', label: 'xtls-rprx-vision' },
                { value: 'xtls-rprx-vision-udp443', label: 'xtls-rprx-vision-udp443' }
            ], description: 'Reality 或 XTLS 时使用' },
            { key: 'network', label: '传输协议', type: 'select', options: [
                { value: 'tcp', label: 'TCP' },
                { value: 'ws', label: 'WebSocket' },
                { value: 'grpc', label: 'gRPC' },
                { value: 'http', label: 'HTTP' }
            ]},
            { key: 'tls', label: 'TLS/Reality', type: 'checkbox', default: false },
            { key: 'servername', label: 'Server Name', type: 'text', placeholder: '例如: example.com', description: 'TLS/Reality SNI' },
            { key: 'skip-cert-verify', label: '跳过证书验证', type: 'checkbox', default: false },
            { key: 'client-fingerprint', label: '客户端指纹', type: 'select', options: [
                { value: '', label: '默认' },
                { value: 'chrome', label: 'Chrome' },
                { value: 'firefox', label: 'Firefox' },
                { value: 'safari', label: 'Safari' },
                { value: 'ios', label: 'iOS' },
                { value: 'android', label: 'Android' },
                { value: 'edge', label: 'Edge' },
                { value: '360', label: '360浏览器' },
                { value: 'qq', label: 'QQ浏览器' }
            ]},
            { key: 'reality-public-key', label: 'Reality Public Key', type: 'text', description: '仅Reality时使用' },
            { key: 'reality-short-id', label: 'Reality Short ID', type: 'text', description: '仅Reality时使用' },
            { key: 'ws-path', label: 'WebSocket路径', type: 'text', placeholder: '例如: /path' },
            { key: 'ws-host', label: 'WebSocket Host', type: 'text', placeholder: '例如: example.com' },
            { key: 'grpc-service-name', label: 'gRPC服务名', type: 'text', placeholder: '例如: GunService' }
        ],
        'trojan': [
            ...commonFields,
            { key: 'password', label: '密码', type: 'text', required: true },
            { key: 'network', label: '传输协议', type: 'select', options: [
                { value: 'tcp', label: 'TCP' },
                { value: 'ws', label: 'WebSocket' },
                { value: 'grpc', label: 'gRPC' }
            ]},
            { key: 'sni', label: 'SNI', type: 'text', placeholder: '例如: example.com', description: 'TLS服务器名称' },
            { key: 'skip-cert-verify', label: '跳过证书验证', type: 'checkbox', default: false },
            { key: 'udp', label: 'UDP支持', type: 'checkbox', default: true },
            { key: 'client-fingerprint', label: '客户端指纹', type: 'select', options: [
                { value: '', label: '默认' },
                { value: 'chrome', label: 'Chrome' },
                { value: 'firefox', label: 'Firefox' },
                { value: 'safari', label: 'Safari' },
                { value: 'ios', label: 'iOS' },
                { value: 'android', label: 'Android' }
            ]},
            { key: 'alpn', label: 'ALPN', type: 'text', placeholder: '例如: h2,http/1.1', description: '用逗号分隔多个值' },
            { key: 'ws-path', label: 'WebSocket路径', type: 'text', placeholder: '例如: /path' },
            { key: 'ws-host', label: 'WebSocket Host', type: 'text' },
            { key: 'grpc-service-name', label: 'gRPC服务名', type: 'text' },
            { key: 'reality-public-key', label: 'Reality Public Key', type: 'text', description: '仅Reality时使用' },
            { key: 'reality-short-id', label: 'Reality Short ID', type: 'text', description: '仅Reality时使用' }
        ],
        'hysteria2': [
            ...commonFields,
            { key: 'password', label: '密码/认证', type: 'text', required: true },
            { key: 'sni', label: 'SNI', type: 'text', placeholder: '例如: example.com' },
            { key: 'skip-cert-verify', label: '跳过证书验证', type: 'checkbox', default: false },
            { key: 'fingerprint', label: '证书指纹', type: 'text', description: '可选' },
            { key: 'alpn', label: 'ALPN', type: 'text', placeholder: '例如: h3', description: '推荐: h3' },
            { key: 'obfs', label: '混淆类型', type: 'select', options: [
                { value: '', label: '无' },
                { value: 'salamander', label: 'salamander' }
            ]},
            { key: 'obfs-password', label: '混淆密码', type: 'text', description: '使用混淆时必填' },
            { key: 'up', label: '上传速度', type: 'text', placeholder: '例如: 50', description: 'Mbps, 可选' },
            { key: 'down', label: '下载速度', type: 'text', placeholder: '例如: 100', description: 'Mbps, 可选' }
        ],
        'socks5': [
            ...commonFields,
            { key: 'username', label: '用户名', type: 'text', placeholder: '可选' },
            { key: 'password', label: '密码', type: 'text', placeholder: '可选' },
            { key: 'tls', label: 'TLS', type: 'checkbox', default: false },
            { key: 'skip-cert-verify', label: '跳过证书验证', type: 'checkbox', default: false },
            { key: 'udp', label: 'UDP支持', type: 'checkbox', default: true }
        ],
        'http': [
            ...commonFields,
            { key: 'username', label: '用户名', type: 'text', placeholder: '可选' },
            { key: 'password', label: '密码', type: 'text', placeholder: '可选' },
            { key: 'tls', label: 'TLS/HTTPS', type: 'checkbox', default: false },
            { key: 'skip-cert-verify', label: '跳过证书验证', type: 'checkbox', default: false },
            { key: 'sni', label: 'SNI', type: 'text', placeholder: 'TLS时使用' }
        ]
    };
    
    return protocolSpecificFields[protocol] || commonFields;
}

// ============ 工具函数 ============

// UUID v4 生成器
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
        
        // 筛选出relay类型的节点
        const relayNodes = nodes.filter(n => n.protocol === 'relay');
        
        const tbody = document.querySelector('#relay-nodes-table tbody');
        tbody.innerHTML = '';
        
        if (relayNodes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #999;">暂无链式节点，点击右上角按钮创建</td></tr>';
            return;
        }
        
        // 并发获取所有relay节点的详细配置
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
            const proxyChain = config.proxies ? config.proxies.join(' → ') : '-';
            
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
    
    // 重置UDP选项（默认不启用）
    document.getElementById('relayEnableUdp').checked = false;
    
    // 渲染前置和后置节点列表
    renderRelayNodeSelections();
    
    document.getElementById('createRelayModal').style.display = 'block';
}

function renderRelayNodeSelections() {
    // 筛选出非relay类型的节点
    const availableNodes = allNodes.filter(node => node.protocol !== 'relay');
    
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
                <div class="node-item-meta">${node.protocol.toUpperCase()} • ${node.subscription_name}</div>
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
                <div class="node-item-meta">${node.protocol.toUpperCase()} • ${node.subscription_name}</div>
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
    
    // 获取节点信息
    const frontNodes = frontNodeIds.map(id => allNodes.find(n => n.id === id)).filter(n => n);
    const backNodes = backNodeIds.map(id => allNodes.find(n => n.id === id)).filter(n => n);
    
    const totalCount = frontNodes.length * backNodes.length;
    
    if (!confirm(`确定要生成 ${totalCount} 个链式节点吗？\n\n组合方式：\n${frontNodes.length} 个前置节点 × ${backNodes.length} 个后置节点 = ${totalCount} 个链式节点\nUDP支持：${enableUdp ? '已启用' : '已禁用'}`)) {
        return;
    }
    
    // 生成所有组合
    const relayConfigs = [];
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
            
            // 构建relay配置
            const relayConfig = {
                name: nodeName,
                type: 'relay',
                proxies: [frontNode.name, backNode.name]
            };
            
            // 根据用户选择设置UDP
            if (enableUdp) {
                relayConfig.udp = true;
            } else {
                relayConfig['disable-udp'] = true;
            }
            
            relayConfigs.push(relayConfig);
        }
    }
    
    try {
        // 调用批量创建API
        const response = await fetch('/api/nodes/batch-relay', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                configs: relayConfigs,
                subscription_id: subscription_id
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ 成功创建 ${data.count} 个链式节点！`);
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
        alert('请输入有效的数字（大于等于0）');
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

