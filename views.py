from flask import Blueprint, render_template
from flask import request
import requests
import os
from dotenv import load_dotenv

# Load in environment variables
load_dotenv()

# Create a blueprint
main_blueprint = Blueprint('main', __name__)