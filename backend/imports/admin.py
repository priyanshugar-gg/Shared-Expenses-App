from django.contrib import admin
from .models import ImportBatch, ImportRow


class ImportRowInline(admin.TabularInline):
    model = ImportRow
    extra = 0
    fields = ("row_number", "proposed_action", "resolution")
    readonly_fields = ("row_number", "proposed_action")


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "file_name", "group", "status", "total_rows", "uploaded_at")
    list_filter = ("status", "group")
    inlines = [ImportRowInline]


@admin.register(ImportRow)
class ImportRowAdmin(admin.ModelAdmin):
    list_display = ("id", "batch", "row_number", "proposed_action", "resolution")
    list_filter = ("proposed_action", "resolution", "batch")