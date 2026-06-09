# Generated manually for MVP
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Source',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('source_type', models.CharField(choices=[('news_site', 'News Site'), ('youtube', 'YouTube'), ('x', 'X/Twitter')], max_length=30)),
                ('url', models.URLField(blank=True)),
                ('rss_url', models.URLField(blank=True)),
                ('youtube_channel_id', models.CharField(blank=True, max_length=255)),
                ('x_handle', models.CharField(blank=True, max_length=255)),
                ('x_query', models.TextField(blank=True)),
                ('crawl_method', models.CharField(choices=[('rss', 'RSS'), ('html', 'HTML'), ('youtube_api', 'YouTube API'), ('x_api', 'X API')], max_length=30)),
                ('language', models.CharField(default='ta', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='RawItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('external_id', models.CharField(blank=True, db_index=True, max_length=500)),
                ('url', models.URLField(blank=True, max_length=1000)),
                ('title', models.TextField(blank=True)),
                ('description', models.TextField(blank=True)),
                ('raw_text', models.TextField(blank=True)),
                ('raw_html', models.TextField(blank=True)),
                ('raw_json', models.JSONField(blank=True, default=dict)),
                ('published_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('fetched_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('content_hash', models.CharField(db_index=True, max_length=64)),
                ('status', models.CharField(db_index=True, default='new', max_length=50)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='raw_items', to='aggregator.source')),
            ],
        ),
        migrations.CreateModel(
            name='ContentItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content_type', models.CharField(choices=[('article', 'Article'), ('youtube_video', 'YouTube Video'), ('tweet', 'Tweet')], max_length=50)),
                ('title_ta', models.TextField(blank=True)),
                ('title_en', models.TextField(blank=True)),
                ('body_ta', models.TextField(blank=True)),
                ('body_en', models.TextField(blank=True)),
                ('url', models.URLField(blank=True, max_length=1000)),
                ('author', models.CharField(blank=True, max_length=255)),
                ('published_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('metrics', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('raw_item', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='content_item', to='aggregator.rawitem')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='content_items', to='aggregator.source')),
            ],
        ),
        migrations.CreateModel(
            name='NLPResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('summary_ta', models.TextField(blank=True)),
                ('summary_en', models.TextField(blank=True)),
                ('topics', models.JSONField(blank=True, default=list)),
                ('entities', models.JSONField(blank=True, default=dict)),
                ('people', models.JSONField(blank=True, default=list)),
                ('parties', models.JSONField(blank=True, default=list)),
                ('districts', models.JSONField(blank=True, default=list)),
                ('sentiment', models.CharField(blank=True, max_length=50)),
                ('emotion', models.CharField(blank=True, max_length=50)),
                ('intensity_score', models.FloatField(default=0.0)),
                ('political_relevance_score', models.FloatField(default=0.0)),
                ('stance_notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('content_item', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='nlp', to='aggregator.contentitem')),
            ],
        ),
        migrations.CreateModel(
            name='DailyReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_date', models.DateField(unique=True)),
                ('summary_ta', models.TextField(blank=True)),
                ('summary_en', models.TextField(blank=True)),
                ('top_stories', models.JSONField(blank=True, default=list)),
                ('source_coverage', models.JSONField(blank=True, default=dict)),
                ('party_mentions', models.JSONField(blank=True, default=dict)),
                ('topic_mentions', models.JSONField(blank=True, default=dict)),
                ('district_mentions', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-report_date']},
        ),
        migrations.AddIndex(model_name='rawitem', index=models.Index(fields=['source', 'external_id'], name='aggregator__source__3533f1_idx')),
        migrations.AddIndex(model_name='rawitem', index=models.Index(fields=['content_hash'], name='aggregator__content_bce448_idx')),
        migrations.AddIndex(model_name='rawitem', index=models.Index(fields=['published_at'], name='aggregator__publish_8f4ce8_idx')),
        migrations.AddConstraint(model_name='rawitem', constraint=models.UniqueConstraint(fields=('source', 'external_id'), name='unique_source_external_id')),
        migrations.AddIndex(model_name='contentitem', index=models.Index(fields=['content_type', 'published_at'], name='aggregator__content_a608f8_idx')),
        migrations.AddIndex(model_name='contentitem', index=models.Index(fields=['source', 'published_at'], name='aggregator__source__2e45fd_idx')),
    ]
