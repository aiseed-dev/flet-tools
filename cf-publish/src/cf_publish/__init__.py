"""cf-publish — deploy to Cloudflare Pages, R2 and Workers, no wrangler needed."""

from .pages import DeployResult, PagesError, deploy
from .r2 import R2SyncResult, sync
from .worker import WorkerResult, deploy_worker

__version__ = "0.3.1"
__all__ = ["deploy", "DeployResult", "sync", "R2SyncResult", "deploy_worker",
           "WorkerResult", "PagesError", "__version__"]
