from django.contrib import admin
from .models import Expense, ExpenseSplit, Settlement


class ExpenseSplitInline(admin.TabularInline):
    model = ExpenseSplit
    extra = 0


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("id", "description", "group", "paid_by", "date", "amount", "currency", "split_type", "source")
    list_filter = ("group", "split_type", "source", "currency")
    inlines = [ExpenseSplitInline]


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ("id", "group", "paid_by", "paid_to", "amount", "date", "source")
    list_filter = ("group",)