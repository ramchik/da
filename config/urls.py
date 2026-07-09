from django.contrib import admin
from django.urls import path

admin.site.site_header = "Dialysis Vascular Access Registry"
admin.site.site_title = "DA Registry"
admin.site.index_title = "Registry administration"

urlpatterns = [
    path("admin/", admin.site.urls),
]
