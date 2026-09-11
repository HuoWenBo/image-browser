from fastapi.routing import APIRouter

from image_browser.web.api import (
    docs,
    image,
    image_tag,
    monitoring,
    tag,
    tag_translation,
)

router = APIRouter()
router.include_router(monitoring.router)
router.include_router(docs.router)
router.include_router(image.router, prefix="/images", tags=["image"])
router.include_router(image_tag.router, prefix="/image-tags", tags=["image-tags"])
router.include_router(tag.router, prefix="/tags", tags=["tags"])
router.include_router(
    tag_translation.router,
    prefix="/tag-translations",
    tags=["tag-translations"],
)
