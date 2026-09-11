/**
 * 图片社区首页逻辑（原生 JS，前后端分离）。
 * 不依赖 Alpine.js / HTMX；数据通过 fetch 调用 RESTful API。
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
    const DEFAULT_PER_PAGE = 12;
    const MAX_PREVIEW_TAGS = 3;
    const MAX_FINGERPRINT_PREVIEW = 3;

    // ==================== 页面状态 ====================
    let state = {
        images: [],
        cur_page: 1,
        total: 0,
        total_pages: 1,
        search: '',
        loading: false,
    };

    // ==================== DOM 引用 ====================
    let grid_el = null;
    let status_el = null;
    let status_text_el = null;
    let pagination_el = null;
    let total_count_el = null;
    let search_form_el = null;
    let search_input_el = null;
    let search_clear_el = null;
    let detail_modal_el = null;
    let detail_backdrop_el = null;
    let detail_image_wrap_el = null;
    let detail_info_el = null;
    let sbi_btn_el = null;
    let sbi_modal_el = null;
    let sbi_backdrop_el = null;
    let sbi_close_el = null;
    let sbi_file_el = null;
    let sbi_file_name_el = null;
    let sbi_dropzone_el = null;
    let sbi_search_el = null;
    let sbi_meta_el = null;
    let sbi_preview_img_el = null;
    let sbi_status_el = null;
    let sbi_status_text_el = null;
    let sbi_results_el = null;

    // ==================== 工具函数 ====================

    /** 生成标签徽标 HTML。 */
    function tagBadgeHtml(text) {
        return '<span class="bg-gray-100 text-gray-700 text-xs px-2 py-0.5 rounded-full">'
            + escapeHtml(text)
            + '</span>';
    }

    /** 生成一组标签徽标（最多展示 MAX_PREVIEW_TAGS 个，超出显示 +N）。 */
    function tagGroupHtml(items, color_class, label) {
        const list = items || [];
        if (list.length === 0) {
            return '';
        }
        let html = '<div class="flex flex-wrap gap-1 mt-1">';
        html += '<span class="' + color_class + ' text-xs px-2 py-0.5 rounded-full">' + label + '</span>';
        const preview = list.slice(0, MAX_PREVIEW_TAGS);
        for (let i = 0; i < preview.length; i++) {
            html += tagBadgeHtml(preview[i]);
        }
        if (list.length > MAX_PREVIEW_TAGS) {
            html += '<span class="bg-gray-100 text-gray-400 text-xs px-2 py-0.5 rounded-full">+'
                + (list.length - MAX_PREVIEW_TAGS) + '</span>';
        }
        html += '</div>';
        return html;
    }

    /** 生成图片网格卡片 HTML。 */
    function cardHtml(img) {
        const html = [
            '<div class="bg-white rounded-2xl overflow-hidden shadow-md hover:shadow-xl transition-all duration-200 hover:-translate-y-1 flex flex-col h-full cursor-pointer" data-id="',
            img.id,
            '">',
            '<div class="relative aspect-[3/4] max-h-[480px] bg-gray-200 flex items-center justify-center">',
            '<img src="', buildImageUrl(img.filepath), '" alt="', escapeHtml(img.filename),
            '" loading="lazy" class="absolute inset-0 w-full h-full object-contain object-center">',
            '<span class="absolute top-3 right-3 bg-black/60 backdrop-blur-sm text-white text-xs px-3 py-1 rounded-full">',
            escapeHtml(img.format), '</span>',
            '</div>',
            '<div class="p-4 flex-1 flex flex-col">',
            '<div class="flex items-center gap-3 text-xs text-gray-400 mt-1">',
            '<span><i class="bi bi-arrows-expand"></i> ', img.width, '&times;', img.height, '</span>',
            '<span><i class="bi bi-hdd"></i> ', formatSize(img.filesize), '</span>',
            '</div>',
            tagGroupHtml(img.series, 'bg-yellow-50 text-yellow-700', '作品'),
            tagGroupHtml(img.characters, 'bg-green-50 text-green-600', '角色'),
            tagGroupHtml(img.tags, 'bg-blue-50 text-blue-600', '标签'),
            '<div class="flex items-center justify-between pt-2 mt-auto border-t border-gray-100">',
            '<small class="text-gray-400 text-xs">#' + img.id + '</small>',
            '<span class="text-xs text-gray-500 border border-gray-300 rounded-full px-3 py-0.5">详情 &rarr;</span>',
            '</div>',
            '</div>',
            '</div>',
        ];
        return html.join('');
    }

    // ==================== 渲染函数 ====================

    function renderStatus(message, show_loading) {
        if (show_loading || state.images.length === 0) {
            status_el.classList.remove('hidden');
            status_text_el.innerHTML = show_loading
                ? '<i class="bi bi-arrow-repeat text-4xl animate-spin inline-block"></i><p class="mt-2">'
                    + escapeHtml(message) + '</p>'
                : escapeHtml(message);
        } else {
            status_el.classList.add('hidden');
        }
    }

    function renderGrid() {
        grid_el.innerHTML = state.images.map(cardHtml).join('');
    }

    function renderPagination() {
        pagination_el.innerHTML = buildPaginationHtml(state.cur_page, state.total_pages);
    }

    function renderTotalCount() {
        total_count_el.textContent = '共 ' + state.total + ' 张';
    }

    function setData(data) {
        state.images = data.items || [];
        state.total = data.total || 0;
        state.total_pages = data.total_pages || 1;
        if (data.page) {
            state.cur_page = data.page;
        }
    }

    // ==================== 数据请求 ====================

    function buildListUrl(page) {
        const params = new URLSearchParams({
            page: String(page),
            per_page: String(DEFAULT_PER_PAGE),
        });
        const query = state.search.trim();
        if (query) {
            params.append('query', query);
            return API_BASE + '/search?' + params.toString();
        }
        return API_BASE + '?' + params.toString();
    }

    async function fetchImages(page) {
        if (page < 1 || (state.total_pages > 0 && page > state.total_pages)) {
            return;
        }
        state.cur_page = page;
        state.loading = true;
        renderStatus('加载图片数据...', true);
        try {
            const res = await fetch(buildListUrl(page));
            if (!res.ok) {
                throw new Error('网络错误');
            }
            const data = await res.json();
            setData(data);
            state.loading = false;
            renderGrid();
            renderPagination();
            renderTotalCount();
            renderStatus(state.images.length === 0 ? '无匹配图片' : '', false);
        } catch (err) {
            console.error('加载失败:', err);
            state.loading = false;
            renderStatus('加载失败，请重试', false);
        }
    }

    // ==================== 详情弹窗 ====================

    function fingerprintPreview(values) {
        if (!values || values.length === 0) {
            return '-';
        }
        const head = values.slice(0, MAX_FINGERPRINT_PREVIEW)
            .map((v) => v.toFixed(3)).join(', ');
        const tail = values.slice(-MAX_FINGERPRINT_PREVIEW)
            .map((v) => v.toFixed(3)).join(', ');
        let html = '<span>' + escapeHtml(head);
        if (values.length > 6) {
            html += '<span class="text-gray-400 text-xs"> &hellip; </span>' + escapeHtml(tail);
        }
        // html += '<span class="text-gray-400 text-xs ml-1">(共 ' + values.length + ' 维)</span></span>';
        html += '</span>';
        return html;
    }

    function tagListHtml(items, color_class, label) {
        const list = items || [];
        let html = '<div class="flex flex-wrap gap-1 mt-1">';
        if (list.length === 0) {
            html += '<span class="text-gray-400">无</span>';
        } else {
            for (let i = 0; i < list.length; i++) {
                html += '<span class="' + color_class + ' px-2 py-0.5 rounded-full text-xs">'
                    + escapeHtml(list[i]) + '</span>';
            }
        }
        html += '</div>';
        return html;
    }

    function renderDetail(data) {
        const info_html = [
            '<div class="flex flex-wrap gap-2 text-sm text-gray-500 mb-4">',
            '<span class="bg-gray-100 px-3 py-1 rounded-full">ID: ', data.id, '</span>',
            '<span class="bg-gray-100 px-3 py-1 rounded-full">', data.width, '&times;', data.height, '</span>',
            '<span class="bg-gray-100 px-3 py-1 rounded-full">', escapeHtml(data.format), '</span>',
            '<span class="bg-gray-100 px-3 py-1 rounded-full">', formatSize(data.filesize), '</span>',
            '</div>',
            '<dl class="grid grid-cols-1 gap-x-4 gap-y-3 text-sm">',
            '<div><dt class="text-gray-400 font-medium">文件路径</dt><dd class="text-gray-700 break-all">',
            escapeHtml(data.filepath || '-'), '</dd></div>',
            '<div><dt class="text-gray-400 font-medium">签名 (SHA256)</dt><dd class="text-gray-700 break-all font-mono text-xs">',
            escapeHtml(data.signature || '-'), '</dd></div>',
            '<div><dt class="text-gray-400 font-medium">作品</dt><dd>',
            tagListHtml(data.series, 'bg-yellow-50 text-yellow-700', ''), '</dd></div>',
            '<div><dt class="text-gray-400 font-medium">角色</dt><dd>',
            tagListHtml(data.characters, 'bg-green-50 text-green-700', ''), '</dd></div>',
            '<div><dt class="text-gray-400 font-medium">标签</dt><dd>',
            tagListHtml(data.tags, 'bg-blue-50 text-blue-700', ''), '</dd></div>',
            '<div><dt class="text-gray-400 font-medium">指纹</dt><dd class="text-gray-700 break-all">',
            fingerprintPreview(data.fingerprint), '</dd></div>',
            '<div class="grid grid-cols-2 gap-2">',
            '<div><dt class="text-gray-400 font-medium">创建时间</dt><dd class="text-gray-700">',
            escapeHtml(formatDatetime(data.created_at)), '</dd></div>',
            '<div><dt class="text-gray-400 font-medium">修改时间</dt><dd class="text-gray-700">',
            escapeHtml(formatDatetime(data.modified_at)), '</dd></div>',
            '</div>',
            '</dl>',
        ].join('');

        detail_image_wrap_el.innerHTML = '<img src="' + buildImageUrl(data.filepath) + '" alt="'
            + escapeHtml(data.filename)
            + '" class="max-w-full max-h-full object-contain rounded-lg shadow-lg">'
            + '<span class="absolute bottom-4 left-4 bg-black/50 backdrop-blur-sm text-white text-xs px-3 py-1 rounded-full">'
            + escapeHtml(data.format) + '</span>';
        detail_info_el.innerHTML = info_html;
    }

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

    function openDetail(id) {
        detail_modal_el.classList.remove('hidden');
        detail_image_wrap_el.innerHTML = '<div class="text-white text-center"><i class="bi bi-arrow-repeat text-4xl animate-spin inline-block"></i><p class="mt-2">加载中...</p></div>';
        detail_info_el.innerHTML = '';
        fetch(API_BASE + '/' + id)
            .then((res) => {
                if (!res.ok) {
                    throw new Error('获取详情失败');
                }
                return res.json();
            })
            .then((data) => renderDetail(data))
            .catch((err) => {
                console.error('获取详情失败:', err);
                detail_info_el.innerHTML = '<p class="text-gray-400 text-center py-8">加载详情失败，请重试</p>';
            });
    }

    function closeModal() {
        detail_modal_el.classList.add('hidden');
    }

    // ==================== 初始化 ====================

    // ==================== 以图搜图 ====================

    function openSbiModal() {
        sbi_modal_el.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }

    function closeSbiModal() {
        sbi_modal_el.classList.add('hidden');
        document.body.style.overflow = '';
    }

    function applySbiFile(file) {
        sbi_file_name_el.textContent = file.name;
        sbi_preview_img_el.src = URL.createObjectURL(file);
        sbi_meta_el.classList.remove('hidden');
        sbi_dropzone_el.classList.add('hidden');
        sbi_search_el.disabled = false;
        sbi_results_el.innerHTML = '';
        sbi_status_el.classList.add('hidden');
    }

    function handleSbiFileChange() {
        const file = sbi_file_el.files && sbi_file_el.files[0];
        if (file) {
            applySbiFile(file);
        }
    }

    function handleSbiDrop(event) {
        event.preventDefault();
        sbi_dropzone_el.classList.remove('border-blue-400', 'bg-blue-50');
        const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
        if (!file) {
            return;
        }
        const dt = new DataTransfer();
        dt.items.add(file);
        sbi_file_el.files = dt.files;
        applySbiFile(file);
    }

    async function runSbiSearch() {
        const file = sbi_file_el.files && sbi_file_el.files[0];
        if (!file) {
            return;
        }
        const form = new FormData();
        form.append('file', file);
        sbi_search_el.disabled = true;
        sbi_results_el.innerHTML = '';
        sbi_status_el.classList.remove('hidden');
        sbi_status_text_el.textContent = '解析图片并匹配中...';
        try {
            const res = await fetch(API_BASE + '/search-by-image', { method: 'POST', body: form });
            if (!res.ok) {
                const err = await res.json().catch(function () { return {}; });
                throw new Error(err.detail || '搜索失败');
            }
            const data = await res.json();
            sbi_status_el.classList.add('hidden');
            const items = data.items || [];
            if (items.length === 0) {
                sbi_status_el.classList.remove('hidden');
                sbi_status_text_el.textContent = '未找到相似图片';
                sbi_status_el.querySelector('i').classList.add('hidden');
            } else {
                sbi_results_el.innerHTML = items.map(cardHtml).join('');
            }
        } catch (err) {
            sbi_status_el.classList.remove('hidden');
            sbi_status_text_el.textContent = err.message || '搜索失败，请重试';
            sbi_status_el.querySelector('i').classList.add('hidden');
        } finally {
            sbi_search_el.disabled = false;
        }
    }

    function initSearchByImage() {
        sbi_btn_el = document.getElementById('search-by-image-btn');
        sbi_modal_el = document.getElementById('sbi-modal');
        sbi_backdrop_el = document.getElementById('sbi-backdrop');
        sbi_close_el = document.getElementById('sbi-close');
        sbi_file_el = document.getElementById('sbi-file');
        sbi_file_name_el = document.getElementById('sbi-file-name');
        sbi_dropzone_el = document.getElementById('sbi-dropzone');
        sbi_search_el = document.getElementById('sbi-search');
        sbi_meta_el = document.getElementById('sbi-meta');
        sbi_preview_img_el = document.getElementById('sbi-preview-img');
        sbi_status_el = document.getElementById('sbi-status');
        sbi_status_text_el = document.getElementById('sbi-status-text');
        sbi_results_el = document.getElementById('sbi-results');

        sbi_btn_el.addEventListener('click', openSbiModal);
        sbi_backdrop_el.addEventListener('click', closeSbiModal);
        sbi_close_el.addEventListener('click', closeSbiModal);
        sbi_file_el.addEventListener('change', handleSbiFileChange);
        sbi_dropzone_el.addEventListener('click', function () {
            sbi_file_el.click();
        });
        sbi_dropzone_el.addEventListener('dragover', function (event) {
            event.preventDefault();
            sbi_dropzone_el.classList.add('border-blue-400', 'bg-blue-50');
        });
        sbi_dropzone_el.addEventListener('dragleave', function () {
            sbi_dropzone_el.classList.remove('border-blue-400', 'bg-blue-50');
        });
        sbi_dropzone_el.addEventListener('drop', handleSbiDrop);
        sbi_search_el.addEventListener('click', runSbiSearch);
        sbi_results_el.addEventListener('click', function (event) {
            const card = event.target.closest('[data-id]');
            if (card) {
                openDetail(Number(card.dataset.id));
            }
        });
    }

    function initGallery() {
        grid_el = document.getElementById('image-grid');
        status_el = document.getElementById('grid-status');
        status_text_el = document.getElementById('status-text');
        pagination_el = document.getElementById('pagination');
        total_count_el = document.getElementById('total-count');
        search_form_el = document.getElementById('search-form');
        search_input_el = document.getElementById('search-input');
        search_clear_el = document.getElementById('search-clear');
        detail_modal_el = document.getElementById('detail-modal');
        detail_backdrop_el = document.getElementById('modal-backdrop');
        detail_image_wrap_el = document.getElementById('detail-image-wrap');
        detail_info_el = document.getElementById('detail-info');

        // 搜索
        search_form_el.addEventListener('submit', (event) => {
            event.preventDefault();
            state.search = search_input_el.value;
            fetchImages(1);
        });
        search_input_el.addEventListener('input', () => {
            search_clear_el.classList.toggle('hidden', !search_input_el.value.trim());
        });
        search_clear_el.addEventListener('click', () => {
            search_input_el.value = '';
            search_clear_el.classList.add('hidden');
            state.search = '';
            fetchImages(1);
        });

        // 网格点击（事件委托）
        grid_el.addEventListener('click', (event) => {
            const card = event.target.closest('[data-id]');
            if (card) {
                openDetail(Number(card.dataset.id));
            }
        });

        // 分页点击（事件委托）
        pagination_el.addEventListener('click', (event) => {
            const btn = event.target.closest('[data-page]');
            if (!btn) {
                return;
            }
            const page = Number(btn.dataset.page);
            if (Number.isNaN(page)) {
                return;
            }
            fetchImages(page);
        });

        // 弹窗关闭
        detail_backdrop_el.addEventListener('click', closeModal);
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                if (!sbi_modal_el.classList.contains('hidden')) {
                    closeSbiModal();
                    return;
                }
                closeModal();
            }
        });

        initSearchByImage();
        fetchImages(1);
    }

    document.addEventListener('DOMContentLoaded', initGallery);
})();
