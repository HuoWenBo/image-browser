/**
 * 标签管理页逻辑（按图片聚合，原生 JS，前后端分离）。
 * 列表复用 /api/images；标签面板读取 /api/images/{id}；
 * 新增标签：从 /api/tags 推荐下拉选择后先暂存到「已选择」待提交区
 * （可删除、可连续添加多个），最后批量提交 POST /api/image-tags；
 * 删除关联走 DELETE /api/image-tags/{image_id}/{tag_id}。
 *
 * 命名规范：函数小驼峰、变量 snake_case、全局常量全大写加下划线。
 */
(function () {
    'use strict';

    // ==================== 共享模块 ====================
    const { escapeHtml, buildImageUrl } = window.ImageGalleryUtils || {};
    const { buildPaginationHtml } = window.GalleryPagination || {};

    // ==================== 全局常量 ====================
    const IMAGES_API = '/api/images';
    const TAGS_API = '/api/tags';
    const IMAGE_TAGS_API = '/api/image-tags';
    const DEFAULT_PER_PAGE = 10;
    const SUGGEST_LIMIT = 8;
    const SUGGEST_DEBOUNCE_MS = 200;
    const PREVIEW_TAG_LIMIT = 4;

    const TYPE_BADGES = {
        GENERAL: ['通用', 'bg-blue-100 text-blue-700'],
        CHARACTER_NAME: ['角色', 'bg-purple-100 text-purple-700'],
        COPYRIGHT: ['作品', 'bg-green-100 text-green-700'],
    };

    // ==================== 页面状态 ====================
    let state = {
        items: [],
        page: 1,
        per_page: DEFAULT_PER_PAGE,
        total: 0,
        total_pages: 1,
        search: '',
    };

    let panel = {
        id: null,
        data: null,
        pending_tags: [],   // 待提交的标签 [{ tag_id, tag_name, tag_type, score }]
        suggest_timer: null,
    };

    // ==================== DOM 引用 ====================
    let table_body_el = null;
    let empty_row_el = null;
    let pagination_el = null;
    let total_count_el = null;
    let per_page_el = null;
    let search_form_el = null;
    let search_input_el = null;
    let search_clear_el = null;
    let panel_modal_el = null;
    let panel_image_el = null;
    let panel_tags_el = null;
    let suggest_input_el = null;
    let suggest_dropdown_el = null;
    let suggest_clear_el = null;
    let suggest_error_el = null;
    let suggest_score_el = null;
    let pending_box_el = null;
    let pending_count_el = null;
    let pending_list_el = null;
    let pending_submit_el = null;
    let preview_modal_el = null;
    let preview_image_el = null;

    // ==================== 工具函数 ====================

    function typeBadge(type) {
        const entry = TYPE_BADGES[type] || [type, 'bg-gray-100 text-gray-600'];
        return '<span class="inline-flex px-2.5 py-0.5 rounded-full text-xs ' + entry[1] + '">' + entry[0] + '</span>';
    }

    function tagPill(name, type) {
        const entry = TYPE_BADGES[type] || ['', 'bg-gray-100 text-gray-600'];
        return '<span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white border border-gray-200 text-xs text-gray-700">'
            + typeBadge(type)
            + '<span class="max-w-[140px] truncate" title="' + escapeHtml(name) + '">' + escapeHtml(name) + '</span>'
            + '</span>';
    }

    /** 计算图片标签总数（tags + characters + series）。 */
    function countTags(item) {
        return (item.tags ? item.tags.length : 0)
            + (item.characters ? item.characters.length : 0)
            + (item.series ? item.series.length : 0);
    }

    /** 生成图片行：缩略图 + 文件名 + 标签预览（前 4 个 + 剩余计数）。 */
    function rowHtml(item) {
        const thumb = '<img src="' + buildImageUrl(item.filepath) + '" alt="' + escapeHtml(item.filename) + '"'
            + ' data-action="preview" data-filepath="' + escapeHtml(item.filepath) + '"'
            + ' class="w-10 h-12 object-contain bg-gray-100 rounded border border-gray-200 cursor-zoom-in"'
            + ' title="点击放大" onerror="this.style.display=\'none\'">';
        const tags = (item.series || []).map(function (name) { return { name: name, type: 'COPYRIGHT' }; })
            .concat((item.characters || []).map(function (name) { return { name: name, type: 'CHARACTER_NAME' }; }))
            .concat((item.tags || []).map(function (name) { return { name: name, type: 'GENERAL' }; }));
        const preview = tags.slice(0, PREVIEW_TAG_LIMIT).map(function (t) { return tagPill(t.name, t.type); }).join('');
        const rest = tags.length - PREVIEW_TAG_LIMIT;
        const rest_html = rest > 0
            ? '<span class="text-xs text-gray-400 px-2 py-1">+' + rest + '</span>'
            : '';
        return [
            '<tr class="border-b border-gray-100 hover:bg-gray-50">',
            '<td class="px-4 py-3 text-gray-400 text-sm">#', item.id, '</td>',
            '<td class="px-4 py-3">',
            '<div class="flex items-center gap-3">', thumb,
            '<span class="text-sm text-gray-800 max-w-[260px] truncate" title="', escapeHtml(item.filename), '">',
            escapeHtml(item.filename), '</span></div></td>',
            '<td class="px-4 py-3">',
            tags.length
                ? '<div class="flex flex-wrap items-center gap-1.5 max-w-[480px]">' + preview + rest_html + '</div>'
                : '<span class="text-xs text-gray-300">暂无标签</span>',
            '</td>',
            '<td class="px-4 py-3 text-sm text-gray-600">', tags.length, '</td>',
            '<td class="px-4 py-3 whitespace-nowrap">',
            '<button type="button" data-action="manage" data-id="', item.id,
            '" class="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 rounded-lg px-3 py-1.5 text-xs font-medium transition">',
            '<i class="bi bi-tags"></i>管理标签</button>',
            '</td>',
            '</tr>',
        ].join('');
    }

    // ==================== 列表渲染 ====================

    function renderTable() {
        if (state.items.length === 0) {
            table_body_el.innerHTML = '';
            empty_row_el.classList.remove('hidden');
            return;
        }
        empty_row_el.classList.add('hidden');
        table_body_el.innerHTML = state.items.map(rowHtml).join('');
    }

    function renderPagination() {
        pagination_el.innerHTML = buildPaginationHtml(state.page, state.total_pages);
    }

    function renderTotalCount() {
        total_count_el.textContent = '共 ' + state.total + ' 张图片';
    }

    function setData(data) {
        state.items = data.items || [];
        state.total = data.total || 0;
        state.total_pages = data.total_pages || 1;
        if (data.page) {
            state.page = data.page;
        }
    }

    // ==================== 数据请求 ====================

    function buildListUrl(page) {
        const params = new URLSearchParams({
            page: String(page),
            per_page: String(state.per_page),
            lang: 'zh',
        });
        const query = state.search.trim();
        if (query) {
            return IMAGES_API + '/search?' + params.toString() + '&query=' + encodeURIComponent(query);
        }
        return IMAGES_API + '?' + params.toString();
    }

    async function fetchList(page) {
        if (page < 1 || (state.total_pages > 0 && page > state.total_pages)) {
            return;
        }
        state.page = page;
        try {
            const res = await fetch(buildListUrl(page));
            if (!res.ok) {
                throw new Error('网络错误');
            }
            const data = await res.json();
            setData(data);
            if (state.items.length === 0 && state.total > 0 && state.page > state.total_pages) {
                await fetchList(state.total_pages);
                return;
            }
            renderTable();
            renderPagination();
            renderTotalCount();
        } catch (err) {
            console.error('加载失败:', err);
        }
    }

    // ==================== 标签管理面板 ====================

    function scoreClass(score) {
        if (score >= 0.9) {
            return 'text-green-600';
        }
        if (score >= 0.5) {
            return 'text-amber-600';
        }
        return 'text-gray-400';
    }

    function panelTagsHtml(data) {
        const groups = [
            { key: 'CHARACTER_NAME', label: '角色' },
            { key: 'COPYRIGHT', label: '作品' },
            { key: 'GENERAL', label: '通用标签' },
        ];
        return groups.map(function (group) {
            const items = (data.scores && data.scores[group.key]) || [];
            const body = items.length
                ? items.map(function (tag) {
                    return [
                        '<div class="flex items-center justify-between px-4 py-2 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 transition">',
                        '<div class="flex items-center gap-2 min-w-0">', typeBadge(tag.type),
                        '<span class="text-sm text-gray-800 truncate" title="', escapeHtml(tag.name), '">', escapeHtml(tag.content || tag.name),
                        tag.content ? '<span class="text-xs text-gray-400 ml-1.5 truncate">(' + escapeHtml(tag.name) + ')</span>' : '',
                        '</span>',
                        '<span class="text-xs font-mono ' + scoreClass(tag.score) + '">', Number(tag.score).toFixed(3), '</span>',
                        '</div>',
                        '<button type="button" data-action="remove-tag" data-tag-id="', tag.id,
                        '" data-tag-name="', escapeHtml(tag.name),
                        '" class="text-red-400 hover:text-red-600 transition" title="删除标签"><i class="bi bi-trash"></i></button>',
                        '</div>',
                    ].join('');
                }).join('')
                : '<p class="text-xs text-gray-300 px-1 py-1">暂无</p>';
            return [
                '<div class="mb-5">',
                '<h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">',
                group.label, ' <span class="text-gray-300">(' + items.length + ')</span></h4>',
                '<div class="space-y-1.5">', body, '</div>',
                '</div>',
            ].join('');
        }).join('');
    }

    async function openPanel(id) {
        panel.id = id;
        panel.data = null;
        panel.pending_tags = [];
        resetSuggestion();
        panel_modal_el.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        try {
            const res = await fetch(IMAGES_API + '/' + id + '?lang=zh');
            if (!res.ok) {
                throw new Error('加载失败');
            }
            panel.data = await res.json();
            panel_image_el.src = buildImageUrl(panel.data.filepath);
            document.getElementById('panel-filename').textContent = panel.data.filename;
            document.getElementById('panel-id').textContent = '图片 ID: ' + panel.data.id;
            panel_tags_el.innerHTML = panelTagsHtml(panel.data);
        } catch (err) {
            console.error('加载图片详情失败:', err);
            panel_tags_el.innerHTML = '<p class="text-sm text-red-500">加载图片详情失败</p>';
        }
    }

    function closePanel() {
        panel_modal_el.classList.add('hidden');
        document.body.style.overflow = '';
        panel.id = null;
        panel.data = null;
        panel.pending_tags = [];
    }

    async function refreshPanel() {
        if (panel.id === null) {
            return;
        }
        await openPanel(panel.id);
    }

    // ==================== 新增标签（推荐 + 临时待提交） ====================

    function resetSuggestion() {
        panel.pending_tags = [];
        suggest_input_el.value = '';
        suggest_score_el.value = '1.0';
        suggest_dropdown_el.classList.add('hidden');
        suggest_dropdown_el.innerHTML = '';
        suggest_clear_el.classList.add('hidden');
        suggest_error_el.classList.add('hidden');
        renderPending();
    }

    function showSuggestError(message) {
        suggest_error_el.textContent = message;
        suggest_error_el.classList.remove('hidden');
    }

    /** 渲染「已选择」待提交区。 */
    function renderPending() {
        const count = panel.pending_tags.length;
        pending_box_el.classList.toggle('hidden', count === 0);
        pending_count_el.textContent = String(count);
        pending_submit_el.textContent = '提交全部 (' + count + ')';
        pending_submit_el.disabled = count === 0;
        pending_list_el.innerHTML = panel.pending_tags.map(function (tag) {
            return [
                '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-50 border border-blue-200 text-xs text-gray-700">',
                typeBadge(tag.tag_type),
                '<span class="max-w-[140px] truncate" title="', escapeHtml(tag.tag_name), '">', escapeHtml(tag.tag_name), '</span>',
                '<span class="text-gray-400 font-mono">', Number(tag.score).toFixed(2), '</span>',
                '<button type="button" data-action="remove-pending" data-tag-id="', tag.tag_id,
                '" class="text-red-400 hover:text-red-600 transition" title="移除（未提交）"><i class="bi bi-x"></i></button>',
                '</span>',
            ].join('');
        }).join('');
    }

    /** 从推荐下拉选中标签 → 暂存到待提交区（不立即入库）。 */
    function addToPending(tag_id, tag_name, tag_type) {
        const score = Number(suggest_score_el.value);
        if (!Number.isFinite(score) || score < 0 || score > 1) {
            showSuggestError('分数必须在 0 到 1 之间');
            return;
        }
        if (panel.pending_tags.some(function (t) { return t.tag_id === tag_id; })) {
            showSuggestError('「' + tag_name + '」已在待提交列表中');
            suggest_input_el.value = '';
            suggest_dropdown_el.classList.add('hidden');
            return;
        }
        panel.pending_tags.push({
            tag_id: tag_id,
            tag_name: tag_name,
            tag_type: tag_type,
            score: score,
        });
        suggest_input_el.value = '';
        suggest_score_el.value = '1.0';
        suggest_dropdown_el.classList.add('hidden');
        suggest_dropdown_el.innerHTML = '';
        suggest_clear_el.classList.add('hidden');
        suggest_error_el.classList.add('hidden');
        renderPending();
        suggest_input_el.focus();
    }

    /** 「添加」按钮：把输入框对应的第一个推荐项加入待提交区。 */
    function addFromInput() {
        const query = suggest_input_el.value.trim();
        if (!query) {
            showSuggestError('请先从推荐列表中选择标签');
            return;
        }
        const match = panel.suggest_items.find(function (tag) {
            return tag.name.toLowerCase() === query.toLowerCase();
        }) || panel.suggest_items[0];
        if (!match) {
            showSuggestError('没有匹配的标签，请从推荐列表中选择');
            return;
        }
        addToPending(match.id, match.name, match.type);
    }

    /** 移除未提交的临时标签。 */
    function removePending(tag_id) {
        panel.pending_tags = panel.pending_tags.filter(function (tag) {
            return tag.tag_id !== tag_id;
        });
        renderPending();
    }

    /** 批量提交待提交区所有标签。 */
    async function submitPending() {
        const pending = panel.pending_tags.slice();
        if (pending.length === 0) {
            return;
        }
        let created = 0;
        let skipped = 0;
        const errors = [];
        for (const tag of pending) {
            try {
                const res = await fetch(IMAGE_TAGS_API, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        image_id: panel.id,
                        tag_id: tag.tag_id,
                        score: tag.score,
                    }),
                });
                if (res.status === 201) {
                    created += 1;
                } else if (res.status === 409) {
                    skipped += 1;
                } else {
                    const body = await res.json().catch(function () { return null; });
                    errors.push('「' + tag.tag_name + '」: '
                        + (body && body.detail ? String(body.detail) : '失败'));
                }
            } catch (err) {
                console.error('提交标签失败:', err);
                errors.push('「' + tag.tag_name + '」: 网络错误');
            }
        }
        panel.pending_tags = [];
        renderPending();
        let message = '已添加 ' + created + ' 个标签';
        if (skipped > 0) {
            message += '，跳过 ' + skipped + ' 个（已存在）';
        }
        if (errors.length > 0) {
            message += '\n' + errors.join('\n');
        }
        window.alert(message);
        await refreshPanel();
        await fetchList(state.page);
    }

    // ==================== 推荐下拉 ====================

    function renderSuggestDropdown(items) {
        suggest_dropdown_el.innerHTML = items.map(function (tag) {
            return [
                '<button type="button" data-tag-id="', tag.id, '" data-tag-name="', escapeHtml(tag.name),
                '" data-tag-type="', tag.type,
                '" class="w-full text-left px-4 py-2 hover:bg-blue-50 transition flex items-center gap-2 min-w-0">',
                typeBadge(tag.type),
                '<span class="text-sm text-gray-800 truncate">', escapeHtml(tag.name), '</span>',
                '</button>',
            ].join('');
        }).join('');
        suggest_dropdown_el.classList.remove('hidden');
    }

    async function fetchSuggestions(query) {
        try {
            const res = await fetch(TAGS_API + '?query=' + encodeURIComponent(query) + '&limit=' + SUGGEST_LIMIT);
            if (!res.ok) {
                throw new Error('推荐失败');
            }
            const items = await res.json();
            panel.suggest_items = items;
            if (items.length === 0) {
                suggest_dropdown_el.classList.add('hidden');
                suggest_dropdown_el.innerHTML = '';
            } else {
                renderSuggestDropdown(items);
            }
        } catch (err) {
            console.error('加载标签推荐失败:', err);
        }
    }

    function onSuggestInput() {
        suggest_clear_el.classList.toggle('hidden', !suggest_input_el.value.trim());
        suggest_error_el.classList.add('hidden');
        const query = suggest_input_el.value.trim();
        if (!query) {
            suggest_dropdown_el.classList.add('hidden');
            suggest_dropdown_el.innerHTML = '';
            return;
        }
        if (panel.suggest_timer !== null) {
            clearTimeout(panel.suggest_timer);
        }
        panel.suggest_timer = setTimeout(function () {
            fetchSuggestions(query);
        }, SUGGEST_DEBOUNCE_MS);
    }

    // ==================== 大图预览 ====================

    function openPreview(relpath) {
        preview_image_el.src = buildImageUrl(relpath);
        preview_modal_el.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }

    function closePreview() {
        preview_modal_el.classList.add('hidden');
        document.body.style.overflow = '';
    }

    // ==================== 删除已提交标签 ====================

    async function removeTag(tag_id, tag_name) {
        if (!panel.id) {
            return;
        }
        if (!window.confirm('确定删除图片 #' + panel.id + ' 的标签「' + tag_name + '」吗？')) {
            return;
        }
        try {
            const res = await fetch(IMAGE_TAGS_API + '/' + panel.id + '/' + tag_id, { method: 'DELETE' });
            if (res.status === 404) {
                window.alert('标签关联不存在，可能已被删除');
            } else if (!res.ok) {
                window.alert('删除失败，请重试');
            }
            await refreshPanel();
            await fetchList(state.page);
        } catch (err) {
            console.error('删除标签失败:', err);
            window.alert('网络错误，请重试');
        }
    }

    // ==================== 初始化 ====================

    function bindPanelEvents() {
        document.getElementById('panel-backdrop').addEventListener('click', closePanel);
        document.getElementById('panel-close').addEventListener('click', closePanel);
        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') {
                return;
            }
            if (!preview_modal_el.classList.contains('hidden')) {
                closePreview();
            } else if (!panel_modal_el.classList.contains('hidden')) {
                closePanel();
            }
        });

        suggest_input_el.addEventListener('input', onSuggestInput);
        suggest_clear_el.addEventListener('click', function () {
            suggest_input_el.value = '';
            suggest_dropdown_el.classList.add('hidden');
            suggest_dropdown_el.innerHTML = '';
            suggest_clear_el.classList.add('hidden');
            suggest_error_el.classList.add('hidden');
            suggest_input_el.focus();
        });
        suggest_dropdown_el.addEventListener('click', function (event) {
            const btn = event.target.closest('[data-tag-id]');
            if (!btn) {
                return;
            }
            addToPending(Number(btn.dataset.tagId), btn.dataset.tagName, btn.dataset.tagType);
        });
        // 点击面板外部关闭下拉
        document.addEventListener('click', function (event) {
            if (!event.target.closest('.relative')) {
                suggest_dropdown_el.classList.add('hidden');
            }
        });
        document.getElementById('suggest-add').addEventListener('click', addFromInput);
        pending_submit_el.addEventListener('click', submitPending);
        pending_list_el.addEventListener('click', function (event) {
            const btn = event.target.closest('[data-action="remove-pending"]');
            if (!btn) {
                return;
            }
            removePending(Number(btn.dataset.tagId));
        });

        panel_tags_el.addEventListener('click', function (event) {
            const btn = event.target.closest('[data-action="remove-tag"]');
            if (!btn) {
                return;
            }
            removeTag(Number(btn.dataset.tagId), btn.dataset.tagName);
        });
    }

    function initAdmin() {
        table_body_el = document.getElementById('table-body');
        empty_row_el = document.getElementById('empty-row');
        pagination_el = document.getElementById('pagination');
        total_count_el = document.getElementById('total-count');
        per_page_el = document.getElementById('per-page');
        per_page_el.value = String(state.per_page);
        per_page_el.addEventListener('change', function () {
            state.per_page = Number(per_page_el.value);
            fetchList(1);
        });
        search_form_el = document.getElementById('search-form');
        search_input_el = document.getElementById('search-input');
        search_clear_el = document.getElementById('search-clear');
        panel_modal_el = document.getElementById('panel-modal');
        panel_image_el = document.getElementById('panel-image');
        panel_tags_el = document.getElementById('panel-tags');
        suggest_input_el = document.getElementById('suggest-input');
        suggest_dropdown_el = document.getElementById('suggest-dropdown');
        suggest_clear_el = document.getElementById('suggest-clear');
        suggest_error_el = document.getElementById('suggest-error');
        suggest_score_el = document.getElementById('suggest-score');
        pending_box_el = document.getElementById('pending-box');
        pending_count_el = document.getElementById('pending-count');
        pending_list_el = document.getElementById('pending-list');
        pending_submit_el = document.getElementById('pending-submit');
        preview_modal_el = document.getElementById('preview-modal');
        preview_image_el = document.getElementById('preview-image');

        // 搜索
        search_form_el.addEventListener('submit', function (event) {
            event.preventDefault();
            state.search = search_input_el.value;
            fetchList(1);
        });
        search_input_el.addEventListener('input', function () {
            search_clear_el.classList.toggle('hidden', !search_input_el.value.trim());
        });
        search_clear_el.addEventListener('click', function () {
            search_input_el.value = '';
            search_clear_el.classList.add('hidden');
            state.search = '';
            fetchList(1);
        });

        // 列表操作（事件委托：缩略图放大 / 管理标签）
        table_body_el.addEventListener('click', function (event) {
            const preview_img = event.target.closest('img[data-action="preview"]');
            if (preview_img) {
                openPreview(preview_img.dataset.filepath);
                return;
            }
            const btn = event.target.closest('[data-action="manage"]');
            if (!btn) {
                return;
            }
            openPanel(Number(btn.dataset.id));
        });

        // 大图预览关闭（点击图片或遮罩均可关闭）
        preview_image_el.addEventListener('click', closePreview);
        document.getElementById('preview-backdrop').addEventListener('click', closePreview);

        // 分页（事件委托）
        pagination_el.addEventListener('click', function (event) {
            const btn = event.target.closest('[data-page]');
            if (!btn) {
                return;
            }
            const page = Number(btn.dataset.page);
            if (!Number.isNaN(page)) {
                fetchList(page);
            }
        });

        bindPanelEvents();
        fetchList(1);
    }

    document.addEventListener('DOMContentLoaded', initAdmin);
})();
