"""FMCG Deal Intelligence pipeline package."""
from . import config, ingest, clean, credibility, relevance, newsletter, run  # noqa: F401

__all__ = ["config", "ingest", "clean", "credibility", "relevance", "newsletter", "run"]
__version__ = "1.0.0"
