# This file loads configuration from json and sets up logging
from json import load
import logging
from rich.logging import RichHandler
import os

# Load config
config_dir = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_dir) as config_file:
    config = load(config_file)
TOKEN = config['token']
GUILD_IDS = config['guild_ids']
GITHUB_LINK = config['github_link']
DESCRIPTION = config['description']
OUTPUT_PATH = config['output_path']

# Set up logger
log = logging.getLogger('rich')
log.setLevel(level=logging.DEBUG)
log.addHandler(RichHandler())
