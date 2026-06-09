from django.core.cache import cache
from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = "Fast NewsIQ refresh pipeline: crawl, analyze, translate, sync jobs, and build reports."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-rss",
            action="store_true",
            help="Skip RSS/news crawling.",
        )

        parser.add_argument(
            "--skip-youtube",
            action="store_true",
            help="Skip YouTube RSS crawling.",
        )

        parser.add_argument(
            "--skip-x",
            action="store_true",
            help="Skip X/Twitter syncing.",
        )

        parser.add_argument(
            "--skip-analysis",
            action="store_true",
            help="Skip NLP/news analysis.",
        )

        parser.add_argument(
            "--skip-translation",
            action="store_true",
            help="Skip translation.",
        )

        parser.add_argument(
            "--skip-jobs",
            action="store_true",
            help="Skip public job syncing.",
        )

        parser.add_argument(
            "--skip-reports",
            action="store_true",
            help="Skip report generation.",
        )

        parser.add_argument(
            "--skip-alerts",
            action="store_true",
            help="Skip alert matching and notification creation.",
        )

        parser.add_argument(
            "--with-transcripts",
            action="store_true",
            help="Also fetch YouTube transcripts. WARNING: this can take hours.",
        )

        parser.add_argument(
            "--with-channel-summaries",
            action="store_true",
            help="Also summarize YouTube channels. Use only after transcripts are ready.",
        )

        parser.add_argument(
            "--jobs-limit",
            type=int,
            default=50,
            help="Number of jobs to sync per job source.",
        )

        parser.add_argument(
            "--top",
            type=int,
            default=20,
            help="Number of top stories to include in reports.",
        )

    def _run_command(self, command_name, **kwargs):
        self.stdout.write("")
        self.stdout.write(f"Running: {command_name}")

        call_command(
            command_name,
            verbosity=1,
            **kwargs,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Completed: {command_name}"
            )
        )

    def handle(self, *args, **options):
        lock_key = "newsiq_refresh_pipeline_running"

        if cache.get(lock_key):
            self.stdout.write(
                self.style.WARNING(
                    "Refresh pipeline is already running. Skipping."
                )
            )
            return

        cache.set(lock_key, True, timeout=30 * 60)

        try:
            self.stdout.write(
                self.style.SUCCESS(
                    "Starting fast NewsIQ refresh pipeline..."
                )
            )

            # ---------------------------------------------------------
            # Step 1: Crawl RSS/news sources
            # ---------------------------------------------------------
            if not options["skip_rss"]:
                self.stdout.write("")
                self.stdout.write("Step 1: Crawling RSS/news sources...")
                self._run_command("crawl_rss")

            # ---------------------------------------------------------
            # Step 2: Crawl YouTube RSS only
            # IMPORTANT:
            # This only fetches YouTube video metadata.
            # It does NOT fetch transcripts unless --with-transcripts is used.
            # ---------------------------------------------------------
            if not options["skip_youtube"]:
                self.stdout.write("")
                self.stdout.write("Step 2: Crawling YouTube RSS sources...")
                self._run_command("crawl_youtube")

                if options["with_transcripts"]:
                    self.stdout.write("")
                    self.stdout.write(
                        self.style.WARNING(
                            "Step 2B: Fetching YouTube transcripts. "
                            "This can take a very long time."
                        )
                    )
                    self._run_command("fetch_transcripts")
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "Skipping fetch_transcripts by default. "
                            "Use --with-transcripts only when needed."
                        )
                    )

                if options["with_channel_summaries"]:
                    self.stdout.write("")
                    self.stdout.write("Step 2C: Summarizing YouTube channels...")
                    self._run_command("summarize_youtube_channels")
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "Skipping summarize_youtube_channels by default."
                        )
                    )

            # ---------------------------------------------------------
            # Step 3: Sync X/Twitter posts
            # ---------------------------------------------------------
            if not options["skip_x"]:
                self.stdout.write("")
                self.stdout.write("Step 3: Syncing X/Twitter posts...")
                self._run_command("sync_x_posts")

            # ---------------------------------------------------------
            # Step 4: Analyze items
            # ---------------------------------------------------------
            if not options["skip_analysis"]:
                self.stdout.write("")
                self.stdout.write("Step 4: Running NLP/news analysis...")
                self._run_command("analyze_items")

            # ---------------------------------------------------------
            # Step 5: Translate items
            # ---------------------------------------------------------
            if not options["skip_translation"]:
                self.stdout.write("")
                self.stdout.write("Step 5: Translating items...")
                self._run_command("translate_items")

            # ---------------------------------------------------------
            # Step 6: Sync public jobs
            # ---------------------------------------------------------
            if not options["skip_jobs"]:
                self.stdout.write("")
                self.stdout.write("Step 6: Syncing public jobs...")

                self._run_command(
                    "sync_public_jobs",
                    limit_per_source=options["jobs_limit"],
                )

            # ---------------------------------------------------------
            # Step 7: Build reports
            # ---------------------------------------------------------
            if not options["skip_reports"]:
                self.stdout.write("")
                self.stdout.write("Step 7: Building intelligence reports...")

                for period in ["daily", "weekly", "monthly", "annual"]:
                    self.stdout.write("")
                    self.stdout.write(f"Building {period} report...")

                    self._run_command(
                        "build_daily_report",
                        period=period,
                        top=options["top"],
                    )

            # ---------------------------------------------------------
            # Step 8: Match alert rules
            # ---------------------------------------------------------
            if not options["skip_alerts"]:
                self.stdout.write("")
                self.stdout.write("Step 8: Matching alerts and notifications...")
                self._run_command("run_alerts")

            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    "Fast NewsIQ refresh pipeline completed successfully."
                )
            )

        except KeyboardInterrupt:
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR(
                    "Refresh pipeline interrupted by user."
                )
            )

        except Exception as exc:
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR(
                    f"Refresh pipeline failed: {exc}"
                )
            )

        finally:
            cache.delete(lock_key)
