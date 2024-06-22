# This file loads configuration from json and sets up logging
from json import load  # To load config
import logging  # For logging
from rich.logging import RichHandler  # For logging
from rich.traceback import install as setup_traceback  # For better error messages
from os.path import join, dirname  # To get current directory of the file

# Load config
config_dir = join(dirname(__file__), 'config.json')
with open(config_dir) as config_file:
    config = load(config_file)
TOKEN = config['token']
GUILD_IDS = config['guild_ids']
DESCRIPTION = config['description']
HELP_MESSAGE = config['help_message']
OUTPUT_PATH = config['output_path']
LOGO_PATH = config['logo']

# Set up logger
log = logging.getLogger('rich')
log.setLevel(level=logging.DEBUG)
log.addHandler(RichHandler())

