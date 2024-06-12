# This file loads configuration from json
from json import load  # For reading config file

# Load config
with open('./config.json') as config_file:
    config = load(config_file)
TOKEN = config['token']
GUILD_IDS = config['guild_ids']
GITHUB_LINK = config['github_link']
DESCRIPTION = config['description']
OUTPUT_PATH = config['output_path']
