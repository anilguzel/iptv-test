"""Weekly walk-forward research: does a model rank next week's winners?

Pipeline: daily bars -> weekly bars -> leakage-safe features -> models and
baselines -> walk-forward (train on the past, predict the next week, score it,
roll forward) -> report with a consistency verdict and next week's picks.

Everything here is analysis only. Nothing is applied to the live scoring or
places orders.
"""
