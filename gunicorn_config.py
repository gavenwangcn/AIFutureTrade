"""
Gunicorn configuration for production deployment
"""
import multiprocessing
import os

# Server socket
bind = os.getenv('GUNICORN_BIND', '0.0.0.0:5002')
backlog = int(os.getenv('GUNICORN_BACKLOG', '2048'))

# Worker processes
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'eventlet')
worker_connections = int(os.getenv('GUNICORN_WORKER_CONNECTIONS', '1000'))
threads = int(os.getenv('GUNICORN_THREADS', '40'))
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))
keepalive = int(os.getenv('GUNICORN_KEEPALIVE', '30'))

# Logging
accesslog = os.getenv('GUNICORN_ACCESSLOG', '-')  # 输出到stdout
access_log_level = os.getenv('GUNICORN_ACCESS_LOG_LEVEL', 'warning')  # 访问日志级别
errorlog = os.getenv('GUNICORN_ERRORLOG', '-')  # 输出到stderr
loglevel = os.getenv('GUNICORN_LOGLEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'aifuturetrade'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
keyfile = None
certfile = None

# Performance tuning
preload_app = True  # 预加载应用以提高性能
max_requests = int(os.getenv('GUNICORN_MAX_REQUESTS', '1000'))  # 每个worker处理的最大请求数
max_requests_jitter = int(os.getenv('GUNICORN_MAX_REQUESTS_JITTER', '50'))  # 随机抖动

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Server is ready. Spawning workers")

def worker_int(worker):
    """Called just after a worker has been killed."""
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_worker_init(worker):
    """Called just after a worker has initialized the application."""
    pass

def worker_abort(worker):
    """Called when a worker times out."""
    worker.log.info("Worker timeout (pid: %s)", worker.pid)

