from fastapi.routing import APIRouter

from image_browser.web.admin import image, image_tag, tag_translation

router = APIRouter()
router.include_router(image.router)
router.include_router(image_tag.router)
router.include_router(tag_translation.router)

__all__ = ["router"]
