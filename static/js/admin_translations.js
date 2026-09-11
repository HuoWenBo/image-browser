/**
 * 翻译管理页逻辑（全局标签翻译 tag_translation，原生 JS，前后端分离）。
 * 视图：全部翻译 / 缺失翻译（tag 目录中无翻译的标签）；
 * 操作：新增、编辑、删除、批量导入（按标签名匹配 tag 表）。
 *
 * 命名规范：函数小驼峰、变量 snake_case、全局常量全大写加下划线。
 */
(function () {
    'use strict';

    // ==================== 共享模块 ====================
    const { escapeHtml } = window.ImageGalleryUtils || {};
    const { buildPaginationHtml } = window.GalleryPagination || {};

    // ==================== 全局常量 ====================
    const API_BASE = '/api/tag-translations';
    const DEFAULT_PER_PAGE = 15;

    const TYPE_BADGES = {
        GENERAL: ['通用', 'bg-blue-100 text-blue-700'],
        CHARACTER_NAME: ['角色', 'bg-purple-100 text-purple-700'],
        COPYRIGHT: ['作品', 'bg-green-100 text-green-700'],
    };

    // ==================== 页面状态 ====================
    let state = {
        mode: 'all',          // 'all' | 'missing'
        items: [],
        page: 1,
        per_page: DEFAULT_PER_PAGE,
        total: 0,
        total_pages: 1,
        search: '',
        filters: { type: '', sub_type: '', language: '' },
        editing: null,        // 编辑中的翻译 { tag_id, language }
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
    let tab_all_el = null;
    let tab_missing_el = null;
    let batch_btn_el = null;
    let form_modal_el = null;
    let form_title_el = null;
    let form_el = null;
    let form_error_el = null;
    let form_tag_id_el = null;
    let form_language_el = null;
    let form_content_el = null;
    let batch_modal_el = null;
    let batch_error_el = null;
    let batch_language_el = null;
    let batch_input_el = null;
    let filter_type_el = null;
    let filter_subtype_el = null;
    let filter_language_el = null;
    let filter_reset_el = null;

    // ==================== 工具函数 ====================

    function typeBadge(type) {
        const entry = TYPE_BADGES[type] || [type, 'bg-gray-100 text-gray-600'];
        return '<span class="inline-flex px-2.5 py-0.5 rounded-full text-xs ' + entry[1] + '">' + entry[0] + '</span>';
    }

    function subTypeBadge(sub_type) {
        if (!sub_type) {
            return '<span class="text-gray-300 text-xs">—</span>';
        }
        const label = ImageGalleryUtils.SUBTYPE_LABELS[sub_type]
            || sub_type.replace(/_/g, ' ').toLowerCase();
        return '<span class="inline-flex px-2.5 py-0.5 rounded-full text-xs bg-gray-100 text-gray-500">'
            + label + '</span>';
    }

    /** 全部翻译视图行。 */
    function translationRowHtml(item) {
        return [
            '<tr class="border-b border-gray-100 hover:bg-gray-50">',
            '<td class="px-4 py-3 text-gray-400 text-sm">#', item.tag_id, '</td>',
            '<td class="px-4 py-3 text-sm text-gray-800 font-mono">', escapeHtml(item.tag_name), '</td>',
            '<td class="px-4 py-3">', typeBadge(item.type), '</td>',
            '<td class="px-4 py-3">', subTypeBadge(item.sub_type), '</td>',
            '<td class="px-4 py-3"><span class="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">', escapeHtml(item.language), '</span></td>',
            '<td class="px-4 py-3 text-sm text-gray-800">', escapeHtml(item.content), '</td>',
            '<td class="px-4 py-3 whitespace-nowrap">',
            '<button type="button" data-action="edit" data-tag-id="', item.tag_id,
            '" data-tag-name="', escapeHtml(item.tag_name),
            '" data-language="', escapeHtml(item.language),
            '" data-content="', escapeHtml(item.content),
            '" class="text-blue-600 hover:text-blue-800 mr-3" title="编辑"><i class="bi bi-pencil"></i></button>',
            '<button type="button" data-action="delete" data-tag-id="', item.tag_id,
            '" data-tag-name="', escapeHtml(item.tag_name),
            '" data-language="', escapeHtml(item.language),
            '" class="text-red-500 hover:text-red-700" title="删除"><i class="bi bi-trash"></i></button>',
            '</td>',
            '</tr>',
        ].join('');
    }

    /** 缺失翻译视图行。 */
    function missingRowHtml(item) {
        return [
            '<tr class="border-b border-gray-100 hover:bg-gray-50">',
            '<td class="px-4 py-3 text-gray-400 text-sm">#', item.tag_id, '</td>',
            '<td class="px-4 py-3 text-sm text-gray-800 font-mono">', escapeHtml(item.tag_name), '</td>',
            '<td class="px-4 py-3">', typeBadge(item.type), '</td>',
            '<td class="px-4 py-3">', subTypeBadge(item.sub_type), '</td>',
            '<td class="px-4 py-3"><span class="text-xs px-2 py-0.5 bg-red-50 text-red-500 rounded">未翻译</span></td>',
            '<td class="px-4 py-3 text-sm text-gray-300">—</td>',
            '<td class="px-4 py-3 whitespace-nowrap">',
            '<button type="button" data-action="add-missing" data-tag-id="', item.tag_id,
            '" data-tag-name="', escapeHtml(item.tag_name),
            '" class="text-blue-600 hover:text-blue-800" title="添加翻译"><i class="bi bi-plus-circle"></i></button>',
            '</td>',
            '</tr>',
        ].join('');
    }

    // ==================== 渲染 ====================

    function renderTable() {
        if (state.items.length === 0) {
            table_body_el.innerHTML = '';
            empty_row_el.classList.remove('hidden');
            return;
        }
        empty_row_el.classList.add('hidden');
        table_body_el.innerHTML = state.items
            .map(state.mode === 'missing' ? missingRowHtml : translationRowHtml)
            .join('');
    }

    function renderPagination() {
        pagination_el.innerHTML = buildPaginationHtml(state.page, state.total_pages);
    }

    function renderTotalCount() {
        total_count_el.textContent = '共 ' + state.total + ' 条';
    }

    function renderTabs() {
        const active = 'bg-white text-blue-600 shadow-sm';
        const idle = 'text-gray-500 hover:text-gray-700';
        tab_all_el.className = 'px-4 py-1.5 rounded-md font-medium transition ' + (state.mode === 'all' ? active : idle);
        tab_missing_el.className = 'px-4 py-1.5 rounded-md font-medium transition ' + (state.mode === 'missing' ? active : idle);
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
        });
        const query = state.search.trim();
        if (query) {
            params.append('query', query);
        }
        if (state.filters.type) {
            params.append('tag_type', state.filters.type);
        }
        if (state.filters.sub_type) {
            params.append('sub_type', state.filters.sub_type);
        }
        if (state.mode !== 'missing' && state.filters.language) {
            params.append('language', state.filters.language);
        }
        const base = state.mode === 'missing' ? API_BASE + '/missing' : API_BASE;
        return base + '?' + params.toString();
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

    // ==================== 新增 / 编辑弹窗 ====================

    /** item 为编辑对象；preset 为新增时的预填信息（tag_id/type）。 */
    function openForm(item, preset) {
        state.editing = item || null;
        form_error_el.classList.add('hidden');
        if (item) {
            form_title_el.textContent = '编辑翻译';
            form_tag_id_el.value = String(item.tag_id);
            form_tag_id_el.disabled = true;
            form_language_el.value = item.language;
            form_language_el.disabled = true;
            form_content_el.value = item.content;
        } else {
            form_title_el.textContent = '新增翻译';
            form_tag_id_el.value = preset && preset.tag_id ? String(preset.tag_id) : '';
            form_tag_id_el.disabled = !!(preset && preset.tag_id);
            form_language_el.value = 'zh';
            form_language_el.disabled = false;
            form_content_el.value = '';
        }
        form_modal_el.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        form_content_el.focus();
    }

    function closeForm() {
        form_modal_el.classList.add('hidden');
        document.body.style.overflow = '';
        state.editing = null;
    }

    function showFormError(message) {
        form_error_el.textContent = message;
        form_error_el.classList.remove('hidden');
    }

    function collectFormPayload() {
        const tag_id = Number(form_tag_id_el.value.trim());
        const language = form_language_el.value.trim();
        const content = form_content_el.value.trim();
        if (!Number.isInteger(tag_id) || tag_id <= 0) {
            showFormError('标签 ID 必须是正整数');
            return null;
        }
        if (!language) {
            showFormError('请输入语言代码');
            return null;
        }
        if (!content) {
            showFormError('请输入翻译内容');
            return null;
        }
        return {
            tag_id: tag_id,
            language: language,
            content: content,
        };
    }

    async function submitForm() {
        const payload = collectFormPayload();
        if (!payload) {
            return;
        }
        try {
            let res;
            if (state.editing) {
                const url = API_BASE + '/' + state.editing.tag_id + '/' + encodeURIComponent(state.editing.language);
                res = await fetch(url, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: payload.content }),
                });
            } else {
                res = await fetch(API_BASE, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
            }
            if (res.status === 404) {
                const body = await res.json().catch(function () { return null; });
                showFormError(body && body.detail ? String(body.detail) : '记录不存在');
                return;
            }
            if (!res.ok) {
                showFormError('保存失败');
                return;
            }
            closeForm();
            await fetchList(state.page);
        } catch (err) {
            console.error('保存失败:', err);
            showFormError('网络错误，请重试');
        }
    }

    // ==================== 删除 ====================

    async function removeTranslation(tag_id, tag_name, language) {
        if (!window.confirm('确定删除标签「' + tag_name + '」（' + language + '）的翻译吗？')) {
            return;
        }
        try {
            const res = await fetch(
                API_BASE + '/' + tag_id + '/' + encodeURIComponent(language),
                { method: 'DELETE' },
            );
            if (res.status === 404) {
                window.alert('翻译不存在，可能已被删除');
            } else if (!res.ok) {
                window.alert('删除失败，请重试');
            }
            await fetchList(state.page);
        } catch (err) {
            console.error('删除失败:', err);
            window.alert('网络错误，请重试');
        }
    }

    // ==================== 批量导入 ====================

    function openBatch() {
        batch_error_el.classList.add('hidden');
        batch_language_el.value = 'zh';
        batch_input_el.value = '';
        batch_modal_el.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        batch_input_el.focus();
    }

    function closeBatch() {
        batch_modal_el.classList.add('hidden');
        document.body.style.overflow = '';
    }

    function parseBatchEntries() {
        const language = batch_language_el.value.trim();
        if (!language) {
            return { error: '请输入语言代码' };
        }
        const lines = batch_input_el.value.split(/\r?\n/).map(function (line) {
            return line.replace(/\s+/g, ' ').trim();
        }).filter(Boolean);
        const entries = [];
        for (const line of lines) {
            // 以第一个空格或 Tab 分割：标签名 + 翻译内容（内容可含空格）
            const idx = line.search(/\s/);
            const tag_name = (idx === -1 ? line : line.slice(0, idx)).trim();
            const content = (idx === -1 ? '' : line.slice(idx).trim());
            if (!tag_name || !content) {
                return { error: '第 ' + (entries.length + 1) + ' 行格式错误：需要「标签名 翻译内容」' };
            }
            entries.push({ tag_name: tag_name, language: language, content: content });
        }
        if (entries.length === 0) {
            return { error: '请输入至少一行内容' };
        }
        return { entries: entries };
    }

    async function submitBatch() {
        const parsed = parseBatchEntries();
        if (parsed.error) {
            batch_error_el.textContent = parsed.error;
            batch_error_el.classList.remove('hidden');
            return;
        }
        try {
            const res = await fetch(API_BASE + '/batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entries: parsed.entries }),
            });
            if (!res.ok) {
                const body = await res.json().catch(function () { return null; });
                const detail = body && body.detail ? String(body.detail) : '导入失败';
                batch_error_el.textContent = detail;
                batch_error_el.classList.remove('hidden');
                return;
            }
            const data = await res.json();
            let message = '已导入/更新 ' + data.updated + ' 条翻译';
            if (data.missing && data.missing.length > 0) {
                message += '\n未匹配的标签（' + data.missing.length + ' 个）：\n' + data.missing.join('、');
            }
            window.alert(message);
            closeBatch();
            await fetchList(state.page);
        } catch (err) {
            console.error('批量导入失败:', err);
            batch_error_el.textContent = '网络错误，请重试';
            batch_error_el.classList.remove('hidden');
        }
    }

    // ==================== 初始化 ====================

    function switchMode(mode) {
        if (state.mode === mode) {
            return;
        }
        state.mode = mode;
        renderTabs();
        filter_language_el.disabled = mode === 'missing';
        fetchList(1);
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
        tab_all_el = document.getElementById('tab-all');
        tab_missing_el = document.getElementById('tab-missing');
        batch_btn_el = document.getElementById('batch-btn');
        form_modal_el = document.getElementById('form-modal');
        form_title_el = document.getElementById('form-title');
        form_el = document.getElementById('translation-form');
        form_error_el = document.getElementById('form-error');
        form_tag_id_el = document.getElementById('form-tag-id');
        form_language_el = document.getElementById('form-language');
        form_content_el = document.getElementById('form-content');
        batch_modal_el = document.getElementById('batch-modal');
        batch_error_el = document.getElementById('batch-error');
        batch_language_el = document.getElementById('batch-language');
        batch_input_el = document.getElementById('batch-input');
        filter_type_el = document.getElementById('filter-type');
        filter_subtype_el = document.getElementById('filter-subtype');
        filter_language_el = document.getElementById('filter-language');
        filter_reset_el = document.getElementById('filter-reset');

        // 视图切换
        tab_all_el.addEventListener('click', function () { switchMode('all'); });
        tab_missing_el.addEventListener('click', function () { switchMode('missing'); });

        // 条件过滤
        filter_type_el.addEventListener('change', function () {
            state.filters.type = filter_type_el.value;
            fetchList(1);
        });
        filter_subtype_el.addEventListener('change', function () {
            state.filters.sub_type = filter_subtype_el.value;
            fetchList(1);
        });
        filter_language_el.addEventListener('change', function () {
            state.filters.language = filter_language_el.value;
            fetchList(1);
        });
        filter_reset_el.addEventListener('click', function () {
            filter_type_el.value = '';
            filter_subtype_el.value = '';
            filter_language_el.value = '';
            state.filters = { type: '', sub_type: '', language: '' };
            fetchList(1);
        });

        // 新增 / 编辑弹窗（新增入口在缺失翻译视图）
        form_el.addEventListener('submit', function (event) {
            event.preventDefault();
            submitForm();
        });
        document.getElementById('modal-backdrop').addEventListener('click', closeForm);
        document.getElementById('modal-cancel').addEventListener('click', closeForm);

        // 批量导入弹窗
        batch_btn_el.addEventListener('click', openBatch);
        document.getElementById('batch-backdrop').addEventListener('click', closeBatch);
        document.getElementById('batch-cancel').addEventListener('click', closeBatch);
        document.getElementById('batch-submit').addEventListener('click', submitBatch);

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

        // 表格操作（事件委托）
        table_body_el.addEventListener('click', function (event) {
            const btn = event.target.closest('[data-action]');
            if (!btn) {
                return;
            }
            const action = btn.dataset.action;
            if (action === 'edit') {
                openForm({
                    tag_id: Number(btn.dataset.tagId),
                    tag_name: btn.dataset.tagName,
                    language: btn.dataset.language,
                    content: btn.dataset.content,
                });
            } else if (action === 'delete') {
                removeTranslation(
                    Number(btn.dataset.tagId),
                    btn.dataset.tagName,
                    btn.dataset.language,
                );
            } else if (action === 'add-missing') {
                openForm(null, {
                    tag_id: Number(btn.dataset.tagId),
                    tag_name: btn.dataset.tagName,
                });
            }
        });

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

        // Esc 关闭弹窗
        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') {
                return;
            }
            if (!batch_modal_el.classList.contains('hidden')) {
                closeBatch();
            } else if (!form_modal_el.classList.contains('hidden')) {
                closeForm();
            }
        });

        renderTabs();
        fetchList(1);
    }

    document.addEventListener('DOMContentLoaded', initAdmin);
})();
