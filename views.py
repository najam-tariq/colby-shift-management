from flask import Blueprint, render_template
from flask import request
import requests
import os
from dotenv import load_dotenv

# Load in environment variables
load_dotenv()

# Create a blueprint
main_blueprint = Blueprint('main', __name__)

@main_blueprint.route('/', methods=['GET', 'POST'])
def shiftManagement():
    
    return render_template('dashboard.html')

@main_blueprint.route('/login', methods=['GET', 'POST'])
def shiftManagementLogin():
    
    return render_template('login.html')


@main_blueprint.route('/signup', methods=['GET', 'POST'])
def shiftManagementSignUp():
    
    return render_template('signup.html')
