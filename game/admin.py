"""Read-only inspection of games during the event. S-04 builds the real staff tooling."""

from django.contrib import admin

from .models import Attempt, GameSession


class ReadOnlyMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AttemptInline(ReadOnlyMixin, admin.TabularInline):
    model = Attempt
    extra = 0
    fields = ('created_at', 'slug', 'command', 'correct', 'timed_out', 'error', 'duration_ms')
    readonly_fields = fields


@admin.register(GameSession)
class GameSessionAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ('nick', 'started_at', 'deadline_at', 'solved', 'attempts', 'finished_at')
    search_fields = ('nick',)
    inlines = [AttemptInline]
