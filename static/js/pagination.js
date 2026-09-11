/**
 * 共享分页 HTML 生成器。
 * buildPaginationHtml(cur, total) 返回分页 <ul> 的 HTML 字符串，
 * 页码按钮带 data-page 属性，由页面脚本用事件委托处理点击。
 * 通过 window.GalleryPagination 暴露。
 */
(function () {
    'use strict';

    /** 生成页码序列（1 ... left-right ... total，'...' 表示省略）。 */
    function paginationItems(cur, total) {
        const items = [];
        if (total <= 7) {
            for (let i = 1; i <= total; i++) {
                items.push(i);
            }
            return items;
        }
        items.push(1);
        const left = Math.max(2, cur - 2);
        const right = Math.min(total - 1, cur + 2);
        if (left > 2) {
            items.push('...');
        }
        for (let i = left; i <= right; i++) {
            items.push(i);
        }
        if (right < total - 1) {
            items.push('...');
        }
        items.push(total);
        return items;
    }

    /** 生成完整分页 HTML。 */
    function buildPaginationHtml(cur, total) {
        if (total <= 1) {
            return '';
        }
        const items = paginationItems(cur, total);
        let html = '<ul class="flex items-center gap-1">';
        const prev_disabled = cur <= 1 ? ' opacity-50 pointer-events-none' : '';
        html += '<li><button type="button" data-page="' + (cur - 1)
            + '" class="px-3 py-2 rounded-lg text-gray-600 hover:bg-gray-100 transition' + prev_disabled
            + '" title="上一页">&lsaquo;</button></li>';
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item === '...') {
                html += '<li><span class="px-3 py-2 text-gray-400">...</span></li>';
            } else {
                const active = item === cur
                    ? ' bg-blue-600 text-white hover:bg-blue-700'
                    : ' text-gray-600 hover:bg-gray-100';
                html += '<li><button type="button" data-page="' + item
                    + '" class="px-3 py-2 rounded-lg transition' + active + '">' + item + '</button></li>';
            }
        }
        const next_disabled = cur >= total ? ' opacity-50 pointer-events-none' : '';
        html += '<li><button type="button" data-page="' + (cur + 1)
            + '" class="px-3 py-2 rounded-lg text-gray-600 hover:bg-gray-100 transition' + next_disabled
            + '" title="下一页">&rsaquo;</button></li>';
        html += '</ul>';
        return html;
    }

    window.GalleryPagination = {
        buildPaginationHtml: buildPaginationHtml,
    };
})();
