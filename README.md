# NewsIQ: Tamil Nadu News Intelligence Platform

NewsIQ is a Django-based Tamil Nadu news intelligence platform for collecting, organizing, translating, summarizing, and analyzing public news, jobs, political updates, YouTube items, government sources, and alert-based content.

The platform is designed to support bilingual Tamil-English news intelligence, topic tracking, public jobs discovery, periodic reports, and local LLM-assisted translation/summarization using Ollama.

---

## Features

### News Intelligence Dashboard

* View recent Tamil Nadu news items.
* Filter by source type, topic, and search query.
* Display bilingual Tamil and English titles, bodies, and summaries.
* Track topics, parties, people, districts, sentiment, and source coverage.
* Show key stories and latest generated intelligence report.

### Jobs Intelligence

* Collect and display public job listings.
* Search jobs directly in the database.
* Filter by district, category, recruiting body, qualification level, link status, and minimum salary.
* Track salary availability, job type, company, recruiting body, and qualification distribution.

### Reports

* Generate and view intelligence reports by period:

  * Daily
  * Weekly
  * Monthly
  * Annual

* Reports include:

  * Tamil summary
  * English summary
  * Top stories
  * Source coverage
  * Party mentions
  * Topic mentions
  * District mentions

### Alerts

* Create keyword-based alert rules.
* Match alerts against content items.
* Track matched keywords, snippets, event status, and unread alerts.
* Alert creation is hardened by requiring verification before external notification delivery.

### API Endpoints

The project includes JSON APIs for:

* Latest news items
* YouTube items
* Jobs
* Alerts
* Trends
* Daily/weekly/monthly/annual reports
* Keyword tracking

### Local LLM Translation and Summarization

The project can use Ollama models for:

* Tamil-to-English translation
* English-to-Tamil translation
* English summarization
* Tamil summarization

Example supported local model:

```bash
gpt-oss:20b
```

You can also use smaller local models such as:

```bash
qwen2.5:3b-instruct
qwen2.5:1.5b-instruct
```

---

## Tech Stack

* Python
* Django
* SQLite for local development
* Ollama for local LLM inference
* Requests for Ollama API calls
* Django management commands for crawling, syncing, and report generation

---

## Project Setup

### 1. Clone the Repository

```bash
git clone https://github.com/ludwigwittgenstein2/TamilNews.git
cd TamilNews
```

### 2. Create and Activate a Virtual Environment

Using `venv`:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows:

```bash
.venv\Scripts\activate
```

Using Conda:

```bash
conda create -n newsiq python=3.12
conda activate newsiq
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

If `requirements.txt` is not created yet, install the core dependencies manually:

```bash
pip install django requests
```

Then create a requirements file:

```bash
pip freeze > requirements.txt
```

---

## Environment Variables

Create a `.env` file or export these variables in your terminal.

For local Ollama use:

```bash
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_TRANSLATION_MODEL=gpt-oss:20b
```

On Windows PowerShell:

```powershell
$env:OLLAMA_BASE_URL="http://localhost:11434"
$env:OLLAMA_TRANSLATION_MODEL="gpt-oss:20b"
```

If you want to use a smaller model:

```bash
export OLLAMA_TRANSLATION_MODEL=qwen2.5:3b-instruct
```

---

## Ollama Setup

### 1. Install Ollama

Install Ollama from:

```text
https://ollama.com
```

### 2. Start Ollama

```bash
ollama serve
```

### 3. Pull a Model

```bash
ollama pull gpt-oss:20b
```

Or use a smaller model:

```bash
ollama pull qwen2.5:3b-instruct
```

### 4. Check Installed Models

```bash
ollama list
```

---

## Database Setup

Run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

Create an admin/staff user:

```bash
python manage.py createsuperuser
```

Then run the server:

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

---

## Important Migration Note

If you see an error like:

```text
sqlite3.OperationalError: no such column: aggregator_source.extract_mode
```

it means your Django models and SQLite database schema are out of sync.

Run:

```bash
python manage.py makemigrations aggregator
python manage.py migrate
```

Then restart the server:

```bash
python manage.py runserver
```

To inspect the database table manually:

```bash
python manage.py dbshell
```

Then inside SQLite:

```sql
PRAGMA table_info(aggregator_source);
```

Check whether the missing column exists.

For local development only, if you do not need the old scraped data, you can reset the database:

```bash
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

---

## Running the App

Start the Django development server:

```bash
python manage.py runserver
```

Then visit:

```text
http://127.0.0.1:8000/
```

Main pages include:

```text
/                 Main dashboard
/jobs/            Jobs intelligence
/reports/         Intelligence reports
/alerts/          Alert rules and alert events
/x-wall/          Public X/Twitter commentary wall
```

---

## Management Commands

The project uses Django management commands for crawling, syncing, translation, and report generation.

Common commands:

```bash
python manage.py sync_public_jobs --limit_per_source 50
python manage.py build_daily_report --period daily --top 20
```

Other likely pipeline commands may include:

```bash
python manage.py crawl_rss
python manage.py crawl_youtube
python manage.py fetch_transcripts
python manage.py translate_items
python manage.py build_daily_report --period weekly --top 20
python manage.py build_daily_report --period monthly --top 20
python manage.py build_daily_report --period annual --top 20
```

Use:

```bash
python manage.py help
```

to see all available commands.

---

## Staff-Only Sync and Report Generation

To prevent random public visitors or crawlers from triggering expensive operations, sync and report generation actions are gated behind staff authentication.

