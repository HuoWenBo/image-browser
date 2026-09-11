/**
 * 图片管理页逻辑（原生 JS，前后端分离）。
 * 列表/上传/查看/删除全部通过 fetch 调用 RESTful API（/api/images）。
 * 工具函数与分页 HTML 复用共享模块 utils.js / pagination.js。
 *
 * 命名规范：函数小驼峰、变量 snake_case、全局常量全大写加下划线。
 */
(function () {
    'use strict';

    // ==================== 共享模块 ====================
    const { escapeHtml, formatSize, buildImageUrl } = window.ImageGalleryUtils || {};
    const { buildPaginationHtml } = window.GalleryPagination || {};

    // ==================== 全局常量 ====================
    const API_BASE = '/api/images';
    const DEFAULT_PER_PAGE = 10;
    const UPLOAD_BATCH_SIZE = 100;

    // ==================== 页面状态 ====================
    let state = {
        items: [],
        page: 1,
        per_page: DEFAULT_PER_PAGE,
        total: 0,
        total_pages: 1,
        search: '',
        upload_files: [],
        uploading: false,
        view_id: null,
        view_filepath: '',
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
    let add_btn_el = null;
    let view_modal_el = null;
    let view_image_el = null;
    let view_meta_el = null;
    let view_tags_el = null;
    let preview_modal_el = null;
    let preview_image_el = null;
    let upload_modal_el = null;
    let upload_files_input_el = null;
    let upload_dir_input_el = null;
    let upload_file_list_el = null;
    let upload_result_el = null;
    let upload_start_el = null;

    // ==================== 工具函数 ====================

    /** 格式化时间（本地时区）。 */
    function formatDatetime(value) {
        if (!value) {
            return '-';
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return '-';
        }
        return date.toLocaleString();
    }

    /** 生成缩略图 HTML（点击可放大预览，URL 基于存储相对路径）。 */
    function thumbHtml(relpath) {
        return '<img src="' + buildImageUrl(relpath) + '" alt="' + escapeHtml(relpath)
            + '" data-action="preview" data-filepath="' + escapeHtml(relpath) + '"'
            + ' class="w-12 h-16 object-contain bg-gray-100 rounded border border-gray-200 cursor-zoom-in"'
            + ' title="点击放大" onerror="this.style.display=\'none\'">';
    }

    /** 生成表格行 HTML。 */
    function rowHtml(item) {
        return [
            '<tr class="border-b border-gray-100 hover:bg-gray-50">',
            '<td class="px-4 py-3 text-gray-400 text-sm">#', item.id, '</td>',
            '<td class="px-4 py-3">', thumbHtml(item.filepath), '</td>',
            '<td class="px-4 py-3 text-sm text-gray-800 max-w-xs truncate" title="', escapeHtml(item.filename), '">',
            escapeHtml(item.filename), '</td>',
            '<td class="px-4 py-3 text-sm text-gray-600">', item.width, '&times;', item.height, '</td>',
            '<td class="px-4 py-3 text-sm text-gray-600">', escapeHtml(item.format), '</td>',
            '<td class="px-4 py-3 text-sm text-gray-600">', formatSize(item.filesize), '</td>',
            '<td class="px-4 py-3 text-sm text-gray-500">', escapeHtml(formatDatetime(item.created_at)), '</td>',
            '<td class="px-4 py-3 whitespace-nowrap">',
            '<button type="button" data-action="view" data-id="', item.id,
            '" class="text-blue-600 hover:text-blue-800 mr-3" title="查看信息"><i class="bi bi-eye"></i></button>',
            '<button type="button" data-action="delete" data-id="', item.id,
            '" class="text-red-500 hover:text-red-700" title="删除"><i class="bi bi-trash"></i></button>',
            '</td>',
            '</tr>',
        ].join('');
    }

    // ==================== 渲染函数 ====================

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
        total_count_el.textContent = '共 ' + state.total + ' 条记录';
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
            lang: 'en',
        });
        const query = state.search.trim();
        if (query) {
            params.append('query', query);
            return API_BASE + '/search?' + params.toString();
        }
        return API_BASE + '?' + params.toString();
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
            // 若当前页已超出总页数（如删除了最后一页唯一记录），回退到最后一页重拉
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

    // ==================== 查看弹窗（只读详情） ====================

    function viewMetaHtml(data) {
        const rows = [
            ['ID', '#' + data.id],
            ['文件名', data.filename],
            ['路径', data.filepath],
            ['尺寸', data.width + ' × ' + data.height],
            ['格式', data.format],
            ['大小', formatSize(data.filesize)],
            ['签名 (SHA256)', '<code class="font-mono text-xs text-gray-500 break-all">' + escapeHtml(data.signature) + '</code>'],
            ['指纹', data.fingerprint.length + ' 维向量（DCT）'],
            ['创建时间', formatDatetime(data.created_at)],
            ['修改时间', formatDatetime(data.modified_at)],
        ];
        return rows.map(function (row) {
            return '<div class="flex flex-col">'
                + '<dt class="text-gray-400 text-xs mb-0.5">' + row[0] + '</dt>'
                + '<dd class="text-gray-800 break-all">' + row[1] + '</dd>'
                + '</div>';
        }).join('');
    }

    function viewTagsHtml(data) {
        const groups = [
            ['角色', 'CHARACTER_NAME', 'bg-purple-100 text-purple-700'],
            ['作品', 'COPYRIGHT', 'bg-green-100 text-green-700'],
            ['通用标签', 'GENERAL', 'bg-blue-100 text-blue-700'],
        ];
        return groups.map(function (group) {
            const label = group[0];
            const type = group[1];
            const badge_cls = group[2];
            const items = (data.scores && data.scores[type]) || [];
            if (items.length === 0) {
                return '';
            }
            const badges = items.map(function (item) {
                return '<span class="inline-flex items-center gap-1.5 ' + badge_cls
                    + ' px-2.5 py-1 rounded-full text-xs">'
                    + escapeHtml(item.content || item.name)
                    + (item.content ? '<span class="opacity-60">(' + escapeHtml(item.name) + ')</span>' : '')
                    + '<span class="opacity-70 font-mono">' + Number(item.score).toFixed(3) + '</span>'
                    + '</span>';
            }).join('');
            return '<div class="mb-4">'
                + '<h3 class="text-sm font-semibold text-gray-500 mb-2">' + label + '（' + items.length + '）</h3>'
                + '<div class="flex flex-wrap gap-2">' + badges + '</div>'
                + '</div>';
        }).join('');
    }

    async function openView(id) {
        state.view_id = id;
        view_modal_el.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        view_image_el.src = '';
        view_meta_el.innerHTML = '<div class="text-gray-400">加载中...</div>';
        view_tags_el.innerHTML = '';
        try {
            const res = await fetch(API_BASE + '/' + id + '?lang=zh');
            if (!res.ok) {
                view_meta_el.innerHTML = '<div class="text-red-500">加载失败</div>';
                return;
            }
            const data = await res.json();
            state.view_filepath = data.filepath || '';
            view_image_el.src = buildImageUrl(state.view_filepath);
            view_meta_el.innerHTML = viewMetaHtml(data);
            view_tags_el.innerHTML = viewTagsHtml(data);
        } catch (err) {
            console.error('加载详情失败:', err);
            view_meta_el.innerHTML = '<div class="text-red-500">网络错误</div>';
        }
    }

    function closeView() {
        view_modal_el.classList.add('hidden');
        document.body.style.overflow = '';
        state.view_id = null;
        state.view_filepath = '';
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

    /** 从查看弹窗内的大图进入全屏预览。 */
    function previewFromView() {
        if (state.view_filepath) {
            openPreview(state.view_filepath);
        }
    }

    // ==================== 上传弹窗 ====================

    function openUploadModal() {
        state.upload_files = [];
        upload_file_list_el.classList.add('hidden');
        upload_file_list_el.innerHTML = '';
        upload_result_el.classList.add('hidden');
        upload_result_el.innerHTML = '';
        upload_start_el.disabled = false;
        upload_start_el.innerHTML = '<i class="bi bi-cloud-arrow-up me-1"></i> 开始上传';
        upload_modal_el.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }

    function closeUploadModal() {
        upload_modal_el.classList.add('hidden');
        document.body.style.overflow = '';
        state.upload_files = [];
    }

    /** 选择文件后更新待上传列表。 */
    function setUploadFiles(file_list) {
        state.upload_files = [];
        for (const file of file_list) {
            const relpath = file.webkitRelativePath || file.name;
            state.upload_files.push({ file: file, relpath: relpath });
        }
        renderUploadList();
    }

    function renderUploadList() {
        const files = state.upload_files;
        if (files.length === 0) {
            upload_file_list_el.classList.add('hidden');
            upload_file_list_el.innerHTML = '';
            return;
        }
        upload_file_list_el.classList.remove('hidden');
        upload_file_list_el.innerHTML = files.map(function (item) {
            return '<div class="flex items-center justify-between px-3 py-2 text-sm">'
                + '<span class="text-gray-700 truncate max-w-xs" title="' + escapeHtml(item.relpath) + '">'
                + '<i class="bi bi-image text-gray-400 mr-2"></i>' + escapeHtml(item.relpath) + '</span>'
                + '<span class="text-gray-400 text-xs flex-shrink-0 ml-2">' + formatSize(item.file.size) + '</span>'
                + '</div>';
        }).join('');
    }

    /** 渲染上传结果（created/skipped/error）。 */
    function renderUploadResult(results) {
        upload_result_el.classList.remove('hidden');
        upload_result_el.innerHTML = results.map(function (item) {
            const badge = item.status === 'created'
                ? '<span class="text-green-600"><i class="bi bi-check-circle mr-1"></i>已入库</span>'
                : item.status === 'skipped'
                    ? '<span class="text-gray-400"><i class="bi bi-dash-circle mr-1"></i>' + escapeHtml(item.message) + '</span>'
                    : '<span class="text-red-500"><i class="bi bi-x-circle mr-1"></i>' + escapeHtml(item.message) + '</span>';
            return '<div class="flex items-center justify-between px-3 py-2 text-sm">'
                + '<span class="text-gray-700 truncate max-w-xs" title="' + escapeHtml(item.filename) + '">'
                + escapeHtml(item.filename) + '</span>' + badge + '</div>';
        }).join('');
    }

    async function startUpload() {
        if (state.upload_files.length === 0 || state.uploading) {
            return;
        }
        state.uploading = true;
        upload_start_el.disabled = true;
        upload_result_el.classList.add('hidden');

        // 大文件列表分批上传，避免单请求超过 FastAPI 单次文件数上限
        const files = state.upload_files;
        const total_batches = Math.ceil(files.length / UPLOAD_BATCH_SIZE);
        const all_results = [];
        for (let batch = 0; batch < total_batches; batch++) {
            upload_start_el.innerHTML = '<i class="bi bi-arrow-repeat animate-spin me-1"></i> 解析上传中 '
                + (batch + 1) + '/' + total_batches + ' 批...';
            const chunk = files.slice(batch * UPLOAD_BATCH_SIZE, (batch + 1) * UPLOAD_BATCH_SIZE);
            const form = new FormData();
            for (const item of chunk) {
                form.append('files', item.file, item.relpath);
            }
            try {
                const res = await fetch(API_BASE + '/upload', { method: 'POST', body: form });
                if (!res.ok) {
                    throw new Error('HTTP ' + res.status);
                }
                const results = await res.json();
                all_results.push(...results);
            } catch (err) {
                console.error('批次 ' + (batch + 1) + ' 上传失败:', err);
                for (const item of chunk) {
                    all_results.push({ filename: item.relpath, status: 'error', message: '批次上传失败' });
                }
            }
        }
        try {
            renderUploadResult(all_results);
            state.upload_files = [];
            upload_file_list_el.classList.add('hidden');
            upload_file_list_el.innerHTML = '';
            await fetchList(1);
        } finally {
            state.uploading = false;
            upload_start_el.disabled = false;
            upload_start_el.innerHTML = '<i class="bi bi-cloud-arrow-up me-1"></i> 开始上传';
        }
    }

    // ==================== 删除 ====================

    async function removeImage(id) {
        if (!window.confirm('确定删除图片 #' + id + ' 吗？该操作不可恢复。')) {
            return;
        }
        try {
            const res = await fetch(API_BASE + '/' + id, { method: 'DELETE' });
            if (res.status === 404) {
                window.alert('图片不存在，可能已被删除');
            } else if (!res.ok) {
                window.alert('删除失败，请重试');
            }
            await fetchList(state.page);
        } catch (err) {
            console.error('删除失败:', err);
            window.alert('网络错误，请重试');
        }
    }

    // ==================== 初始化 ====================

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
        add_btn_el = document.getElementById('add-btn');
        view_modal_el = document.getElementById('view-modal');
        view_image_el = document.getElementById('view-image');
        view_meta_el = document.getElementById('view-meta');
        view_tags_el = document.getElementById('view-tags');
        preview_modal_el = document.getElementById('preview-modal');
        preview_image_el = document.getElementById('preview-image');
        upload_modal_el = document.getElementById('upload-modal');
        upload_files_input_el = document.getElementById('upload-files-input');
        upload_dir_input_el = document.getElementById('upload-dir-input');
        upload_file_list_el = document.getElementById('upload-file-list');
        upload_result_el = document.getElementById('upload-result');
        upload_start_el = document.getElementById('upload-start');

        // 上传入口
        add_btn_el.addEventListener('click', openUploadModal);
        document.getElementById('pick-files-btn').addEventListener('click', function () { upload_files_input_el.click(); });
        document.getElementById('pick-dir-btn').addEventListener('click', function () { upload_dir_input_el.click(); });
        upload_files_input_el.addEventListener('change', function () { setUploadFiles(upload_files_input_el.files); });
        upload_dir_input_el.addEventListener('change', function () { setUploadFiles(upload_dir_input_el.files); });
        upload_start_el.addEventListener('click', startUpload);
        document.getElementById('upload-backdrop').addEventListener('click', closeUploadModal);
        document.getElementById('upload-close').addEventListener('click', closeUploadModal);
        document.getElementById('upload-cancel').addEventListener('click', closeUploadModal);

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

        // 表格操作（事件委托：查看 / 删除 / 图片放大预览）
        table_body_el.addEventListener('click', function (event) {
            const preview_img = event.target.closest('img[data-action="preview"]');
            if (preview_img) {
                openPreview(preview_img.dataset.filepath);
                return;
            }
            const btn = event.target.closest('[data-action]');
            if (!btn) {
                return;
            }
            const id = Number(btn.dataset.id);
            if (btn.dataset.action === 'view') {
                openView(id);
            } else if (btn.dataset.action === 'delete') {
                removeImage(id);
            }
        });

        // 查看弹窗关闭
        document.getElementById('view-backdrop').addEventListener('click', closeView);
        document.getElementById('view-close').addEventListener('click', closeView);

        // 大图预览关闭
        document.getElementById('preview-backdrop').addEventListener('click', closePreview);
        preview_image_el.addEventListener('click', closePreview);

        // 分页点击（事件委托）
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

        // Esc 逐层关闭弹窗
        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') {
                return;
            }
            if (!preview_modal_el.classList.contains('hidden')) {
                closePreview();
            } else if (!view_modal_el.classList.contains('hidden')) {
                closeView();
            } else if (!upload_modal_el.classList.contains('hidden')) {
                closeUploadModal();
            }
        });

        fetchList(1);
    }

    document.addEventListener('DOMContentLoaded', initAdmin);

    // 暴露给模板内联 onclick（查看弹窗大图点击放大）
    window.ImageGalleryAdmin = {
        previewFromView: previewFromView,
    };
})();
