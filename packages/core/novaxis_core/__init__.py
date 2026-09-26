"""Novaxis core: the domain the worker operates in.

Everything a pack or an app needs to talk about (tenants, conversations, actions,
risk) is defined here and nowhere else. Apps import from core; core imports from
nothing above it.
"""

__version__ = "0.0.0"
