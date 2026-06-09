from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('aggregator', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='nlpresult',
            name='news_relevance_score',
            field=models.FloatField(default=0.0),
        ),
    ]
