import datetime

import django.utils.timezone
from django.db import migrations, models


def backfill_deadline(apps, schema_editor):
    GameSession = apps.get_model('game', 'GameSession')
    for game in GameSession.objects.filter(deadline_at__isnull=True):
        game.deadline_at = game.started_at + datetime.timedelta(seconds=300)
        game.save(update_fields=['deadline_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gamesession',
            name='started_at',
            field=models.DateTimeField(db_index=True, default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='gamesession',
            name='deadline_at',
            field=models.DateTimeField(db_index=True, null=True),
        ),
        migrations.RunPython(backfill_deadline, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='gamesession',
            name='deadline_at',
            field=models.DateTimeField(db_index=True),
        ),
    ]
