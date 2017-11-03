# -*- coding: utf-8 -*-

import logging

_logger = None


def logger():
    global _logger

    if _logger:
        return _logger

    _logger = logging.getLogger(__name__)

    return _logger
