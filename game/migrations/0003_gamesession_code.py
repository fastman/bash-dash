from django.db import migrations, models

import game.models


def backfill_codes(apps, schema_editor):
    GameSession = apps.get_model('game', 'GameSession')
    used = set()
    for row in GameSession.objects.filter(code__isnull=True):
        code = game.models.generate_code()
        while code in used:
            code = game.models.generate_code()
        used.add(code)
        row.code = code
        row.save(update_fields=['code'])


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0002_gamesession_deadline_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesession',
            name='code',
            field=models.CharField(max_length=6, null=True, editable=False),
        ),
        migrations.RunPython(backfill_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='gamesession',
            name='code',
            field=models.CharField(
                default=game.models.generate_code, editable=False, max_length=6, unique=True),
        ),
    ]
