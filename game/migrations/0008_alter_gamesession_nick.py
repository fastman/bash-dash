from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0007_gamesettings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gamesession',
            name='nick',
            field=models.CharField(max_length=64),
        ),
    ]
