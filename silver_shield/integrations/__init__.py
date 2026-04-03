"""Ecosystem integrations -- EZ Merit, Auto-Agent, Community Shield."""

from .merit import MeritBridge
from .auto_agent import AutoAgentBridge
from .reconcile import MeritReconciler

__all__ = ["MeritBridge", "AutoAgentBridge", "MeritReconciler"]
