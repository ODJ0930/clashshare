(() => {
    'use strict';

    if (!window.lucide) return;

    const emojiIcons = new Map([
        ['🚀', 'Network'], ['📊', 'ChartNoAxesCombined'], ['🌐', 'Globe'],
        ['📡', 'Radio'], ['👥', 'Users'], ['📝', 'FilePenLine'],
        ['🔗', 'Link'], ['🔌', 'Plug'], ['⚙️', 'Settings'], ['👤', 'UserRound'],
        ['➕', 'Plus'], ['🗑️', 'Trash2'], ['📥', 'Download'], ['📤', 'Upload'],
        ['✏️', 'Pencil'], ['📌', 'ListTree'], ['💡', 'Info'],
        ['🔐', 'LockKeyhole'], ['⚠️', 'TriangleAlert'], ['🎲', 'Shuffle'], ['📋', 'Copy']
    ]);
    const commandIcons = new Map([
        ['删除', 'Trash2'], ['编辑', 'Pencil'], ['重命名', 'TextCursorInput'],
        ['导出', 'Upload'], ['复制', 'Copy'], ['刷新', 'RefreshCw'],
        ['退出登录', 'LogOut'], ['管理节点', 'ListTree'], ['新增后端', 'Plus'],
        ['新建入站节点', 'Plus']
    ]);
    const compactCommands = new Set(['删除', '编辑', '重命名', '导出', '复制']);
    const selector = '.nav-item .icon, .stat-icon, .admin-name, h1, h2, h3, .btn, .copy-btn';

    function icon(name) {
        const definition = lucide.icons[name];
        if (!definition) return null;
        const glyph = lucide.createElement(definition);
        Object.entries({
            class: 'ui-icon', width: 18, height: 18, 'stroke-width': 1.75,
            'aria-hidden': 'true', focusable: 'false'
        }).forEach(([key, value]) => glyph.setAttribute(key, value));
        return glyph;
    }

    function hideMarker(element, marker) {
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            const start = node.textContent.indexOf(marker);
            if (start === -1) continue;
            const markerNode = node.splitText(start);
            markerNode.splitText(marker.length);
            const hidden = document.createElement('span');
            hidden.className = 'legacy-icon';
            markerNode.replaceWith(hidden);
            hidden.append(markerNode);
            break;
        }
    }

    function decorate(element) {
        if (element.querySelector('.ui-icon')) return;
        const text = element.textContent;
        const prefix = [...emojiIcons.keys()].find(emoji => text.trimStart().startsWith(emoji));
        const label = (prefix ? text.replace(prefix, '') : text).trim();
        const isButton = element.matches('.btn, .copy-btn');
        const name = (isButton && commandIcons.get(label)) || emojiIcons.get(prefix);
        const glyph = icon(name);
        if (!glyph) return;

        // Keep original text and event-bearing elements intact; only presentation changes.
        if (prefix) hideMarker(element, prefix);

        if (isButton && compactCommands.has(label) && element.closest('table, .subscription-link-row')) {
            const hiddenLabel = document.createElement('span');
            hiddenLabel.className = 'visually-hidden';
            hiddenLabel.append(...element.childNodes);
            element.append(hiddenLabel);
            element.classList.add('icon-action');
        }
        if (isButton) {
            element.title = element.title || label;
            element.setAttribute('aria-label', label);
        }
        element.prepend(glyph);
    }

    function decorateTree(root) {
        if (root.nodeType !== Node.ELEMENT_NODE) return;
        if (root.matches(selector)) decorate(root);
        root.querySelectorAll(selector).forEach(decorate);
        if (root.matches('tr') && root.closest('table.record-grid')) decorateCard(root);
        root.querySelectorAll('table.record-grid > tbody > tr').forEach(decorateCard);
    }

    function decorateCard(row) {
        if (row.classList.contains('user-node-detail-row') || row.querySelector('td[colspan]')) return;
        const table = row.closest('table');
        const headers = [...table.querySelectorAll('thead th')];
        const titleIndex = ['nodes-table', 'users-table'].includes(table.id) ? 1 : 0;
        row.classList.add('record-card');
        [...row.cells].forEach((cell, index) => {
            const label = headers[index]?.textContent.trim();
            if (label && index !== titleIndex && !cell.classList.contains('action-buttons')) {
                cell.dataset.label = label;
            }
            if (index !== titleIndex) return;
            cell.classList.add('record-title');
            if (cell.querySelector('.record-icon')) return;
            if (['nodes-table', 'relay-nodes-table'].includes(table.id)) {
                const name = cell.querySelector('strong')?.textContent || '';
                const originalName = cell.querySelector('small')?.textContent.replace(/^\s*原\s*[:：]\s*/, '') || '';
                const country = window.ClashShareCountries?.inferCountry(name) || window.ClashShareCountries?.inferCountry(originalName);
                if (country) {
                    const flag = document.createElement('span');
                    flag.className = 'record-icon node-flag';
                    flag.title = `${country.name}（根据节点名称识别）`;
                    flag.setAttribute('role', 'img');
                    flag.setAttribute('aria-label', flag.title);
                    const image = document.createElement('img');
                    image.src = `/static/img/flags/${country.code}.svg`;
                    image.alt = '';
                    image.width = 24;
                    image.height = 18;
                    flag.append(image);
                    cell.prepend(flag);
                    const marker = name.match(/[\u{1F1E6}-\u{1F1FF}]{2}/u);
                    if (marker) hideMarker(cell.querySelector('strong'), marker[0]);
                    return;
                }
            }
            const glyph = icon({
                'nodes-table': 'Globe', 'subscriptions-table': 'FolderClosed',
                'users-table': 'UserRound', 'templates-table': 'FileCode2',
                'relay-nodes-table': 'Waypoints'
            }[table.id]);
            if (glyph) {
                glyph.classList.add('record-icon');
                cell.prepend(glyph);
            }
        });
    }

    lucide.createIcons({ attrs: { class: 'ui-icon', 'stroke-width': 1.75 } });
    decorateTree(document.body);
    const observer = new MutationObserver(records => {
        const roots = new Set();
        records.forEach(record => {
            if (record.target.nodeType === Node.ELEMENT_NODE && record.target.matches(selector)) {
                roots.add(record.target);
            }
            record.addedNodes.forEach(node => {
                if (node.nodeType === Node.ELEMENT_NODE && !node.matches('.ui-icon, .legacy-icon, .visually-hidden')) {
                    roots.add(node);
                }
            });
        });
        roots.forEach(decorateTree);
    });
    observer.observe(document.body, { childList: true, subtree: true });
})();
