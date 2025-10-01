# backend/gunicorn_conf.py
import multiprocessing, os

bind = f"0.0.0.0:{os.getenv('PORT','5000')}"
workers = int(os.getenv("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))
threads = int(os.getenv("WEB_THREADS", "2"))
timeout = int(os.getenv("WEB_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("WEB_GRACEFUL", "90"))
accesslog = "-"
errorlog = "-"
