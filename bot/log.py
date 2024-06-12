# This file is used for debugging purposes to display pretty info, errors, warnings, exceptions, etc.
import logging
from rich.logging import RichHandler

log = logging.getLogger('rich')
log.setLevel(level=logging.DEBUG)
log.addHandler(RichHandler())