These actions are staff-only:

```text
/jobs/?sync=1
/reports/?generate=1
/reports/?force=1
/api/daily-report/?generate=1
/api/daily-report/?force=1
```

For production or unattended runs, use cron or a scheduled job instead of public GET requests.

Example cron-style commands:

```bash
python manage.py sync_public_jobs --limit_per_source 50
python manage.py build_daily_report --period daily --top 20
```

---

## Ollama Translation Helper

The project can use a local Ollama model for translation and summarization.

Example helper functions:

```python
translate_to_english(text)
translate_to_tamil(text)
summarize_in_english(text)
summarize_in_tamil(text)
```

Recommended file location:

```text
aggregator/services/ollama_translate.py
```

Example usage in Django shell:

```bash
python manage.py shell
```

```python
from aggregator.services.ollama_translate import translate_to_english, summarize_in_english

text = "தமிழ்நாடு அரசு இன்று புதிய வேலைவாய்ப்பு அறிவிப்பை வெளியிட்டது."

print(translate_to_english(text))
print(summarize_in_english(text))
```

---

## API Endpoints

### Latest Items

```text
/api/latest/
```

Optional query parameters:

```text
?limit=50
?source_type=youtube
?primary_topic=politics_governance
?q=vijay
?include_jobs=1
```

### YouTube Items

```text
/api/youtube/
```

Optional:

```text
?limit=50
```

### Jobs

```text
/api/jobs/
```

Optional query parameters:

```text
?q=police
?district=Chennai
?category=government
?recruiting_body=tnusrb
?qualification_level=degree
?link_status=active
?min_salary=30000
?limit=50
```

### Alerts

```text
/api/alerts/
```

Optional:

```text
?status=new
?limit=50
```

### Trends

```text
/api/trends/
```

Optional:

```text
?hours=24
?hours=168
?hours=720
```

### Reports

Existing endpoint:

```text
/api/daily-report/
```

Recommended alias:

```text
/api/report/
```

Supported periods:

```text
/api/report/?period=daily
/api/report/?period=weekly
/api/report/?period=monthly
/api/report/?period=annual
```

Staff-only generation:

```text
/api/report/?period=daily&generate=1
/api/report/?period=daily&force=1
```

### Track Keyword

```text
/api/track/?q=vijay
```

---

## Suggested Local Development Workflow

### Start Ollama

```bash
ollama serve
```

### Activate Environment

```bash
source .venv/bin/activate
```

or:

```bash
conda activate newsiq
```

### Apply Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Start Server

```bash
python manage.py runserver
```

### Run Sync Commands

```bash
python manage.py sync_public_jobs --limit_per_source 50
python manage.py build_daily_report --period daily --top 20
```

---

## Deployment Notes

For deployment, set these values properly:

```text
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
SECRET_KEY=your-production-secret-key
```

Recommended production setup:

* PostgreSQL instead of SQLite
* Gunicorn or uWSGI
* Nginx or platform proxy
* Scheduled jobs for crawlers and report generation
* Environment variables for secrets and model configuration
* Staff-only admin access
* Proper logging and error monitoring

Example Gunicorn command:

```bash
gunicorn YOUR_PROJECT_NAME.wsgi:application
```

---

## Security Notes

* Do not allow anonymous visitors to trigger crawlers or report builders.
* Keep `SECRET_KEY` out of GitHub.
* Do not commit `.env`, local databases, logs, or scraped private data.
* Alert notification delivery should remain disabled until contact verification is implemented.
* Use staff-only permissions for expensive operations.
* Use scheduled jobs for production crawling and report generation.

Recommended `.gitignore` entries:

```gitignore
.env
*.sqlite3
db.sqlite3
__pycache__/
*.pyc
.DS_Store
.venv/
logs/
media/
staticfiles/
```

---

## Troubleshooting

### Ollama Connection Refused

Error:

```text
Connection refused
```

Fix:

```bash
ollama serve
```

Then check:

```bash
curl http://localhost:11434/api/tags
```

### Ollama Model Not Found

Error:

```text
model not found
```

Fix:

```bash
ollama list
ollama pull gpt-oss:20b
```

Or change the model:

```bash
export OLLAMA_TRANSLATION_MODEL=qwen2.5:3b-instruct
```

### Request Timeout

If translation or summarization times out, increase timeout in the Ollama request:

```python
response = requests.post(url, json=payload, timeout=300)
```

### Missing Database Column

Error:

```text
no such column: aggregator_source.extract_mode
```

Fix:

```bash
python manage.py makemigrations aggregator
python manage.py migrate
python manage.py runserver
```

### No Data Showing

Run sync or crawl commands:

```bash
python manage.py sync_public_jobs --limit_per_source 50
python manage.py build_daily_report --period daily --top 20
```

Also check whether sources are active in the database/admin panel.

---

## Roadmap

Possible future improvements:

* Add source management UI.
* Add verified email/WhatsApp alert delivery.
* Add scheduled background jobs using Celery or cron.
* Add PostgreSQL support for production.
* Add richer topic clustering.
* Add Tamil/English switch in all templates.
* Add YouTube transcript summarization.
* Add public report archive.
* Add user accounts and saved alert rules.
* Add export to CSV/JSON.
* Add analytics charts for parties, people, districts, and sources.

---

## License

Add your preferred license here.

Example:

```text
MIT License
```

---

## Author

Rick Rejeleene

Project: NewsIQ — Tamil Nadu News Intelligence Platform
