"""Ecosystem Auditor package for density-based expert germination."""

from master.auditor.ecosystem_auditor import (
    check_density_and_germinate,
    increment_packages_absorbed,
    CRITICAL_MASS_THRESHOLD
)

__all__ = [
    'check_density_and_germinate',
    'increment_packages_absorbed',
    'CRITICAL_MASS_THRESHOLD'
]
