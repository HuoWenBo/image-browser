/**
 * 共享工具函数（HTML 转义 / 文件大小格式化 / 图片地址拼接）。
 * 通过 window.ImageGalleryUtils 暴露，供各页面脚本复用。
 */
(function () {
    'use strict';

    const IMAGE_BASE = '/image/';

    /** HTML 转义，防止注入。 */
    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /** 字节数格式化为可读大小。 */
    function formatSize(bytes) {
        if (!bytes || bytes === 0) {
            return '0 B';
        }
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const k = 1024;
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        const size = (bytes / Math.pow(k, i)).toFixed(1);
        return size + ' ' + units[i];
    }

    /** 拼接静态图片地址（绝对 Windows 路径取文件名；相对路径按段编码）。 */
    function buildImageUrl(relpath) {
        const raw = String(relpath || '');
        if (/^[A-Za-z]:[\\/]/.test(raw)) {
            const parts = raw.split(/[\\/]/);
            return IMAGE_BASE + encodeURIComponent(parts[parts.length - 1]);
        }
        return IMAGE_BASE + raw.split('/').map(encodeURIComponent).join('/');
    }

    /** 标签类型中文名。 */
    const TYPE_LABELS = {
        COPYRIGHT: '作品',
        CHARACTER_NAME: '角色',
        GENERAL: '通用',
    };

    /** 标签子类型中文名。 */
    const SUBTYPE_LABELS = {
        CHARACTER: '人物',
        FACE_FEATURES: '五官',
        LIGHT_SHADOW: '光影',
        ACTION: '动作',
        ANIMAL: '动物',
        HAIRSTYLE: '发型',
        SCENE: '场景',
        POSE: '姿势',
        TEXT: '文本',
        CLOTHING: '服装',
        COMPOSITION: '构图',
        ITEM: '物品',
        ART_STYLE: '画风',
        BACKGROUND: '背景',
        EXPRESSION: '表情',
        EYE_SIGHT: '视线',
        QUALITY: '质量',
        BODY: '身体',
        OTHER: '其他',
    };

    window.ImageGalleryUtils = {
        escapeHtml: escapeHtml,
        formatSize: formatSize,
        buildImageUrl: buildImageUrl,
        TYPE_LABELS: TYPE_LABELS,
        SUBTYPE_LABELS: SUBTYPE_LABELS,
    };
})();
