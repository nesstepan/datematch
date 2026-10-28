from django.urls import include, path

handler400 = "core.errors.bad_request"
handler403 = "core.errors.forbidden"
handler404 = "core.errors.not_found"
handler500 = "core.errors.server_error"

urlpatterns = [path("", include("core.urls"))]
